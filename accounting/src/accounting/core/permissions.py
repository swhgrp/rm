"""
Permission checking helpers
"""
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from accounting.models.user import User
from accounting.models.permission import Permission


def has_permission(user: User, permission_name: str) -> bool:
    """
    Check if a user has a specific permission

    Args:
        user: The user to check
        permission_name: Permission name in format 'module:action' (e.g., 'general_ledger:view')

    Returns:
        True if user has the permission, False otherwise

    Note:
        - Admins (is_admin=True) always have all permissions
        - Users without a role have no permissions
    """
    # Admins have all permissions
    if user.is_admin:
        return True

    # Users without a role have no permissions
    if not user.role:
        return False

    # Check if the role has the permission
    role_permission_names = [p.name for p in user.role.permissions]
    return permission_name in role_permission_names


def has_any_permission(user: User, permission_names: list[str]) -> bool:
    """
    Check if a user has ANY of the specified permissions

    Args:
        user: The user to check
        permission_names: List of permission names

    Returns:
        True if user has at least one of the permissions, False otherwise
    """
    if user.is_admin:
        return True

    for perm_name in permission_names:
        if has_permission(user, perm_name):
            return True

    return False


def has_all_permissions(user: User, permission_names: list[str]) -> bool:
    """
    Check if a user has ALL of the specified permissions

    Args:
        user: The user to check
        permission_names: List of permission names

    Returns:
        True if user has all permissions, False otherwise
    """
    if user.is_admin:
        return True

    for perm_name in permission_names:
        if not has_permission(user, perm_name):
            return False

    return True


def require_permission(user: User, permission_name: str) -> User:
    """
    Require a specific permission, raise HTTPException if not granted

    Args:
        user: The user to check
        permission_name: Permission name required

    Returns:
        The user if they have the permission

    Raises:
        HTTPException: 403 if user doesn't have the permission
    """
    if not has_permission(user, permission_name):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission required: {permission_name}"
        )
    return user


def require_any_permission(user: User, permission_names: list[str]) -> User:
    """
    Require ANY of the specified permissions

    Args:
        user: The user to check
        permission_names: List of permission names

    Returns:
        The user if they have at least one permission

    Raises:
        HTTPException: 403 if user doesn't have any of the permissions
    """
    if not has_any_permission(user, permission_names):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions"
        )
    return user


def require_all_permissions(user: User, permission_names: list[str]) -> User:
    """
    Require ALL of the specified permissions

    Args:
        user: The user to check
        permission_names: List of permission names

    Returns:
        The user if they have all permissions

    Raises:
        HTTPException: 403 if user doesn't have all permissions
    """
    if not has_all_permissions(user, permission_names):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions"
        )
    return user


def has_location_access(user: User, location_id: int) -> bool:
    """
    Check if a user has access to a specific location/area

    Args:
        user: The user to check
        location_id: The area/location ID

    Returns:
        True if user has access, False otherwise

    Note:
        - Admins have access to all locations
        - Users without a role have no location access
        - If role has no area restrictions, user has access to all locations
        - Otherwise, check if location is in role's areas
    """
    # Admins have access to all locations
    if user.is_admin:
        return True

    # Users without a role have no access
    if not user.role:
        return False

    # If role has no area restrictions, user has access to all
    if not user.role.areas or len(user.role.areas) == 0:
        return True

    # Check if location is in role's allowed areas
    role_area_ids = [area.id for area in user.role.areas]
    return location_id in role_area_ids


def get_accessible_location_ids(user: User) -> list[int] | None:
    """
    Get list of location IDs the user can access

    Args:
        user: The user to check

    Returns:
        List of area IDs, or None if user has access to all locations

    Note:
        - Returns None for admins (access to all)
        - Returns None for roles with no area restrictions (access to all)
        - Returns list of area IDs for restricted roles
        - Returns empty list for users without a role
    """
    # Admins have access to all
    if user.is_admin:
        return None

    # Users without a role have no access
    if not user.role:
        return []

    # If role has no restrictions, access to all
    if not user.role.areas or len(user.role.areas) == 0:
        return None

    # Return list of accessible area IDs
    return [area.id for area in user.role.areas]


# Convenience decorators for FastAPI dependencies
def create_permission_dependency(permission_name: str):
    """
    Create a FastAPI dependency that requires a specific permission

    Usage:
        require_gl_view = create_permission_dependency('general_ledger:view')

        @router.get("/accounts")
        def list_accounts(user: User = Depends(require_gl_view)):
            ...
    """
    def dependency(user: User) -> User:
        return require_permission(user, permission_name)

    return dependency
