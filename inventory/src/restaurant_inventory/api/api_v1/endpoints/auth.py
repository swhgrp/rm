"""
Authentication endpoints
"""

from datetime import timedelta, datetime
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address
from pydantic import BaseModel

from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
def get_now(): return datetime.now(_ET)

from restaurant_inventory.core.config import settings
from restaurant_inventory.core.security import verify_password, create_access_token, get_password_hash
from restaurant_inventory.core.deps import get_db, get_current_user
from restaurant_inventory.models.user import User
from restaurant_inventory.models.password_reset_token import PasswordResetToken
from restaurant_inventory.schemas.auth import LoginResponse, UserResponse, UserCreate
from restaurant_inventory.core.audit import log_audit_event
from restaurant_inventory.core.portal_sso import validate_portal_token

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


class PasswordSetupRequest(BaseModel):
    """Request model for password setup"""
    token: str
    password: str

@router.post("/login", response_model=LoginResponse)
@limiter.limit("5/minute")
async def login(
    request: Request,
    db: Session = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends()
):
    """User login endpoint"""
    
    # Find user by username
    user = db.query(User).filter(User.username == form_data.username).first()
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    
    # Create access token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        subject=user.id, expires_delta=access_token_expires
    )
    
    # Update last login
    user.last_login = get_now()
    db.commit()

    # Log audit event
    log_audit_event(
        db=db,
        action="LOGIN",
        entity_type="user",
        entity_id=user.id,
        user=user,
        request=request
    )

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.from_orm(user)
    )


@router.get("/sso-login")
async def sso_login(
    token: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """SSO login from Portal"""
    from fastapi.responses import Response

    # Validate Portal token
    portal_user = validate_portal_token(token, "inventory")

    if not portal_user:
        # Return with no-cache headers to prevent caching of 401 errors
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired Portal token",
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache"
            }
        )

    # Find or create user based on Portal information
    user = db.query(User).filter(User.username == portal_user["username"]).first()

    if not user:
        # Create user from Portal information
        # Set role based on is_admin flag from portal
        # Use "Admin" not "ADMIN" to match permission checks
        role = "Admin" if portal_user.get("is_admin", False) else "Staff"

        user = User(
            username=portal_user["username"],
            email=portal_user["email"],
            full_name=portal_user["full_name"],
            hashed_password="",  # No password for SSO users
            is_active=True,
            role=role
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        # Update existing user from Portal information
        # Always activate users who successfully authenticate via SSO
        user.is_active = True
        user.email = portal_user["email"]
        user.full_name = portal_user["full_name"]

        # Update role if user is admin in portal
        # Use "Admin" not "ADMIN" to match permission checks
        if portal_user.get("is_admin", False):
            user.role = "Admin"

        db.commit()
        db.refresh(user)

    # Create access token for this system
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        subject=user.id, expires_delta=access_token_expires
    )

    # Update last login
    user.last_login = get_now()
    db.commit()

    # Log audit event
    log_audit_event(
        db=db,
        action="SSO_LOGIN",
        entity_type="user",
        entity_id=user.id,
        user=user,
        request=request
    )

    # Redirect to dashboard with token
    # We need to set the token in localStorage via JavaScript since the frontend expects it there
    from fastapi.responses import HTMLResponse
    import json

    # Create user response object
    user_data = {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active
    }

    # Convert to JSON string for embedding in JavaScript
    user_json = json.dumps(user_data).replace("'", "\\'")

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Logging in...</title>
        <style>
            body {{
                background-color: #0d1117;
                margin: 0;
                padding: 0;
            }}
        </style>
    </head>
    <body>
        <script>
            // Store token and user in localStorage for the frontend
            localStorage.setItem('access_token', '{access_token}');
            localStorage.setItem('user', '{user_json}');
            localStorage.setItem('user_role', '{user_data["role"]}');
            // Redirect to dashboard immediately
            window.location.href = '/inventory/';
        </script>
    </body>
    </html>
    """

    return HTMLResponse(content=html_content)


@router.post("/register", response_model=UserResponse)
@limiter.limit("3/hour")
async def register(
    request: Request,
    user_data: UserCreate,
    db: Session = Depends(get_db)
):
    """User registration endpoint"""
    
    # Check if username already exists
    if db.query(User).filter(User.username == user_data.username).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    # Check if email already exists
    if db.query(User).filter(User.email == user_data.email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create new user
    user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        full_name=user_data.full_name,
        role=user_data.role,
        is_active=True,
        is_verified=False
    )
    
    db.add(user)
    db.commit()
    db.refresh(user)
    
    return UserResponse.from_orm(user)

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """Get current user information"""
    return UserResponse.from_orm(current_user)


@router.get("/keepalive")
async def keepalive(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Keepalive endpoint pinged every 5 minutes by the inactivity warning system.
    Validates the current token and returns a fresh one to extend the session.
    """
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    new_token = create_access_token(
        subject=current_user.id, expires_delta=access_token_expires
    )

    return {
        "status": "ok",
        "access_token": new_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }


