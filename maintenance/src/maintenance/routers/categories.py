"""Equipment categories router for Maintenance Service"""
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from maintenance.database import get_db
from maintenance.models import EquipmentCategory
from maintenance.schemas import (
    EquipmentCategoryCreate, EquipmentCategoryUpdate,
    EquipmentCategoryResponse, EquipmentCategoryWithChildren
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", response_model=List[EquipmentCategoryResponse])
async def list_categories(
    parent_id: Optional[int] = None,
    include_children: bool = False,
    db: AsyncSession = Depends(get_db)
):
    """List equipment categories"""
    if include_children and parent_id is None:
        # Get root categories with children
        query = (
            select(EquipmentCategory)
            .where(EquipmentCategory.parent_id == None)
            .options(selectinload(EquipmentCategory.subcategories))
            .order_by(EquipmentCategory.name)
        )
    else:
        query = select(EquipmentCategory)
        if parent_id is not None:
            query = query.where(EquipmentCategory.parent_id == parent_id)
        else:
            query = query.where(EquipmentCategory.parent_id == None)
        query = query.order_by(EquipmentCategory.name)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/tree", response_model=List[EquipmentCategoryWithChildren])
async def get_category_tree(db: AsyncSession = Depends(get_db)):
    """Get full category tree with nested children"""
    # Get all categories
    query = select(EquipmentCategory).order_by(EquipmentCategory.name)
    result = await db.execute(query)
    all_categories = result.scalars().all()

    # Build tree
    category_map = {cat.id: cat for cat in all_categories}
    root_categories = []

    for cat in all_categories:
        if cat.parent_id is None:
            root_categories.append(cat)

    def build_tree(category):
        children = [c for c in all_categories if c.parent_id == category.id]
        return EquipmentCategoryWithChildren(
            id=category.id,
            name=category.name,
            description=category.description,
            parent_id=category.parent_id,
            created_at=category.created_at,
            updated_at=category.updated_at,
            subcategories=[build_tree(child) for child in children]
        )

    return [build_tree(cat) for cat in root_categories]


@router.get("/{category_id}", response_model=EquipmentCategoryResponse)
async def get_category(category_id: int, db: AsyncSession = Depends(get_db)):
    """Get category by ID"""
    query = select(EquipmentCategory).where(EquipmentCategory.id == category_id)
    result = await db.execute(query)
    category = result.scalar_one_or_none()

    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    return category


@router.post("", response_model=EquipmentCategoryResponse, status_code=201)
async def create_category(
    category_data: EquipmentCategoryCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create new equipment category"""
    # Verify parent exists if specified
    if category_data.parent_id:
        parent_query = select(EquipmentCategory.id).where(
            EquipmentCategory.id == category_data.parent_id
        )
        result = await db.execute(parent_query)
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Parent category not found")

    category = EquipmentCategory(**category_data.model_dump())
    db.add(category)
    await db.commit()
    await db.refresh(category)

    logger.info(f"Created category: {category.name} (ID: {category.id})")
    return category


@router.put("/{category_id}", response_model=EquipmentCategoryResponse)
async def update_category(
    category_id: int,
    category_data: EquipmentCategoryUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update equipment category"""
    query = select(EquipmentCategory).where(EquipmentCategory.id == category_id)
    result = await db.execute(query)
    category = result.scalar_one_or_none()

    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    update_data = category_data.model_dump(exclude_unset=True)

    # Prevent circular parent reference
    if "parent_id" in update_data:
        if update_data["parent_id"] == category_id:
            raise HTTPException(status_code=400, detail="Category cannot be its own parent")

    for field, value in update_data.items():
        setattr(category, field, value)

    await db.commit()
    await db.refresh(category)

    logger.info(f"Updated category: {category.name} (ID: {category.id})")
    return category


@router.delete("/{category_id}", status_code=204)
async def delete_category(category_id: int, db: AsyncSession = Depends(get_db)):
    """Delete equipment category"""
    query = select(EquipmentCategory).where(EquipmentCategory.id == category_id)
    result = await db.execute(query)
    category = result.scalar_one_or_none()

    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    # Check for subcategories
    sub_query = select(EquipmentCategory.id).where(
        EquipmentCategory.parent_id == category_id
    )
    result = await db.execute(sub_query)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="Cannot delete category with subcategories"
        )

    await db.delete(category)
    await db.commit()

    logger.info(f"Deleted category: {category.name} (ID: {category_id})")
