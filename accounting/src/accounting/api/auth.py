"""
Authentication API endpoints
"""
import os
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request, Header
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from typing import Optional

from accounting.db.database import get_db
from accounting.models.user import User, UserSession
from accounting.schemas.user import LoginRequest, LoginResponse, UserResponse
from accounting.core.security import verify_password, generate_session_token
from accounting.core.portal_sso import validate_portal_token

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# Internal API key for Hub-to-system communication - MUST be set via environment
HUB_INTERNAL_API_KEY = os.getenv("HUB_INTERNAL_API_KEY")
if not HUB_INTERNAL_API_KEY:
    raise ValueError("HUB_INTERNAL_API_KEY environment variable must be set")


def verify_hub_api_key(x_hub_api_key: str = Header(..., alias="X-Hub-API-Key")):
    """
    Verify the internal API key for Hub-to-system communication.
    This is used for internal endpoints like /_hub/sync and /_hub/receive.
    """
    if x_hub_api_key != HUB_INTERNAL_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Hub API key"
        )
    return True


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    """Get current logged-in user from session"""
    session_token = request.cookies.get("accounting_session")

    if not session_token:
        return None

    # Find active session
    session = db.query(UserSession).filter(
        UserSession.session_id == session_token,
        UserSession.is_active == True,
        UserSession.expires_at > datetime.now(timezone.utc)
    ).first()

    if not session:
        return None

    user = db.query(User).filter(
        User.id == session.user_id,
        User.is_active == True
    ).first()

    return user


def require_auth(request: Request, db: Session = Depends(get_db)) -> User:
    """Require authentication - raise exception if not logged in"""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    return user


def require_admin(user: User = Depends(require_auth)) -> User:
    """Require admin privileges"""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return user


@router.post("/login", response_model=LoginResponse)
async def login(
    login_data: LoginRequest,
    response: Response,
    db: Session = Depends(get_db)
):
    """Login to accounting system"""
    # Find user by username
    user = db.query(User).filter(User.username == login_data.username).first()

    if not user or not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )

    # Generate session token
    session_token = generate_session_token()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)

    # Create session
    session = UserSession(
        user_id=user.id,
        session_id=session_token,
        expires_at=expires_at
    )
    db.add(session)

    # Update last login
    user.last_login = datetime.now(timezone.utc)
    db.commit()

    # Set session cookie
    response.set_cookie(
        key="accounting_session",
        value=session_token,
        httponly=True,
        max_age=1800,  # 30 minutes (30 * 60 seconds)
        samesite="lax"
    )

    return LoginResponse(
        user=UserResponse.model_validate(user),
        message="Login successful"
    )


@router.get("/sso-login")
async def sso_login(
    token: str,
    response: Response,
    db: Session = Depends(get_db)
):
    """SSO login from Portal"""
    # Validate Portal token
    portal_user = validate_portal_token(token, "accounting")

    if not portal_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired Portal token"
        )

    # Find or create user based on Portal information
    user = db.query(User).filter(User.username == portal_user["username"]).first()

    if not user:
        # Create user from Portal information
        user = User(
            username=portal_user["username"],
            email=portal_user["email"],
            full_name=portal_user["full_name"],
            hashed_password="",  # No password for SSO users
            is_active=True,
            is_admin=portal_user.get("is_admin", False)
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )

    # Generate session token
    session_token = generate_session_token()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)

    # Create session
    session = UserSession(
        user_id=user.id,
        session_id=session_token,
        expires_at=expires_at
    )
    db.add(session)

    # Update last login
    user.last_login = datetime.now(timezone.utc)
    db.commit()

    # Set session cookie
    response.set_cookie(
        key="accounting_session",
        value=session_token,
        httponly=True,
        max_age=1800,  # 30 minutes (30 * 60 seconds)
        samesite="lax"
    )

    # Redirect to accounting dashboard
    from fastapi.responses import RedirectResponse
    redirect_response = RedirectResponse(url="/accounting/", status_code=303)
    redirect_response.set_cookie(
        key="accounting_session",
        value=session_token,
        httponly=True,
        max_age=1800,  # 30 minutes
        samesite="lax"
    )

    return redirect_response


@router.post("/logout")
async def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    """Logout from accounting system"""
    session_token = request.cookies.get("accounting_session")

    if session_token:
        # Deactivate session
        session = db.query(UserSession).filter(
            UserSession.session_id == session_token
        ).first()
        if session:
            session.is_active = False
            db.commit()

    response.delete_cookie(key="accounting_session")

    return {"message": "Logged out successfully"}


@router.get("/logout")
async def logout_get(request: Request, db: Session = Depends(get_db)):
    """Logout from accounting system (GET method for direct links)"""
    from fastapi.responses import RedirectResponse

    session_token = request.cookies.get("accounting_session")

    if session_token:
        # Deactivate session
        session = db.query(UserSession).filter(
            UserSession.session_id == session_token
        ).first()
        if session:
            session.is_active = False
            db.commit()

    response = RedirectResponse(url="/accounting/login", status_code=302)
    response.delete_cookie(key="accounting_session")

    return response


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(user: User = Depends(require_auth)):
    """Get current user information"""
    return UserResponse.model_validate(user)


@router.get("/check")
async def check_auth(request: Request, db: Session = Depends(get_db)):
    """Check if user is authenticated"""
    user = get_current_user(request, db)

    if user:
        return {
            "authenticated": True,
            "user": UserResponse.model_validate(user)
        }

    return {"authenticated": False}
