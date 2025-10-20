"""
Role and Permission Management API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from typing import List

from hr.db.database import get_db
from hr.models.user import User
from hr.models.role import Role
from hr.models.permission import Permission
from hr.models.user_role import UserRole
from hr.models.role_permission import RolePermission
from hr.schemas.role import (
    RoleCreate, RoleUpdate, RoleResponse, RoleWithPermissions,
    PermissionResponse, UserRoleAssignment, UserRoleResponse
)
from hr.api.auth import require_admin, require_auth
from hr.core.authorization import get_user_roles, get_user_permissions


router = APIRouter(prefix="/api/roles", tags=["Roles & Permissions"])


@router.get("/", response_model=List[RoleResponse])
def list_roles(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """List all roles (Admin only)"""
    roles = db.query(Role).offset(skip).limit(limit).all()
    return roles


@router.get("/{role_id}", response_model=RoleWithPermissions)
def get_role(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Get role by ID with its permissions (Admin only)"""
    role = db.query(Role).filter(Role.id == role_id).first()

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )

    # Get permissions for this role
    role_perms = db.query(RolePermission).filter(
        RolePermission.role_id == role_id
    ).all()

    permission_ids = [rp.permission_id for rp in role_perms]
    permissions = db.query(Permission).filter(Permission.id.in_(permission_ids)).all()

    # Convert to response format
    role_data = RoleWithPermissions.model_validate(role)
    role_data.permissions = [PermissionResponse.model_validate(p) for p in permissions]

    return role_data


@router.post("/", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
def create_role(
    role_data: RoleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Create a new role (Admin only)"""
    # Check if role name already exists
    existing_role = db.query(Role).filter(Role.name == role_data.name).first()
    if existing_role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role with this name already exists"
        )

    # Create role
    new_role = Role(
        name=role_data.name,
        description=role_data.description,
        is_active=True
    )
    db.add(new_role)
    db.flush()

    # Add permissions if provided
    if role_data.permission_ids:
        for perm_id in role_data.permission_ids:
            # Verify permission exists
            perm = db.query(Permission).filter(Permission.id == perm_id).first()
            if not perm:
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Permission with ID {perm_id} not found"
                )

            role_perm = RolePermission(
                role_id=new_role.id,
                permission_id=perm_id
            )
            db.add(role_perm)

    db.commit()
    db.refresh(new_role)

    return RoleResponse.model_validate(new_role)


@router.put("/{role_id}", response_model=RoleResponse)
def update_role(
    role_id: int,
    role_data: RoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Update a role (Admin only)"""
    role = db.query(Role).filter(Role.id == role_id).first()

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )

    # Update fields if provided
    if role_data.name is not None:
        # Check if new name conflicts
        existing = db.query(Role).filter(
            Role.name == role_data.name,
            Role.id != role_id
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Role with this name already exists"
            )
        role.name = role_data.name

    if role_data.description is not None:
        role.description = role_data.description

    if role_data.is_active is not None:
        role.is_active = role_data.is_active

    db.commit()
    db.refresh(role)

    return RoleResponse.model_validate(role)


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Delete a role (Admin only)"""
    role = db.query(Role).filter(Role.id == role_id).first()

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )

    # Check if role is assigned to any users
    user_count = db.query(UserRole).filter(UserRole.role_id == role_id).count()
    if user_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete role. It is assigned to {user_count} user(s)"
        )

    db.delete(role)
    db.commit()

    return None


@router.get("/permissions/all", response_model=List[PermissionResponse])
def list_all_permissions(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """List all available permissions (Admin only)"""
    permissions = db.query(Permission).all()
    return permissions


@router.post("/assign", response_model=UserRoleResponse)
def assign_role_to_user(
    assignment: UserRoleAssignment,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Assign a role to a user (Admin only)"""
    # Verify user exists
    user = db.query(User).filter(User.id == assignment.user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Verify role exists
    role = db.query(Role).filter(Role.id == assignment.role_id).first()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )

    # Check if already assigned
    existing = db.query(UserRole).filter(
        UserRole.user_id == assignment.user_id,
        UserRole.role_id == assignment.role_id
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already has this role"
        )

    # Create assignment
    user_role = UserRole(
        user_id=assignment.user_id,
        role_id=assignment.role_id,
        assigned_by=current_user.id
    )
    db.add(user_role)
    db.commit()
    db.refresh(user_role)

    # Create response
    response = UserRoleResponse(
        id=user_role.id,
        user_id=user_role.user_id,
        role_id=user_role.role_id,
        role_name=role.name,
        assigned_at=user_role.assigned_at,
        assigned_by=user_role.assigned_by
    )

    return response


@router.delete("/assign/{user_role_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_role_from_user(
    user_role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Remove a role assignment from a user (Admin only)"""
    user_role = db.query(UserRole).filter(UserRole.id == user_role_id).first()

    if not user_role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role assignment not found"
        )

    db.delete(user_role)
    db.commit()

    return None


@router.get("/user/{user_id}", response_model=List[UserRoleResponse])
def get_user_roles_endpoint(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Get all roles assigned to a user (Admin only)"""
    # Verify user exists
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Get user roles
    user_roles = db.query(UserRole).filter(UserRole.user_id == user_id).all()

    # Build response
    response = []
    for ur in user_roles:
        role = db.query(Role).filter(Role.id == ur.role_id).first()
        if role:
            response.append(UserRoleResponse(
                id=ur.id,
                user_id=ur.user_id,
                role_id=ur.role_id,
                role_name=role.name,
                assigned_at=ur.assigned_at,
                assigned_by=ur.assigned_by
            ))

    return response


@router.get("/me/roles")
def get_my_roles(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Get current user's roles and permissions"""
    roles = get_user_roles(db, current_user)
    permissions = get_user_permissions(db, current_user)

    return {
        "user_id": current_user.id,
        "username": current_user.username,
        "is_admin": current_user.is_admin,
        "roles": list(roles),
        "permissions": list(permissions)
    }
