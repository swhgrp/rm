"""
Dependency functions for authentication and authorization in Events system
"""

from typing import Generator, Optional
from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from events.core.database import get_db
from events.models.user import User
from events.core.security import verify_jwt_token

def get_current_user(
    request: Request,
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    Get current authenticated user from JWT cookie (Portal SSO)

    Returns None if not authenticated (allows optional auth)
    Raises HTTPException if token is invalid
    """
    # Get JWT token from cookie (set by Portal)
    # Portal uses "portal_session" as cookie name
    token = request.cookies.get("portal_session")

    if not token:
        return None

    # Remove "Bearer " prefix if present
    if token.startswith("Bearer "):
        token = token[7:]

    # Verify JWT token
    payload = verify_jwt_token(token)
    if not payload:
        return None

    # Extract user info from token
    username = payload.get("sub")
    email = payload.get("email")
    full_name = payload.get("full_name")

    if not email:
        # Fallback: use username as email if email not in token
        email = username if username else None

    if not email:
        return None

    # Find or create user in Events database (JIT provisioning)
    # Events uses email as primary identifier, not username
    user = db.query(User).filter(User.email == email).first()

    if not user:
        # JIT provisioning: Create user from Portal token data
        user = User(
            email=email,
            full_name=full_name or username or email,
            is_active=True,
            source='portal'
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # Assign default role (staff) for new users
        from events.models.user import Role
        default_role = db.query(Role).filter(Role.code == "staff").first()
        if default_role:
            user.roles.append(default_role)
            db.commit()

    return user


def require_auth(
    request: Request,
    db: Session = Depends(get_db)
) -> User:
    """
    Require authentication - raise exception if not logged in
    Use this dependency on protected endpoints
    """
    user = get_current_user(request, db)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated - please log in via Portal"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )

    return user


def require_admin(
    user: User = Depends(require_auth)
) -> User:
    """Require admin role"""
    user_roles = [role.code for role in user.roles]

    if "admin" not in user_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    return user


def require_event_manager(
    user: User = Depends(require_auth)
) -> User:
    """Require event manager or admin role"""
    user_roles = [role.code for role in user.roles]

    if "admin" not in user_roles and "event_manager" not in user_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Event Manager or Admin access required"
        )

    return user


def check_permission(user: User, action: str, resource: str) -> bool:
    """
    Check if user has permission for action on resource

    Args:
        user: The user to check
        action: Action to perform (create, read, update, delete)
        resource: Resource type (event, task, document, financials)

    Returns:
        bool: True if user has permission
    """
    user_roles = [role.code for role in user.roles]

    # Admin has all permissions
    if "admin" in user_roles:
        return True

    # Event managers can do most things
    if "event_manager" in user_roles:
        return action != "delete" or resource != "user"

    # Department leads can manage their own department
    if "dept_lead" in user_roles:
        if resource == "task" and action in ["read", "update"]:
            return True
        if resource == "event" and action == "read":
            return True
        if resource == "financials":
            return action == "read"  # Read totals only

    # Staff can only read and update their assigned tasks
    if "staff" in user_roles:
        if resource == "task" and action in ["read", "update"]:
            return True
        if resource == "event" and action == "read":
            return True  # But will filter to assigned events only

    # Read-only role
    if "read_only" in user_roles:
        return action == "read" and resource != "financials"

    return False


def require_role(*allowed_roles: str):
    """
    Dependency factory to require specific roles

    Usage:
        @router.post("/events")
        async def create_event(
            user: User = Depends(require_role("admin", "event_manager"))
        ):
            ...
    """
    def role_checker(user: User = Depends(require_auth)) -> User:
        user_roles = [role.code for role in user.roles]

        if not any(role in user_roles for role in allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of these roles: {', '.join(allowed_roles)}"
            )

        return user

    return role_checker


def require_permission(action: str, resource: str):
    """
    Dependency factory to require specific permission

    Usage:
        @router.delete("/events/{id}")
        async def delete_event(
            event_id: int,
            user: User = Depends(require_permission("delete", "event"))
        ):
            ...
    """
    def permission_checker(user: User = Depends(require_auth)) -> User:
        if not check_permission(user, action, resource):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: Cannot {action} {resource}"
            )

        return user

    return permission_checker
