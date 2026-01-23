"""Portal SSO authentication - JWT-based"""
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer
from jose import JWTError, jwt
import logging

from forms.config import settings

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)

# Cookie name must match Portal's SESSION_COOKIE_NAME
SESSION_COOKIE_NAME = "portal_session"
ALGORITHM = "HS256"


def decode_session_token(token: str) -> dict:
    """Decode a Portal session JWT token and return user data."""
    try:
        payload = jwt.decode(token, settings.PORTAL_SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            return None

        # Return user info from the token
        return {
            "username": username,
            "id": payload.get("user_id"),
            "role": payload.get("role", "user"),
            "is_admin": payload.get("is_admin", False),
            "full_name": payload.get("full_name"),
            "locations": payload.get("locations", [])
        }
    except JWTError as e:
        logger.debug(f"JWT decode error: {e}")
        return None


async def verify_portal_session(session_token: str) -> dict:
    """Verify a portal session token and return user data."""
    user = decode_session_token(session_token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session"
        )
    return user


async def get_current_user(request: Request):
    """Validate session from Portal JWT cookie."""
    session_token = request.cookies.get(SESSION_COOKIE_NAME)

    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )

    user = decode_session_token(session_token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session"
        )

    return user


async def get_current_user_optional(request: Request):
    """Get current user if authenticated, None otherwise."""
    session_token = request.cookies.get(SESSION_COOKIE_NAME)

    if not session_token:
        return None

    return decode_session_token(session_token)


async def require_admin(user: dict = Depends(get_current_user)):
    """Require admin role."""
    if user.get("role") not in ["admin", "superadmin"] and not user.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return user


async def require_manager(user: dict = Depends(get_current_user)):
    """Require manager or higher role."""
    if user.get("role") not in ["manager", "gm", "admin", "superadmin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manager access required"
        )
    return user


async def require_hr(user: dict = Depends(get_current_user)):
    """Require HR role."""
    if user.get("role") not in ["hr", "admin", "superadmin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="HR access required"
        )
    return user
