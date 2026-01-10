"""User permission management router for Food Safety Service"""
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from food_safety.database import get_db
from food_safety.models import UserPermission, UserRole
from food_safety.schemas import (
    UserPermissionCreate, UserPermissionUpdate, UserPermissionResponse
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", response_model=List[UserPermissionResponse])
async def list_users(
    role: Optional[UserRole] = Query(None),
    is_active: Optional[bool] = Query(True),
    db: AsyncSession = Depends(get_db)
):
    """List all users with food safety permissions"""
    query = select(UserPermission)

    if role:
        query = query.where(UserPermission.role == role)
    if is_active is not None:
        query = query.where(UserPermission.is_active == is_active)

    query = query.order_by(UserPermission.employee_name)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{hr_user_id}", response_model=UserPermissionResponse)
async def get_user(
    hr_user_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get user permissions by HR user ID"""
    query = select(UserPermission).where(UserPermission.hr_user_id == hr_user_id)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user


@router.post("", response_model=UserPermissionResponse, status_code=201)
async def create_user_permission(
    data: UserPermissionCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create user permission entry"""
    # Check if user already has permissions
    existing_query = select(UserPermission).where(UserPermission.hr_user_id == data.hr_user_id)
    result = await db.execute(existing_query)
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="User already has permissions assigned")

    user_perm = UserPermission(**data.model_dump())
    db.add(user_perm)
    await db.commit()
    await db.refresh(user_perm)

    logger.info(f"Created user permission for HR user {data.hr_user_id} with role {data.role}")
    return user_perm


@router.put("/{hr_user_id}", response_model=UserPermissionResponse)
async def update_user_permission(
    hr_user_id: int,
    data: UserPermissionUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update user permissions"""
    query = select(UserPermission).where(UserPermission.hr_user_id == hr_user_id)
    result = await db.execute(query)
    user_perm = result.scalar_one_or_none()

    if not user_perm:
        raise HTTPException(status_code=404, detail="User not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user_perm, field, value)

    await db.commit()
    await db.refresh(user_perm)

    logger.info(f"Updated user permission for HR user {hr_user_id}")
    return user_perm


@router.delete("/{hr_user_id}")
async def delete_user_permission(
    hr_user_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Remove user from food safety system"""
    query = select(UserPermission).where(UserPermission.hr_user_id == hr_user_id)
    result = await db.execute(query)
    user_perm = result.scalar_one_or_none()

    if not user_perm:
        raise HTTPException(status_code=404, detail="User not found")

    await db.delete(user_perm)
    await db.commit()

    logger.info(f"Deleted user permission for HR user {hr_user_id}")
    return {"message": "User permission deleted"}
