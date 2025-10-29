"""
Dependency injection for FastAPI routes
"""
from typing import Generator, Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from nextcloud.db.database import SessionLocal, HRSessionLocal
from nextcloud.core.security import verify_token
from nextcloud.models.user import User

security = HTTPBearer(auto_error=False)


def get_db() -> Generator:
    """
    Database session dependency for Nextcloud database

    Yields:
        Database session
    """
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()


def get_hr_db() -> Generator:
    """
    Database session dependency for HR database (users table)

    Yields:
        Database session
    """
    try:
        db = HRSessionLocal()
        yield db
    finally:
        db.close()


def get_current_user(
    request: Request,
    db: Session = Depends(get_hr_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> User:
    """
    Get current authenticated user from JWT token

    Supports both Authorization header and cookie-based authentication
    for compatibility with Portal SSO.

    Args:
        request: FastAPI request object
        db: Database session
        credentials: HTTP Bearer credentials

    Returns:
        Authenticated User object

    Raises:
        HTTPException: If authentication fails
    """
    # Try Authorization header first
    token = None
    if credentials:
        token = credentials.credentials
    else:
        # Try cookie for SSO from Portal
        cookie_token = request.cookies.get("access_token")
        if cookie_token:
            if cookie_token.startswith("Bearer "):
                token = cookie_token[7:]
            else:
                token = cookie_token

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = verify_token(token)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        )

    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )

    return user


def require_nextcloud_setup(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Require user to have Nextcloud credentials configured

    Args:
        current_user: Authenticated user

    Returns:
        User object with Nextcloud credentials

    Raises:
        HTTPException: If Nextcloud credentials not configured
    """
    if not current_user.nextcloud_username or not current_user.nextcloud_encrypted_password:
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail="Nextcloud credentials not configured. Please set up your Nextcloud connection first."
        )

    return current_user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """
    Require admin role

    Args:
        current_user: Authenticated user

    Returns:
        User object with admin role

    Raises:
        HTTPException: If user is not admin
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user
