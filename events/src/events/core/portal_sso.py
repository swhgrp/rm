"""
Portal SSO Authentication Helper
Shared module for validating Portal SSO tokens
"""

from jose import JWTError, jwt
from typing import Optional, Dict
import os

# Portal secret key - should match Portal configuration
PORTAL_SECRET_KEY = os.getenv("PORTAL_SECRET_KEY", "your-super-secret-key-change-in-production-galveston34")
PORTAL_ALGORITHM = "HS256"


def validate_portal_token(token: str, expected_system: str) -> Optional[Dict]:
    """
    Validate a Portal SSO token

    Args:
        token: JWT token from Portal
        expected_system: The system name this token should be for (events)

    Returns:
        Dict with user information if valid, None if invalid
    """
    try:
        payload = jwt.decode(token, PORTAL_SECRET_KEY, algorithms=[PORTAL_ALGORITHM])

        # Verify the token is for this system
        if payload.get("system") != expected_system:
            return None

        # Extract user information
        return {
            "username": payload.get("sub"),
            "email": payload.get("email"),
            "full_name": payload.get("full_name"),
            "user_id": payload.get("user_id"),
            "is_admin": payload.get("is_admin", False),
        }
    except JWTError:
        return None
