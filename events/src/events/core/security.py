"""
Security utilities for JWT token validation
"""

from jose import JWTError, jwt
from typing import Optional, Dict
import os

# Portal secret key - should match Portal configuration
PORTAL_SECRET_KEY = os.getenv("PORTAL_SECRET_KEY", "your-super-secret-key-change-in-production-galveston34")
PORTAL_ALGORITHM = "HS256"


def verify_jwt_token(token: str) -> Optional[Dict]:
    """
    Verify JWT token from Portal

    Args:
        token: JWT token string

    Returns:
        Dict with token payload if valid, None if invalid
    """
    try:
        payload = jwt.decode(token, PORTAL_SECRET_KEY, algorithms=[PORTAL_ALGORITHM])
        return payload
    except JWTError:
        return None
