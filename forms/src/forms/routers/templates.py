"""Form Templates API Router"""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from forms.database import get_db
from forms.auth import get_current_user, require_admin
from forms.models import FormTemplate, FormCategory
from forms.schemas import (
    FormTemplateCreate, FormTemplateUpdate, FormTemplateResponse,
    FormTemplateSummary, PaginatedResponse
)

router = APIRouter()


@router.get("/", response_model=List[FormTemplateSummary])
async def list_templates(
    category: Optional[FormCategory] = None,
    active_only: bool = True,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """List all form templates."""
    query = select(FormTemplate)

    if active_only:
        query = query.where(FormTemplate.is_active == True)

    if category:
        query = query.where(FormTemplate.category == category)

    query = query.order_by(FormTemplate.name)

    result = await db.execute(query)
    templates = result.scalars().all()

    return templates


@router.get("/{template_id}", response_model=FormTemplateResponse)
async def get_template(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Get a form template with full schema."""
    result = await db.execute(
        select(FormTemplate).where(FormTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    return template


@router.get("/slug/{slug}", response_model=FormTemplateResponse)
async def get_template_by_slug(
    slug: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Get a form template by slug."""
    result = await db.execute(
        select(FormTemplate).where(FormTemplate.slug == slug, FormTemplate.is_active == True)
    )
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    return template


@router.post("/", response_model=FormTemplateResponse)
async def create_template(
    template_data: FormTemplateCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_admin)
):
    """Create a new form template (admin only)."""
    # Check for duplicate slug
    existing = await db.execute(
        select(FormTemplate).where(FormTemplate.slug == template_data.slug)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Template with this slug already exists")

    template = FormTemplate(
        **template_data.model_dump(),
        created_by=user.get("id"),
        updated_by=user.get("id")
    )

    db.add(template)
    await db.commit()
    await db.refresh(template)

    return template


@router.put("/{template_id}", response_model=FormTemplateResponse)
async def update_template(
    template_id: UUID,
    template_data: FormTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_admin)
):
    """Update a form template (creates new version if schema changed)."""
    result = await db.execute(
        select(FormTemplate).where(FormTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    update_data = template_data.model_dump(exclude_unset=True)

    # If schema is being updated, increment version
    if "schema" in update_data and update_data["schema"] != template.schema:
        template.version += 1

    for key, value in update_data.items():
        setattr(template, key, value)

    template.updated_by = user.get("id")

    await db.commit()
    await db.refresh(template)

    return template


@router.delete("/{template_id}")
async def delete_template(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_admin)
):
    """Soft delete a template (set is_active=False)."""
    result = await db.execute(
        select(FormTemplate).where(FormTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    template.is_active = False
    template.updated_by = user.get("id")

    await db.commit()

    return {"message": "Template deactivated"}


@router.post("/{template_id}/duplicate", response_model=FormTemplateResponse)
async def duplicate_template(
    template_id: UUID,
    new_slug: str = Query(..., description="Slug for the new template"),
    new_name: Optional[str] = Query(None, description="Name for the new template"),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_admin)
):
    """Duplicate a template with a new slug."""
    result = await db.execute(
        select(FormTemplate).where(FormTemplate.id == template_id)
    )
    original = result.scalar_one_or_none()

    if not original:
        raise HTTPException(status_code=404, detail="Template not found")

    # Check for duplicate slug
    existing = await db.execute(
        select(FormTemplate).where(FormTemplate.slug == new_slug)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Template with this slug already exists")

    new_template = FormTemplate(
        name=new_name or f"{original.name} (Copy)",
        slug=new_slug,
        category=original.category,
        description=original.description,
        schema=original.schema,
        ui_schema=original.ui_schema,
        requires_signature=original.requires_signature,
        requires_manager_signature=original.requires_manager_signature,
        retention_days=original.retention_days,
        workflow_id=original.workflow_id,
        version=1,
        is_active=True,
        created_by=user.get("id"),
        updated_by=user.get("id")
    )

    db.add(new_template)
    await db.commit()
    await db.refresh(new_template)

    return new_template
