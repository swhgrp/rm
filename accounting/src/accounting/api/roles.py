"""
Role management API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional

from accounting.db.database import get_db
from accounting.models.user import User
from accounting.models.role import Role
from accounting.models.area import Area
from accounting.models.permission import Permission
from accounting.schemas.role import RoleCreate, RoleUpdate, RoleResponse
from accounting.schemas.permission import PermissionResponse
from accounting.api.auth import require_admin

router = APIRouter(prefix="/api/roles", tags=["roles"])


@router.get("/", response_model=List[RoleResponse])
def list_roles(
    skip: int = 0,
    limit: int = 100,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """List all roles (admin only)"""
    query = db.query(Role)
    if not include_inactive:
        query = query.filter(Role.is_active == True)

    roles = query.offset(skip).limit(limit).all()
    return roles


@router.get("/permissions", response_model=List[PermissionResponse])
def list_permissions(
    module: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """List all available permissions (admin only)"""
    query = db.query(Permission)

    if module:
        query = query.filter(Permission.module == module)

    permissions = query.order_by(Permission.module, Permission.action).all()
    return permissions


@router.get("/{role_id}", response_model=RoleResponse)
def get_role(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Get a specific role by ID (admin only)"""
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )
    return role


@router.post("/", response_model=RoleResponse)
def create_role(
    role_data: RoleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Create a new role (admin only)"""
    # Check if role name already exists
    existing_role = db.query(Role).filter(Role.name == role_data.name).first()
    if existing_role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role name already exists"
        )

    # Create new role
    new_role = Role(
        name=role_data.name,
        description=role_data.description
    )

    # Add area assignments if provided
    if role_data.area_ids:
        areas = db.query(Area).filter(Area.id.in_(role_data.area_ids)).all()
        if len(areas) != len(role_data.area_ids):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="One or more area IDs are invalid"
            )
        new_role.areas = areas

    # Add permission assignments if provided
    if role_data.permission_ids:
        permissions = db.query(Permission).filter(Permission.id.in_(role_data.permission_ids)).all()
        if len(permissions) != len(role_data.permission_ids):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="One or more permission IDs are invalid"
            )
        new_role.permissions = permissions

    db.add(new_role)
    db.commit()
    db.refresh(new_role)

    return new_role


@router.put("/{role_id}", response_model=RoleResponse)
def update_role(
    role_id: int,
    role_data: RoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Update a role (admin only)"""
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )

    # Update fields if provided
    if role_data.name is not None:
        # Check if name already exists for another role
        existing_name = db.query(Role).filter(
            Role.name == role_data.name,
            Role.id != role_id
        ).first()
        if existing_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Role name already exists"
            )
        role.name = role_data.name

    if role_data.description is not None:
        role.description = role_data.description

    if role_data.is_active is not None:
        role.is_active = role_data.is_active

    # Update area assignments if provided
    if role_data.area_ids is not None:
        if role_data.area_ids:
            areas = db.query(Area).filter(Area.id.in_(role_data.area_ids)).all()
            if len(areas) != len(role_data.area_ids):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="One or more area IDs are invalid"
                )
            role.areas = areas
        else:
            # Empty list means no area restrictions
            role.areas = []

    # Update permission assignments if provided
    if role_data.permission_ids is not None:
        if role_data.permission_ids:
            permissions = db.query(Permission).filter(Permission.id.in_(role_data.permission_ids)).all()
            if len(permissions) != len(role_data.permission_ids):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="One or more permission IDs are invalid"
                )
            role.permissions = permissions
        else:
            # Empty list means no permissions
            role.permissions = []

    db.commit()
    db.refresh(role)

    return role


@router.delete("/{role_id}")
def delete_role(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Delete a role (admin only)"""
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )

    # Check if any users are assigned to this role
    users_count = db.query(User).filter(User.role_id == role_id).count()
    if users_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete role: {users_count} user(s) are still assigned to it"
        )

    db.delete(role)
    db.commit()

    return {"message": "Role deleted successfully"}
