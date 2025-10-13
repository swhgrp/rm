"""
Dependency functions for authentication and authorization
"""

from typing import Generator, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from restaurant_inventory.db.database import SessionLocal
from restaurant_inventory.core.security import verify_token
from restaurant_inventory.models.user import User

# Security scheme
security = HTTPBearer()

def get_db() -> Generator:
    """Database session dependency"""
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()

def get_current_user(
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> User:
    """Get current authenticated user with location assignments loaded"""
    from sqlalchemy.orm import joinedload

    # Verify token
    user_id = verify_token(credentials.credentials)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get user from database with location assignments eagerly loaded
    user = db.query(User).options(
        joinedload(User.assigned_locations)
    ).filter(User.id == int(user_id)).first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )

    return user

def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """Get current active user"""
    return current_user

def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require admin role"""
    if current_user.role != "Admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user

def require_manager_or_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require manager or admin role"""
    if current_user.role not in ["Admin", "Manager"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user


def get_user_location_ids(user: User) -> Optional[list]:
    """
    Get list of location IDs the user has access to.

    Returns:
        - None if user has no restrictions (access to all locations)
        - List of location IDs if user has specific location assignments

    Admin users always have access to all locations (returns None).
    """
    # Admins have access to everything
    if user.role == "Admin":
        return None

    # If user has assigned locations, return those IDs
    if user.assigned_locations:
        return [loc.id for loc in user.assigned_locations]

    # No assigned locations means no restrictions (access to all)
    return None


def filter_by_user_locations(query, location_column, user: User):
    """
    Filter a query by user's assigned locations.

    Args:
        query: SQLAlchemy query object
        location_column: The column to filter on (e.g., Inventory.location_id)
        user: Current user object

    Returns:
        Filtered query or original query if user has access to all locations
    """
    location_ids = get_user_location_ids(user)

    # If location_ids is None, user has access to all locations
    if location_ids is None:
        return query

    # Filter by assigned location IDs
    return query.filter(location_column.in_(location_ids))
