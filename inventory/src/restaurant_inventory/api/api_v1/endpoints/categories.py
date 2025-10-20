"""
Category API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from restaurant_inventory.core.deps import get_db, get_current_user, require_manager_or_admin
from restaurant_inventory.models.user import User
from restaurant_inventory.models.category import Category

router = APIRouter()


# Pydantic schemas
class CategoryCreate(BaseModel):
    name: str
    description: Optional[str] = None
    display_order: int = 0
    parent_id: Optional[int] = None  # None = main category, otherwise subcategory


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    display_order: Optional[int] = None
    parent_id: Optional[int] = None
    is_active: Optional[bool] = None


class SubcategoryResponse(BaseModel):
    """Simple response for subcategories to avoid recursion"""
    id: int
    name: str
    description: Optional[str] = None
    display_order: int
    is_active: bool
    parent_id: Optional[int] = None

    class Config:
        from_attributes = True


class CategoryResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    display_order: int
    is_active: bool
    parent_id: Optional[int] = None
    subcategories: List['SubcategoryResponse'] = []

    class Config:
        from_attributes = True


@router.get("/", response_model=List[CategoryResponse])
async def get_categories(
    include_inactive: bool = False,
    only_main: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all categories with subcategories.
    - include_inactive: Include inactive categories
    - only_main: Only return main categories (parent_id is NULL)
    """
    from sqlalchemy.orm import joinedload

    query = db.query(Category).options(joinedload(Category.subcategories))

    if not include_inactive:
        query = query.filter(Category.is_active == True)

    # Only return main categories (categories without a parent)
    # Subcategories will be included via the relationship
    query = query.filter(Category.parent_id == None)

    return query.order_by(Category.display_order, Category.name).all()


@router.get("/{category_id}", response_model=CategoryResponse)
async def get_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific category"""
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found"
        )
    return category


@router.post("/", response_model=CategoryResponse)
async def create_category(
    category_data: CategoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Create a new category or subcategory"""
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Creating category: {category_data.model_dump()}")

    # Check if category name already exists
    existing = db.query(Category).filter(Category.name == category_data.name).first()
    if existing:
        logger.warning(f"Duplicate category name attempted: {category_data.name}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Category with this name already exists"
        )

    # If parent_id is provided, verify it exists
    if category_data.parent_id:
        parent = db.query(Category).filter(Category.id == category_data.parent_id).first()
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Parent category not found"
            )
        # Don't allow subcategories of subcategories (only 2 levels)
        if parent.parent_id is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot create subcategory of a subcategory. Only 2 levels allowed."
            )

    category = Category(
        name=category_data.name,
        description=category_data.description,
        display_order=category_data.display_order,
        parent_id=category_data.parent_id,
        is_active=True
    )

    db.add(category)
    db.commit()
    db.refresh(category)

    return category


@router.put("/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: int,
    category_data: CategoryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Update a category"""
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found"
        )

    # Check name uniqueness if changing name
    if category_data.name and category_data.name != category.name:
        existing = db.query(Category).filter(Category.name == category_data.name).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Category with this name already exists"
            )
        category.name = category_data.name

    if category_data.description is not None:
        category.description = category_data.description
    if category_data.display_order is not None:
        category.display_order = category_data.display_order
    if category_data.is_active is not None:
        category.is_active = category_data.is_active

    # Handle parent_id changes
    if category_data.parent_id is not None:
        if category_data.parent_id == category_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Category cannot be its own parent"
            )
        # Verify parent exists if not null
        if category_data.parent_id:
            parent = db.query(Category).filter(Category.id == category_data.parent_id).first()
            if not parent:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Parent category not found"
                )
            # Don't allow subcategories of subcategories
            if parent.parent_id is not None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot create subcategory of a subcategory. Only 2 levels allowed."
                )
        category.parent_id = category_data.parent_id

    db.commit()
    db.refresh(category)

    return category


@router.delete("/{category_id}")
async def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Delete a category (hard delete)"""
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found"
        )

    # Hard delete - subcategories will be deleted automatically due to CASCADE
    db.delete(category)
    db.commit()

    return {"success": True, "message": "Category deleted"}
