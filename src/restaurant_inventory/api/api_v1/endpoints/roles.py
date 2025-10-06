"""
Role management endpoints
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from restaurant_inventory.db.database import get_db
from restaurant_inventory.models.role import Role
from restaurant_inventory.schemas.role import Role as RoleSchema, RoleCreate, RoleUpdate

router = APIRouter()

@router.get("/", response_model=List[RoleSchema])
def get_roles(db: Session = Depends(get_db)):
    """Get all roles"""
    return db.query(Role).all()

@router.get("/{role_id}", response_model=RoleSchema)
def get_role(role_id: int, db: Session = Depends(get_db)):
    """Get a specific role"""
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    return role

@router.post("/", response_model=RoleSchema)
def create_role(role_data: RoleCreate, db: Session = Depends(get_db)):
    """Create a new role"""
    # Check if role name already exists
    existing = db.query(Role).filter(Role.name == role_data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Role name already exists")

    role = Role(**role_data.model_dump())
    db.add(role)
    db.commit()
    db.refresh(role)
    return role

@router.put("/{role_id}", response_model=RoleSchema)
def update_role(role_id: int, role_data: RoleUpdate, db: Session = Depends(get_db)):
    """Update a role"""
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    # For system roles, only allow updating permissions and description, not the name
    if role.is_system:
        if role_data.name and role_data.name != role.name:
            raise HTTPException(status_code=400, detail="Cannot change the name of system roles")
        # Allow updating permissions and description for system roles
        if role_data.permissions is not None:
            role.permissions = role_data.permissions
        if role_data.description is not None:
            role.description = role_data.description
    else:
        # For custom roles, check if new name conflicts with existing role
        if role_data.name and role_data.name != role.name:
            existing = db.query(Role).filter(Role.name == role_data.name).first()
            if existing:
                raise HTTPException(status_code=400, detail="Role name already exists")

        # Update all fields for custom roles
        update_data = role_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(role, field, value)

    db.commit()
    db.refresh(role)
    return role

@router.delete("/{role_id}")
def delete_role(role_id: int, db: Session = Depends(get_db)):
    """Delete a role"""
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    if role.is_system:
        raise HTTPException(status_code=400, detail="Cannot delete system roles")

    # Check if any users have this role
    from restaurant_inventory.models.user import User
    users_with_role = db.query(User).filter(User.role == role.name).count()
    if users_with_role > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete role: {users_with_role} user(s) currently assigned to this role"
        )

    db.delete(role)
    db.commit()
    return {"message": "Role deleted successfully"}
