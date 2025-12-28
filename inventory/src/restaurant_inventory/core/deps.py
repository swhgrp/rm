"""
Dependency functions for authentication and authorization
"""

import os
from typing import Generator, Optional
from fastapi import Depends, HTTPException, status, Request, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from restaurant_inventory.db.database import SessionLocal
from restaurant_inventory.core.security import verify_token
from restaurant_inventory.models.user import User

# Security scheme
security = HTTPBearer(auto_error=False)

# Internal API key for Hub-to-system communication - MUST be set via environment
HUB_INTERNAL_API_KEY = os.getenv("HUB_INTERNAL_API_KEY")
if not HUB_INTERNAL_API_KEY:
    raise ValueError("HUB_INTERNAL_API_KEY environment variable must be set")


def verify_hub_api_key(x_hub_api_key: str = Header(..., alias="X-Hub-API-Key")):
    """
    Verify the internal API key for Hub-to-system communication.
    This is used for internal endpoints like /_hub/sync and /_hub/receive.
    """
    if x_hub_api_key != HUB_INTERNAL_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Hub API key"
        )
    return True

def get_db() -> Generator:
    """Database session dependency"""
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()

def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> User:
    """Get current authenticated user with location assignments loaded"""
    from sqlalchemy.orm import joinedload

    # Try to get token from Authorization header first
    token = None
    if credentials:
        token = credentials.credentials
    else:
        # Try to get token from cookie (for SSO)
        cookie_token = request.cookies.get("access_token")
        if cookie_token:
            # Cookie format is "Bearer <token>"
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

    # Verify token
    user_id = verify_token(token)
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


def get_user_location_ids(user: User, db: Session = None) -> list:
    """
    Get list of location IDs the user has access to.

    Args:
        user: Current user object
        db: Database session (optional, needed for admins to get all location IDs)

    Returns:
        - List of all location IDs if user is admin (requires db session)
        - List of assigned location IDs if user has specific location assignments
        - Empty list if user has no access to any locations

    Admin users always have access to all locations.
    Non-admin users with assigned locations only see those locations.
    Non-admin users without assigned locations have NO access (empty list).
    """
    # Admins have access to everything
    if user.role == "Admin":
        # If db session provided, get all location IDs
        if db:
            from restaurant_inventory.models.location import Location
            all_locations = db.query(Location.id).filter(Location.is_active == True).all()
            return [loc.id for loc in all_locations]
        else:
            # Legacy behavior - return None to indicate all access
            return None

    # If user has assigned locations, return those IDs
    if user.assigned_locations:
        return [loc.id for loc in user.assigned_locations]

    # IMPORTANT: No assigned locations means NO ACCESS for non-admins
    # This prevents staff/managers from seeing all data
    return []


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
