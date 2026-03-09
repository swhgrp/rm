"""
Authentication API endpoints for HR system
"""
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional

from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
def get_now(): return datetime.now(_ET)

from hr.db.database import get_db
from hr.models.user import User
from hr.schemas.user import LoginRequest, LoginResponse, UserResponse, ChangePasswordRequest
from hr.core.security import verify_password, hash_password
from hr.core.portal_sso import validate_portal_token


router = APIRouter(prefix="/api/auth", tags=["Authentication"])


# Session storage (in production, use Redis or database)
active_sessions = {}


def _try_bearer_auth(request: Request, db: Session) -> Optional[User]:
    """Try to authenticate via Authorization: Bearer header using Portal JWT."""
    from sqlalchemy.orm import joinedload
    from jose import jwt, JWTError
    import os

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None

    token = auth_header[7:]
    portal_secret = os.getenv("PORTAL_SECRET_KEY")
    if not portal_secret:
        return None

    try:
        payload = jwt.decode(token, portal_secret, algorithms=["HS256"])
        username = payload.get("sub")
        if not username:
            return None
    except JWTError:
        return None

    user = db.query(User).options(
        joinedload(User.assigned_locations)
    ).filter(User.username == username, User.is_active == True).first()
    return user


def _try_portal_cookie_auth(request: Request, db: Session) -> Optional[User]:
    """Try to authenticate via the portal_session cookie (Portal JWT).
    This allows HR sessions to survive HR container restarts as long as
    the user is still logged into the Portal."""
    from sqlalchemy.orm import joinedload
    from jose import jwt, JWTError
    import os

    portal_token = request.cookies.get("portal_session")
    if not portal_token:
        return None

    portal_secret = os.getenv("PORTAL_SECRET_KEY")
    if not portal_secret:
        return None

    try:
        payload = jwt.decode(portal_token, portal_secret, algorithms=["HS256"])
        username = payload.get("sub")
        if not username:
            return None
    except JWTError:
        return None

    user = db.query(User).options(
        joinedload(User.assigned_locations)
    ).filter(User.username == username, User.is_active == True).first()

    if user:
        # Auto-create an HR session so subsequent requests don't need to decode JWT again
        from hr.core.security import generate_session_token
        new_session = generate_session_token()
        active_sessions[new_session] = user.id
        # Store on request state so middleware/response can set the cookie
        request.state.new_hr_session = new_session

    return user


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    """Get current logged-in user from Bearer token, session cookie, or Portal cookie, with location assignments eagerly loaded."""
    from sqlalchemy.orm import joinedload

    # Try Bearer token first (for mobile app)
    user = _try_bearer_auth(request, db)
    if user:
        return user

    # Fall back to session cookie (web)
    session_token = request.cookies.get("hr_session")

    if session_token:
        user_id = active_sessions.get(session_token)
        if user_id:
            user = db.query(User).options(
                joinedload(User.assigned_locations)
            ).filter(User.id == user_id, User.is_active == True).first()
            if user:
                return user

    # Fall back to Portal session cookie (SSO — survives HR restarts)
    user = _try_portal_cookie_auth(request, db)
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
    """Login to HR system"""
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
    from hr.core.security import generate_session_token
    session_token = generate_session_token()
    active_sessions[session_token] = user.id

    # Update last login
    user.last_login = get_now()
    db.commit()

    # Set session cookie
    response.set_cookie(
        key="hr_session",
        value=session_token,
        httponly=True,
        max_age=1800,  # 30 minutes (30 * 60 seconds)
        samesite="lax"
    )

    # Get user roles
    from hr.core.authorization import get_user_roles
    user_data = UserResponse.model_validate(user)
    user_data.roles = get_user_roles(db, user)

    return LoginResponse(
        user=user_data,
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
    portal_user = validate_portal_token(token, "hr")

    if not portal_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired Portal token"
        )

    # Find user - HR users should already exist in HR system
    user = db.query(User).filter(User.username == portal_user["username"]).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found in HR system"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )

    # Generate session token
    from hr.core.security import generate_session_token
    session_token = generate_session_token()
    active_sessions[session_token] = user.id

    # Update last login
    user.last_login = get_now()
    db.commit()

    # Redirect to HR dashboard
    from fastapi.responses import RedirectResponse
    redirect_response = RedirectResponse(url="/hr/", status_code=303)
    redirect_response.set_cookie(
        key="hr_session",
        value=session_token,
        httponly=True,
        max_age=1800,  # 30 minutes
        samesite="lax"
    )

    return redirect_response


@router.get("/keepalive")
async def keepalive(request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Keep the HR session alive.
    Called periodically by the frontend when user is active to extend the session.
    """
    session_token = request.cookies.get("hr_session")

    if not session_token or session_token not in active_sessions:
        raise HTTPException(status_code=401, detail="Session expired")

    # Refresh cookie max_age (session is in-memory dict, no expiration to update)
    response.set_cookie(
        key="hr_session",
        value=session_token,
        httponly=True,
        max_age=1800,
        samesite="lax"
    )

    return {"status": "ok", "session_extended": True}


@router.post("/logout")
async def logout(request: Request, response: Response):
    """Logout from HR system"""
    session_token = request.cookies.get("hr_session")

    if session_token and session_token in active_sessions:
        del active_sessions[session_token]

    response.delete_cookie(key="hr_session")

    return {"message": "Logged out successfully"}


@router.get("/logout")
async def logout_get(request: Request):
    """Logout from HR system (GET method for direct links)"""
    from starlette.responses import RedirectResponse

    session_token = request.cookies.get("hr_session")

    if session_token and session_token in active_sessions:
        del active_sessions[session_token]

    response = RedirectResponse(url="/hr/login", status_code=302)
    response.delete_cookie(key="hr_session")

    return response


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Get current user information"""
    from hr.core.authorization import get_user_roles

    user_data = UserResponse.model_validate(user)
    user_data.roles = get_user_roles(db, user)
    return user_data


@router.get("/check")
async def check_auth(request: Request, db: Session = Depends(get_db)):
    """Check if user is authenticated"""
    from hr.core.authorization import get_user_roles

    user = get_current_user(request, db)

    if user:
        user_data = UserResponse.model_validate(user)
        user_data.roles = get_user_roles(db, user)
        return {
            "authenticated": True,
            "user": user_data
        }

    return {"authenticated": False}


@router.post("/change-password")
async def change_password(
    password_data: ChangePasswordRequest,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Change current user's password"""
    # Verify current password
    if not verify_password(password_data.current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )

    # Validate new password
    if len(password_data.new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 6 characters"
        )

    # Hash and update password
    user.hashed_password = hash_password(password_data.new_password)
    db.commit()

    return {"message": "Password updated successfully"}
