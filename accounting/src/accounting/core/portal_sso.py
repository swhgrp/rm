"""
Portal SSO Authentication Helper
Shared module for validating Portal SSO tokens across all systems
"""

from jose import JWTError, jwt
from typing import Optional, Dict
import os
import logging

logger = logging.getLogger(__name__)

# Portal secret key - MUST be set via environment variable
PORTAL_SECRET_KEY = os.getenv("PORTAL_SECRET_KEY")
if not PORTAL_SECRET_KEY:
    raise ValueError("PORTAL_SECRET_KEY environment variable must be set")
PORTAL_ALGORITHM = "HS256"


def validate_portal_token(token: str, expected_system: str) -> Optional[Dict]:
    """
    Validate a Portal SSO token

    Args:
        token: JWT token from Portal
        expected_system: The system name this token should be for (inventory, accounting, hr, hub)

    Returns:
        Dict with user information if valid, None if invalid
    """
    try:
        payload = jwt.decode(token, PORTAL_SECRET_KEY, algorithms=[PORTAL_ALGORITHM])

        # Verify the token is for this system
        if payload.get("system") != expected_system:
            logger.warning(f"SSO token system mismatch: expected={expected_system}, got={payload.get('system')}, sub={payload.get('sub')}")
            return None

        # Extract user information
        return {
            "username": payload.get("sub"),
            "email": payload.get("email"),
            "full_name": payload.get("full_name"),
            "user_id": payload.get("user_id"),
            "is_admin": payload.get("is_admin", False),
            "accounting_role_id": payload.get("accounting_role_id")
        }
    except JWTError:
        return None
