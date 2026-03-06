"""Authentication utilities for Food Safety Service.

Reads the portal JWT cookie to identify the current user.
"""
import logging
from dataclasses import dataclass
from typing import Optional

from fastapi import Request, HTTPException
from jose import jwt, JWTError

from food_safety.config import settings

logger = logging.getLogger(__name__)


@dataclass
class CurrentUser:
    user_id: int
    username: str
    full_name: str
    email: str
    is_admin: bool = False


def _decode_token(token: str) -> Optional[CurrentUser]:
    """Decode a portal JWT token and return CurrentUser."""
    # Try portal secret first, then local secret
    secrets = [s for s in [settings.PORTAL_SECRET_KEY, settings.SECRET_KEY] if s]
    for secret in secrets:
        try:
            payload = jwt.decode(token, secret, algorithms=[settings.ALGORITHM])
            user_id = payload.get("user_id")
            username = payload.get("sub")
            if not user_id or not username:
                continue
            return CurrentUser(
                user_id=user_id,
                username=username,
                full_name=payload.get("full_name", username),
                email=payload.get("email", ""),
                is_admin=payload.get("is_admin", False),
            )
        except JWTError:
            continue
    return None


def get_current_user_optional(request: Request) -> Optional[CurrentUser]:
    """Extract current user from Bearer header or portal_session cookie. Returns None if not authenticated."""
    # Try Authorization header first (for mobile app)
    token = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]

    # Fall back to cookie (web SSO)
    if not token:
        token = request.cookies.get("portal_session")

    if not token:
        return None
    return _decode_token(token)


def get_current_user_required(request: Request) -> CurrentUser:
    """Extract current user from portal_session cookie. Raises 401 if not authenticated."""
    user = get_current_user_optional(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user
