"""Checklist management router for Food Safety Service"""
import logging
from datetime import date, datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
def get_now(): return datetime.now(_ET)

from food_safety.database import get_db
from food_safety.models import (
    ChecklistTemplate, ChecklistItem, ChecklistSubmission,
    ChecklistResponse, ManagerSignoff, ChecklistType, ChecklistStatus,
    Location
)
from food_safety.schemas import (
    ChecklistTemplateCreate, ChecklistTemplateUpdate, ChecklistTemplateResponse,
    ChecklistTemplateWithItems, ChecklistItemCreate, ChecklistItemResponse,
    ChecklistSubmissionCreate, ChecklistSubmissionComplete, ChecklistSubmissionResponse,
    ChecklistSubmissionWithDetails, ManagerSignoffCreate, ManagerSignoffResponse
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ==================== Templates ====================

@router.get("/templates", response_model=List[ChecklistTemplateResponse])
async def list_templates(
    location_id: Optional[int] = Query(None),
    checklist_type: Optional[ChecklistType] = Query(None),
    is_active: Optional[bool] = Query(True),
    db: AsyncSession = Depends(get_db)
):
    """List checklist templates"""
    query = select(ChecklistTemplate)

    if location_id:
        # Include templates for this location OR global templates (location_id is NULL)
        query = query.where(
            (ChecklistTemplate.location_id == location_id) |
            (ChecklistTemplate.location_id.is_(None))
        )
    if checklist_type:
        query = query.where(ChecklistTemplate.checklist_type == checklist_type)
    if is_active is not None:
        query = query.where(ChecklistTemplate.is_active == is_active)

    query = query.order_by(ChecklistTemplate.name)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/templates/{template_id}", response_model=ChecklistTemplateWithItems)
async def get_template(
    template_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get checklist template with items"""
    query = select(ChecklistTemplate).options(
        selectinload(ChecklistTemplate.items)
    ).where(ChecklistTemplate.id == template_id)

    result = await db.execute(query)
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Get location name
    location_name = None
    if template.location_id:
        loc_query = select(Location.name).where(Location.id == template.location_id)
        loc_result = await db.execute(loc_query)
        location_name = loc_result.scalar_one_or_none()

    response = ChecklistTemplateWithItems.model_validate(template)
    response.location_name = location_name
    return response


@router.post("/templates", response_model=ChecklistTemplateWithItems, status_code=201)
async def create_template(
    data: ChecklistTemplateCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new checklist template"""
    # Extract items from data
    items_data = data.items
    template_data = data.model_dump(exclude={"items"})

    template = ChecklistTemplate(**template_data)
    db.add(template)
    await db.flush()  # Get template ID

    # Create items
    for idx, item_data in enumerate(items_data):
        item = ChecklistItem(
            template_id=template.id,
            sort_order=item_data.sort_order if item_data.sort_order else idx,
            **item_data.model_dump(exclude={"sort_order"})
        )
        db.add(item)

    await db.commit()
    await db.refresh(template)

    # Reload with items
    query = select(ChecklistTemplate).options(
        selectinload(ChecklistTemplate.items)
    ).where(ChecklistTemplate.id == template.id)
    result = await db.execute(query)
    template = result.scalar_one()

    logger.info(f"Created checklist template: {template.name}")
    return ChecklistTemplateWithItems.model_validate(template)


@router.put("/templates/{template_id}", response_model=ChecklistTemplateResponse)
async def update_template(
    template_id: int,
    data: ChecklistTemplateUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a checklist template"""
    query = select(ChecklistTemplate).where(ChecklistTemplate.id == template_id)
    result = await db.execute(query)
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(template, field, value)

    await db.commit()
    await db.refresh(template)

    logger.info(f"Updated checklist template: {template.name}")
    return template


@router.post("/templates/{template_id}/items", response_model=ChecklistItemResponse, status_code=201)
async def add_template_item(
    template_id: int,
    data: ChecklistItemCreate,
    db: AsyncSession = Depends(get_db)
):
    """Add an item to a checklist template"""
    # Verify template exists
    query = select(ChecklistTemplate.id).where(ChecklistTemplate.id == template_id)
    result = await db.execute(query)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Template not found")

    item = ChecklistItem(template_id=template_id, **data.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)

    logger.info(f"Added item to template {template_id}")
    return item


@router.delete("/templates/{template_id}/items/{item_id}")
async def delete_template_item(
    template_id: int,
    item_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Remove an item from a checklist template"""
    query = select(ChecklistItem).where(
        and_(
            ChecklistItem.id == item_id,
            ChecklistItem.template_id == template_id
        )
    )
    result = await db.execute(query)
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    await db.delete(item)
    await db.commit()

    logger.info(f"Deleted item {item_id} from template {template_id}")
    return {"message": "Item deleted"}


# ==================== Submissions ====================

@router.get("/submissions", response_model=List[ChecklistSubmissionResponse])
async def list_submissions(
    location_id: Optional[int] = Query(None),
    template_id: Optional[int] = Query(None),
    status: Optional[ChecklistStatus] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db)
):
    """List checklist submissions"""
    query = select(ChecklistSubmission)

    if location_id:
        query = query.where(ChecklistSubmission.location_id == location_id)
    if template_id:
        query = query.where(ChecklistSubmission.template_id == template_id)
    if status:
        query = query.where(ChecklistSubmission.status == status)
    if start_date:
        query = query.where(ChecklistSubmission.submission_date >= start_date)
    if end_date:
        query = query.where(ChecklistSubmission.submission_date <= end_date)

    query = query.order_by(ChecklistSubmission.submission_date.desc()).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/submissions/{submission_id}", response_model=ChecklistSubmissionWithDetails)
async def get_submission(
    submission_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get checklist submission with responses"""
    query = select(ChecklistSubmission).options(
        selectinload(ChecklistSubmission.responses),
        selectinload(ChecklistSubmission.signoffs)
    ).where(ChecklistSubmission.id == submission_id)

    result = await db.execute(query)
    submission = result.scalar_one_or_none()

    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    # Get template and location names
    template_query = select(ChecklistTemplate.name).where(ChecklistTemplate.id == submission.template_id)
    template_result = await db.execute(template_query)
    template_name = template_result.scalar_one_or_none()

    location_query = select(Location.name).where(Location.id == submission.location_id)
    location_result = await db.execute(location_query)
    location_name = location_result.scalar_one_or_none()

    response = ChecklistSubmissionWithDetails.model_validate(submission)
    response.template_name = template_name
    response.location_name = location_name
    return response


@router.post("/submissions", response_model=ChecklistSubmissionResponse, status_code=201)
async def start_submission(
    data: ChecklistSubmissionCreate,
    db: AsyncSession = Depends(get_db)
):
    """Start a new checklist submission"""
    # Verify template exists
    template_query = select(ChecklistTemplate).where(ChecklistTemplate.id == data.template_id)
    result = await db.execute(template_query)
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    submission = ChecklistSubmission(
        template_id=data.template_id,
        location_id=data.location_id,
        submission_date=data.submission_date,
        shift_id=data.shift_id,
        status=ChecklistStatus.IN_PROGRESS,
        notes=data.notes
    )
    db.add(submission)
    await db.commit()
    await db.refresh(submission)

    logger.info(f"Started checklist submission for template {template.name}")
    return submission


@router.post("/submissions/{submission_id}/complete", response_model=ChecklistSubmissionResponse)
async def complete_submission(
    submission_id: int,
    data: ChecklistSubmissionComplete,
    db: AsyncSession = Depends(get_db)
):
    """Complete a checklist submission with all responses"""
    query = select(ChecklistSubmission).options(
        selectinload(ChecklistSubmission.template)
    ).where(ChecklistSubmission.id == submission_id)

    result = await db.execute(query)
    submission = result.scalar_one_or_none()

    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    if submission.status not in [ChecklistStatus.IN_PROGRESS]:
        raise HTTPException(status_code=400, detail="Submission cannot be completed in current status")

    # Delete existing responses and add new ones
    delete_query = select(ChecklistResponse).where(ChecklistResponse.submission_id == submission_id)
    delete_result = await db.execute(delete_query)
    for existing in delete_result.scalars().all():
        await db.delete(existing)

    # Add new responses
    for resp_data in data.responses:
        response = ChecklistResponse(
            submission_id=submission_id,
            item_id=resp_data.item_id,
            response_value=resp_data.response_value,
            is_passing=resp_data.is_passing,
            corrective_action=resp_data.corrective_action,
            notes=resp_data.notes,
            responded_by=resp_data.responded_by or data.completed_by
        )
        db.add(response)

    # Update submission status
    submission.completed_by = data.completed_by
    submission.completed_at = get_now()
    submission.notes = data.notes

    # Check if manager signoff is required
    if submission.template.requires_manager_signoff:
        submission.status = ChecklistStatus.PENDING_SIGNOFF
    else:
        submission.status = ChecklistStatus.COMPLETED

    await db.commit()
    await db.refresh(submission)

    logger.info(f"Completed checklist submission {submission_id}")
    return submission


@router.post("/submissions/{submission_id}/signoff", response_model=ManagerSignoffResponse)
async def manager_signoff(
    submission_id: int,
    data: ManagerSignoffCreate,
    db: AsyncSession = Depends(get_db)
):
    """Manager sign-off on a checklist submission"""
    query = select(ChecklistSubmission).where(ChecklistSubmission.id == submission_id)
    result = await db.execute(query)
    submission = result.scalar_one_or_none()

    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    if submission.status != ChecklistStatus.PENDING_SIGNOFF:
        raise HTTPException(status_code=400, detail="Submission is not pending sign-off")

    signoff = ManagerSignoff(
        submission_id=submission_id,
        signed_off_by=data.signed_off_by,
        is_approved=data.is_approved,
        rejection_reason=data.rejection_reason,
        notes=data.notes
    )
    db.add(signoff)

    # Update submission status
    if data.is_approved:
        submission.status = ChecklistStatus.SIGNED_OFF
    else:
        submission.status = ChecklistStatus.REJECTED

    await db.commit()
    await db.refresh(signoff)

    logger.info(f"Manager {'approved' if data.is_approved else 'rejected'} submission {submission_id}")
    return signoff


@router.get("/pending-signoffs", response_model=List[ChecklistSubmissionResponse])
async def list_pending_signoffs(
    location_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """List submissions pending manager sign-off"""
    query = select(ChecklistSubmission).where(
        ChecklistSubmission.status == ChecklistStatus.PENDING_SIGNOFF
    )

    if location_id:
        query = query.where(ChecklistSubmission.location_id == location_id)

    query = query.order_by(ChecklistSubmission.completed_at)
    result = await db.execute(query)
    return result.scalars().all()