@router.post("/refresh-token")
async def refresh_token(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Refresh the access token for an authenticated user.

    This endpoint issues a new token with a fresh expiration time,
    effectively extending the session as long as the user is active.
    The old token remains valid until it expires.
    """
    # Create new access token with fresh expiration
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    new_token = create_access_token(
        subject=current_user.id, expires_delta=access_token_expires
    )

    return {
        "access_token": new_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60  # seconds
    }


@router.post("/logout")
async def logout():
    """User logout endpoint"""
    # In a real app, you might want to blacklist the token
    return {"message": "Successfully logged out"}


@router.get("/verify-token/{token}")
async def verify_setup_token(
    token: str,
    db: Session = Depends(get_db)
):
    """
    Verify if a password setup/reset token is valid.
    Returns user information if valid.
    """
    # Find the token
    reset_token = db.query(PasswordResetToken).filter(
        PasswordResetToken.token == token,
        PasswordResetToken.is_used == False
    ).first()

    if not reset_token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or expired token"
        )

    # Check if token is expired
    if get_now() > reset_token.expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation link has expired. Please contact your administrator for a new invitation."
        )

    # Get the user
    user = db.query(User).filter(User.id == reset_token.user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return {
        "valid": True,
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "token_type": reset_token.token_type
    }


@router.post("/setup-password")
async def setup_password(
    request: Request,
    password_data: PasswordSetupRequest,
    db: Session = Depends(get_db)
):
    """
    Set up password for a new user using invitation token.
    This activates the user account.
    """
    # Find the token
    reset_token = db.query(PasswordResetToken).filter(
        PasswordResetToken.token == password_data.token,
        PasswordResetToken.is_used == False
    ).first()

    if not reset_token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or expired token"
        )

    # Check if token is expired
    if get_now() > reset_token.expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation link has expired. Please contact your administrator for a new invitation."
        )

    # Get the user
    user = db.query(User).filter(User.id == reset_token.user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Validate password strength (basic validation)
    if len(password_data.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long"
        )

    # Update user password
    user.hashed_password = get_password_hash(password_data.password)
    user.is_active = True  # Activate the account
    user.is_verified = True

    # Mark token as used
    reset_token.is_used = True
    reset_token.used_at = get_now()

    db.commit()

    # Log audit event
    log_audit_event(
        db=db,
        action="PASSWORD_SETUP",
        entity_type="user",
        entity_id=user.id,
        user=user,
        changes={"action": "Account activated via invitation"},
        request=request
    )

    # Create access token for automatic login
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        subject=user.id, expires_delta=access_token_expires
    )

    return {
        "message": "Password set successfully! Your account is now active.",
        "access_token": access_token,
        "token_type": "bearer",
        "user": UserResponse.from_orm(user)
    }
