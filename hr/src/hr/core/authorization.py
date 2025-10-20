"""
Authorization and permission checking utilities
"""
from typing import List, Set, Optional
from fastapi import HTTPException, status, Depends
from sqlalchemy.orm import Session, joinedload

from hr.models.user import User
from hr.models.role import Role
from hr.models.permission import Permission
from hr.models.user_role import UserRole
from hr.models.role_permission import RolePermission
from hr.api.auth import require_auth


def get_user_permissions(db: Session, user: User) -> Set[str]:
    """
    Get all permissions for a user based on their roles
    Returns a set of permission names
    """
    # Get all user's roles
    user_roles = db.query(UserRole).filter(UserRole.user_id == user.id).all()

    if not user_roles:
        return set()

    role_ids = [ur.role_id for ur in user_roles]

    # Get all permissions for these roles
    role_permissions = db.query(RolePermission).filter(
        RolePermission.role_id.in_(role_ids)
    ).all()

    if not role_permissions:
        return set()

    permission_ids = [rp.permission_id for rp in role_permissions]

    # Get permission names
    permissions = db.query(Permission).filter(Permission.id.in_(permission_ids)).all()

    return {p.name for p in permissions}


def get_user_roles(db: Session, user: User) -> List[str]:
    """
    Get all role names for a user
    Returns a list of role names
    """
    user_roles = db.query(UserRole).join(Role).filter(
        UserRole.user_id == user.id,
        Role.is_active == True
    ).all()

    if not user_roles:
        return []

    role_ids = [ur.role_id for ur in user_roles]
    roles = db.query(Role).filter(Role.id.in_(role_ids)).all()

    return [r.name for r in roles]


def check_permission(db: Session, user: User, permission_name: str) -> bool:
    """
    Check if a user has a specific permission
    Returns True if user has the permission, False otherwise
    """
    # Admin users have all permissions
    if user.is_admin:
        return True

    user_permissions = get_user_permissions(db, user)
    return permission_name in user_permissions


def check_role(db: Session, user: User, role_name: str) -> bool:
    """
    Check if a user has a specific role
    Returns True if user has the role, False otherwise
    """
    # Admin users implicitly have Admin role
    if user.is_admin and role_name.lower() == "admin":
        return True

    user_roles = get_user_roles(db, user)
    return role_name in user_roles


def require_permission(permission_name: str):
    """
    Dependency to require a specific permission
    Usage: @router.get("/endpoint", dependencies=[Depends(require_permission("view_employees"))])
    """
    def permission_checker(
        user: User = Depends(require_auth),
        db: Session = Depends(get_db)
    ) -> User:
        if not check_permission(db, user, permission_name):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied. Required permission: {permission_name}"
            )
        return user

    return permission_checker


def require_role(role_name: str):
    """
    Dependency to require a specific role
    Usage: @router.get("/endpoint", dependencies=[Depends(require_role("Manager"))])
    """
    def role_checker(
        user: User = Depends(require_auth),
        db: Session = Depends(get_db)
    ) -> User:
        if not check_role(db, user, role_name):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role: {role_name}"
            )
        return user

    return role_checker


def require_any_permission(*permission_names: str):
    """
    Dependency to require any one of multiple permissions
    Usage: @router.get("/endpoint", dependencies=[Depends(require_any_permission("view_employees", "manage_employees"))])
    """
    def permission_checker(
        user: User = Depends(require_auth),
        db: Session = Depends(get_db)
    ) -> User:
        for perm in permission_names:
            if check_permission(db, user, perm):
                return user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied. Required one of: {', '.join(permission_names)}"
        )

    return permission_checker


def require_any_role(*role_names: str):
    """
    Dependency to require any one of multiple roles
    Usage: @router.get("/endpoint", dependencies=[Depends(require_any_role("Admin", "Manager"))])
    """
    def role_checker(
        user: User = Depends(require_auth),
        db: Session = Depends(get_db)
    ) -> User:
        for role in role_names:
            if check_role(db, user, role):
                return user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied. Required one of: {', '.join(role_names)}"
        )

    return role_checker


# Need to import get_db here to avoid circular import
from hr.db.database import get_db


# ============================================================================
# LOCATION-BASED ACCESS CONTROL
# ============================================================================

def get_user_location_ids(user: User) -> Optional[List[int]]:
    """
    Get list of location IDs the user has access to.

    Returns:
        - None if user has no restrictions (access to all locations - ADMIN)
        - List of location IDs if user has specific location assignments
        - Empty list if user has no access to any locations

    Admin users always have access to all locations (returns None).
    Non-admin users with assigned locations only see those locations.
    Non-admin users without assigned locations have NO access (empty list).
    """
    # Admins have access to everything
    if user.is_admin:
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
        location_column: The column to filter on (e.g., Employee.location_id)
        user: Current user object

    Returns:
        Filtered query or original query if user has access to all locations

    Example:
        query = db.query(Employee)
        query = filter_by_user_locations(query, Employee.location_id, current_user)
    """
    location_ids = get_user_location_ids(user)

    # If location_ids is None, user has access to all locations
    if location_ids is None:
        return query

    # Filter by assigned location IDs
    # If location_ids is empty list, this will return no results (safe default)
    return query.filter(location_column.in_(location_ids))
