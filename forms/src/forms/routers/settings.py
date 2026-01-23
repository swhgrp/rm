"""Settings API routes for Forms Service"""
import logging
import httpx
from typing import Optional, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from pydantic import BaseModel

from forms.database import get_db
from forms.auth import verify_portal_session
from forms.models import Category, UserPermission
from forms.config import settings as app_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["Settings"])


# ==================== Schemas ====================

class CategoryCreate(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    color: Optional[str] = "#455A64"
    icon: Optional[str] = "bi-folder"
    is_active: bool = True


class CategoryUpdate(CategoryCreate):
    pass


class CategoryResponse(BaseModel):
    id: str
    name: str
    slug: str
    description: Optional[str]
    color: Optional[str]
    icon: Optional[str]
    sort_order: int
    is_active: bool

    class Config:
        from_attributes = True


class UserPermissionCreate(BaseModel):
    employee_id: int
    can_create_templates: bool = False
    can_edit_templates: bool = False
    can_delete_templates: bool = False
    can_view_all_submissions: bool = False
    can_delete_submissions: bool = False
    can_export_submissions: bool = True
    can_manage_categories: bool = False
    can_manage_users: bool = False
    can_view_audit_logs: bool = False
    allowed_locations: Optional[List[int]] = None


class EmployeeSearchResult(BaseModel):
    id: int
    name: str
    email: Optional[str]
    employee_number: Optional[str]


# ==================== Helper Functions ====================

async def get_hr_employees(query: str) -> List[dict]:
    """Search employees from HR system."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"http://hr-service:8000/api/employees/search",
                params={"q": query, "limit": 10},
                timeout=5.0
            )
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        logger.error(f"Error fetching employees from HR: {e}")

    # Fallback: return empty list if HR unavailable
    return []


async def get_employee_by_id(employee_id: int) -> Optional[dict]:
    """Get employee details from HR system."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"http://hr-service:8000/api/employees/{employee_id}",
                timeout=5.0
            )
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        logger.error(f"Error fetching employee {employee_id} from HR: {e}")
    return None


# ==================== Category Endpoints ====================

@router.get("/categories", response_model=List[CategoryResponse])
async def list_categories(
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db)
):
    """List all categories."""
    query = select(Category).order_by(Category.sort_order, Category.name)
    if not include_inactive:
        query = query.where(Category.is_active == True)

    result = await db.execute(query)
    categories = result.scalars().all()

    return [
        CategoryResponse(
            id=str(c.id),
            name=c.name,
            slug=c.slug,
            description=c.description,
            color=c.color,
            icon=c.icon,
            sort_order=c.sort_order or 0,
            is_active=c.is_active
        )
        for c in categories
    ]


