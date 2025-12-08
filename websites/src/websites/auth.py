"""
Authentication - integrates with Portal SSO
"""
from fastapi import Request, HTTPException, Depends
from fastapi.responses import RedirectResponse
from jose import jwt, JWTError
from typing import Optional
from config import get_settings

settings = get_settings()


class User:
    """Authenticated user from Portal SSO"""
    def __init__(self, user_id: int, username: str, full_name: str, email: str, is_admin: bool = False):
        self.user_id = user_id
        self.username = username
        self.full_name = full_name
        self.email = email
        self.is_admin = is_admin


def get_current_user(request: Request) -> Optional[User]:
    """Extract user from Portal SSO cookie"""
    # Try portal_session first (main session cookie), fall back to portal_token for compatibility
    token = request.cookies.get("portal_session") or request.cookies.get("portal_token")
    if not token:
        return None

    try:
        payload = jwt.decode(token, settings.portal_sso_secret, algorithms=["HS256"])
        return User(
            user_id=payload.get("user_id"),
            username=payload.get("sub"),
            full_name=payload.get("full_name", ""),
            email=payload.get("email", ""),
            is_admin=payload.get("is_admin", False)
        )
    except JWTError:
        return None


def require_auth(request: Request) -> User:
    """Dependency that requires authentication"""
    user = get_current_user(request)
    if not user:
        # For htmx requests, return 401 so client can redirect
        if request.headers.get("HX-Request"):
            raise HTTPException(status_code=401, detail="Not authenticated")
        # For regular requests, redirect to portal login
        raise HTTPException(
            status_code=307,
            headers={"Location": f"/portal/login?next=/websites/"}
        )
    return user


def require_admin(request: Request) -> User:
    """Dependency that requires admin access"""
    user = require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
