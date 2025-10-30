"""
Authentication API endpoints for Events system
"""
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional
import secrets

from events.core.database import get_db
from events.models.user import User, Role
from events.core.portal_sso import validate_portal_token

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# Simple session store (in production, use Redis)
_sessions = {}


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    """Get current logged-in user from session"""
    session_token = request.cookies.get("events_session")

    if not session_token or session_token not in _sessions:
        return None

    session = _sessions[session_token]
    if session['expires_at'] < datetime.utcnow():
        del _sessions[session_token]
        return None

    user = db.query(User).filter(
        User.id == session['user_id'],
        User.is_active == True
    ).first()

    return user


def require_auth(request: Request, db: Session = Depends(get_db)) -> User:
    """Require authentication - raise exception if not logged in"""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated - please log in via Portal"
        )
    return user


@router.get("/sso-login")
async def sso_login(
    token: str,
    response: Response,
    db: Session = Depends(get_db)
):
    """SSO login from Portal"""
    # Validate Portal token
    portal_user = validate_portal_token(token, "events")

    if not portal_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired Portal token"
        )

    # Find or create user based on Portal information
    user = db.query(User).filter(User.email == portal_user["email"]).first()

    if not user:
        # Create user from Portal information
        user = User(
            email=portal_user["email"],
            full_name=portal_user["full_name"],
            is_active=True,
            source='portal'
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # Assign default role (staff) for new users
        default_role = db.query(Role).filter(Role.code == "staff").first()
        if default_role:
            user.roles.append(default_role)
            db.commit()
    else:
        # Update user information from Portal
        user.full_name = portal_user["full_name"]
        user.is_active = True
        db.commit()

    # Generate session token
    session_token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(minutes=30)

    # Store session
    _sessions[session_token] = {
        'user_id': user.id,
        'expires_at': expires_at,
        'email': user.email
    }

    # Create redirect response with session cookie
    redirect_response = RedirectResponse(url="/events/", status_code=303)
    redirect_response.set_cookie(
        key="events_session",
        value=session_token,
        httponly=True,
        max_age=30 * 60,  # 30 minutes
        samesite="lax"
    )

    return redirect_response


@router.get("/logout")
async def logout(request: Request, response: Response):
    """Logout current user"""
    session_token = request.cookies.get("events_session")

    if session_token and session_token in _sessions:
        del _sessions[session_token]

    # Redirect to portal
    redirect_response = RedirectResponse(url="/portal/", status_code=303)
    redirect_response.delete_cookie("events_session")
    return redirect_response


@router.get("/me")
async def get_current_user_info(user: User = Depends(require_auth)):
    """Get current user information"""
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "department": user.department,
        "roles": [{"code": role.code, "name": role.name} for role in user.roles],
        "is_active": user.is_active
    }


@router.post("/sync-password")
async def sync_password_from_portal(
    sync_data: dict,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Sync password from Portal (internal service API)
    Called by Portal when user changes password to keep all systems in sync
    """
    import os
    import logging

    logger = logging.getLogger(__name__)

    # Validate internal service token
    portal_token = request.headers.get("X-Portal-Auth")
    portal_secret = os.getenv("PORTAL_SECRET_KEY", "your-super-secret-key-change-in-production-galveston34")

    # Simple validation - check if it matches the portal secret key
    if portal_token != portal_secret:
        logger.warning(f"Invalid portal token in password sync request from {request.client.host}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized - Invalid service token"
        )

    username = sync_data.get("username")
    new_hashed_password = sync_data.get("hashed_password")

    if not username or not new_hashed_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required fields: username and hashed_password"
        )

    # Find user by username
    user = db.query(User).filter(User.username == username).first()

    if user:
        # Update password
        user.hashed_password = new_hashed_password
        db.commit()

        logger.info(f"Password synced for user {username} from Portal")

        return {
            "message": "Password synced successfully",
            "username": username,
            "user_exists": True
        }
    else:
        # User doesn't exist yet (hasn't logged in via SSO)
        # This is OK - password will be set when they first login
        logger.info(f"Password sync skipped for user {username} - user not found (will be set on first SSO login)")

        return {
            "message": "User not found in Events system - password will be set on first SSO login",
            "username": username,
            "user_exists": False
        }