@router.get("/categories/{category_id}", response_model=CategoryResponse)
async def get_category(
    category_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific category."""
    try:
        uuid_id = UUID(category_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Category not found")

    result = await db.execute(
        select(Category).where(Category.id == uuid_id)
    )
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    return CategoryResponse(
        id=str(category.id),
        name=category.name,
        slug=category.slug,
        description=category.description,
        color=category.color,
        icon=category.icon,
        sort_order=category.sort_order or 0,
        is_active=category.is_active
    )


@router.post("/categories", response_model=CategoryResponse)
async def create_category(
    data: CategoryCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new category."""
    # Check for duplicate slug
    existing = await db.execute(
        select(Category).where(Category.slug == data.slug)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Category with this slug already exists")

    # Get max sort order
    max_order = await db.execute(
        select(Category.sort_order).order_by(Category.sort_order.desc()).limit(1)
    )
    max_val = max_order.scalar() or 0

    category = Category(
        name=data.name,
        slug=data.slug,
        description=data.description,
        color=data.color,
        icon=data.icon,
        sort_order=max_val + 1,
        is_active=data.is_active
    )
    db.add(category)
    await db.commit()
    await db.refresh(category)

    return CategoryResponse(
        id=str(category.id),
        name=category.name,
        slug=category.slug,
        description=category.description,
        color=category.color,
        icon=category.icon,
        sort_order=category.sort_order or 0,
        is_active=category.is_active
    )


@router.put("/categories/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: str,
    data: CategoryUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a category."""
    try:
        uuid_id = UUID(category_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Category not found")

    result = await db.execute(
        select(Category).where(Category.id == uuid_id)
    )
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    # Check for duplicate slug if changed
    if data.slug != category.slug:
        existing = await db.execute(
            select(Category).where(Category.slug == data.slug, Category.id != uuid_id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Category with this slug already exists")

    category.name = data.name
    category.slug = data.slug
    category.description = data.description
    category.color = data.color
    category.icon = data.icon
    category.is_active = data.is_active

    await db.commit()
    await db.refresh(category)

    return CategoryResponse(
        id=str(category.id),
        name=category.name,
        slug=category.slug,
        description=category.description,
        color=category.color,
        icon=category.icon,
        sort_order=category.sort_order or 0,
        is_active=category.is_active
    )


@router.delete("/categories/{category_id}")
async def delete_category(
    category_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Delete a category."""
    try:
        uuid_id = UUID(category_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Category not found")

    result = await db.execute(
        select(Category).where(Category.id == uuid_id)
    )
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    # TODO: Check if category is in use by any templates

    await db.delete(category)
    await db.commit()

    return {"status": "deleted"}


# ==================== User Permission Endpoints ====================

@router.get("/search-employees")
async def search_employees(
    q: str = Query(..., min_length=2)
):
    """Search employees from HR system."""
    employees = await get_hr_employees(q)
    return [
        EmployeeSearchResult(
            id=e.get("id"),
            name=f"{e.get('first_name', '')} {e.get('last_name', '')}".strip(),
            email=e.get("email"),
            employee_number=e.get("employee_number")
        )
        for e in employees
    ]


@router.get("/users/{employee_id}/permissions")
async def get_user_permissions(
    employee_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get permissions for a specific user."""
    result = await db.execute(
        select(UserPermission).where(UserPermission.employee_id == employee_id)
    )
    perm = result.scalar_one_or_none()

    # Get employee info from HR
    employee = await get_employee_by_id(employee_id)
    name = "Unknown"
    if employee:
        name = f"{employee.get('first_name', '')} {employee.get('last_name', '')}".strip()

    if not perm:
        # Return default permissions
        return {
            "employee_id": employee_id,
            "name": name,
            "can_create_templates": False,
            "can_edit_templates": False,
            "can_delete_templates": False,
            "can_view_all_submissions": False,
            "can_delete_submissions": False,
            "can_export_submissions": True,
            "can_manage_categories": False,
            "can_manage_users": False,
            "can_view_audit_logs": False
        }

    return {
        "employee_id": perm.employee_id,
        "name": name,
        "can_create_templates": perm.can_create_templates,
        "can_edit_templates": perm.can_edit_templates,
        "can_delete_templates": perm.can_delete_templates,
        "can_view_all_submissions": perm.can_view_all_submissions,
        "can_delete_submissions": perm.can_delete_submissions,
        "can_export_submissions": perm.can_export_submissions,
        "can_manage_categories": perm.can_manage_categories,
        "can_manage_users": perm.can_manage_users,
        "can_view_audit_logs": perm.can_view_audit_logs
    }


@router.post("/users/permissions")
async def save_user_permissions(
    data: UserPermissionCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create or update user permissions."""
    # Check if permissions already exist for this user
    result = await db.execute(
        select(UserPermission).where(UserPermission.employee_id == data.employee_id)
    )
    perm = result.scalar_one_or_none()

    if perm:
        # Update existing
        perm.can_create_templates = data.can_create_templates
        perm.can_edit_templates = data.can_edit_templates
        perm.can_delete_templates = data.can_delete_templates
        perm.can_view_all_submissions = data.can_view_all_submissions
        perm.can_delete_submissions = data.can_delete_submissions
        perm.can_export_submissions = data.can_export_submissions
        perm.can_manage_categories = data.can_manage_categories
        perm.can_manage_users = data.can_manage_users
        perm.can_view_audit_logs = data.can_view_audit_logs
        perm.allowed_locations = data.allowed_locations
    else:
        # Create new
        perm = UserPermission(
            employee_id=data.employee_id,
            can_create_templates=data.can_create_templates,
            can_edit_templates=data.can_edit_templates,
            can_delete_templates=data.can_delete_templates,
            can_view_all_submissions=data.can_view_all_submissions,
            can_delete_submissions=data.can_delete_submissions,
            can_export_submissions=data.can_export_submissions,
            can_manage_categories=data.can_manage_categories,
            can_manage_users=data.can_manage_users,
            can_view_audit_logs=data.can_view_audit_logs,
            allowed_locations=data.allowed_locations
        )
        db.add(perm)

    await db.commit()
    await db.refresh(perm)

    return {"status": "saved", "employee_id": perm.employee_id}


@router.delete("/users/{employee_id}/permissions")
async def delete_user_permissions(
    employee_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Remove custom permissions for a user (reverts to default)."""
    await db.execute(
        delete(UserPermission).where(UserPermission.employee_id == employee_id)
    )
    await db.commit()
    return {"status": "deleted"}
