"""User and role management API endpoints"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID

from events.core.database import get_db
from events.core.deps import require_auth, require_role
from events.models.user import User, Role
from events.schemas.user import UserResponse, RoleResponse

router = APIRouter()


# ============= USERS =============

@router.get("/", response_model=List[UserResponse])
async def list_users(
    search: Optional[str] = None,
    department: Optional[str] = None,
    role: Optional[str] = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """
    List all users with optional filters

    - **search**: Search by email or full name
    - **department**: Filter by department
    - **role**: Filter by role code (admin, event_manager, etc.)
    - **include_inactive**: Include inactive users (default: false)
    """
    from sqlalchemy import or_
    from events.models.user import user_roles

    query = db.query(User)

    # Search filter
    if search:
        query = query.filter(
            or_(
                User.email.ilike(f"%{search}%"),
                User.full_name.ilike(f"%{search}%")
            )
        )

    # Department filter
    if department:
        query = query.filter(User.department == department)

    # Role filter
    if role:
        query = query.join(User.roles).filter(Role.code == role)

    # Active filter
    if not include_inactive:
        query = query.filter(User.is_active == True)

    users = query.order_by(User.full_name.asc()).all()
    return users


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Get user by ID"""
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return user


@router.post("/{user_id}/roles/{role_code}", response_model=UserResponse)
async def assign_role_to_user(
    user_id: UUID,
    role_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    """
    Assign a role to a user (admin only)

    - **user_id**: User UUID
    - **role_code**: Role code (admin, event_manager, dept_lead, staff, read_only)
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    role = db.query(Role).filter(Role.code == role_code).first()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role '{role_code}' not found"
        )

    # Check if user already has this role
    if role in user.roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User already has role '{role_code}'"
        )

    user.roles.append(role)
    db.commit()
    db.refresh(user)

    return user


@router.delete("/{user_id}/roles/{role_code}", response_model=UserResponse)
async def remove_role_from_user(
    user_id: UUID,
    role_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    """
    Remove a role from a user (admin only)

    - **user_id**: User UUID
    - **role_code**: Role code to remove
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    role = db.query(Role).filter(Role.code == role_code).first()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role '{role_code}' not found"
        )

    # Check if user has this role
    if role not in user.roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User does not have role '{role_code}'"
        )

    # Prevent removing last role
    if len(user.roles) == 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove user's last role. Assign a different role first."
        )

    user.roles.remove(role)
    db.commit()
    db.refresh(user)

    return user


@router.patch("/{user_id}/deactivate", response_model=UserResponse)
async def deactivate_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    """
    Deactivate a user (admin only)

    User will not be able to log in or perform any actions.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Prevent deactivating self
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate yourself"
        )

    user.is_active = False
    db.commit()
    db.refresh(user)

    return user


@router.patch("/{user_id}/activate", response_model=UserResponse)
async def activate_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    """
    Activate a user (admin only)

    User will be able to log in and perform actions according to their roles.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    user.is_active = True
    db.commit()
    db.refresh(user)

    return user


# ============= ROLES =============

@router.get("/roles/", response_model=List[RoleResponse])
async def list_roles(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """List all available roles"""
    roles = db.query(Role).order_by(Role.name.asc()).all()
    return roles


@router.get("/roles/{role_code}/users", response_model=List[UserResponse])
async def list_users_by_role(
    role_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """
    List all users with a specific role

    - **role_code**: Role code (admin, event_manager, dept_lead, staff, read_only)
    """
    role = db.query(Role).filter(Role.code == role_code).first()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role '{role_code}' not found"
        )

    return role.users
