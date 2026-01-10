"""Inspection management router for Food Safety Service"""
import logging
from datetime import date, datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from food_safety.database import get_db
from food_safety.models import (
    Inspection, InspectionViolation, CorrectiveAction,
    InspectionType, ViolationSeverity, CorrectiveActionStatus, Location
)
from food_safety.schemas import (
    InspectionCreate, InspectionUpdate, InspectionResponse, InspectionWithViolations,
    InspectionViolationCreate, InspectionViolationResponse
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", response_model=List[InspectionResponse])
async def list_inspections(
    location_id: Optional[int] = Query(None),
    inspection_type: Optional[InspectionType] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db)
):
    """List inspections with optional filters"""
    query = select(Inspection)

    if location_id:
        query = query.where(Inspection.location_id == location_id)
    if inspection_type:
        query = query.where(Inspection.inspection_type == inspection_type)
    if start_date:
        query = query.where(Inspection.inspection_date >= start_date)
    if end_date:
        query = query.where(Inspection.inspection_date <= end_date)

    query = query.order_by(Inspection.inspection_date.desc()).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{inspection_id}", response_model=InspectionWithViolations)
async def get_inspection(
    inspection_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get inspection with violations"""
    query = select(Inspection).options(
        selectinload(Inspection.violations).selectinload(InspectionViolation.corrective_actions)
    ).where(Inspection.id == inspection_id)

    result = await db.execute(query)
    inspection = result.scalar_one_or_none()

    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")

    # Get location name
    loc_query = select(Location.name).where(Location.id == inspection.location_id)
    loc_result = await db.execute(loc_query)
    location_name = loc_result.scalar_one_or_none()

    response = InspectionWithViolations.model_validate(inspection)
    response.location_name = location_name
    return response


@router.post("", response_model=InspectionWithViolations, status_code=201)
async def create_inspection(
    data: InspectionCreate,
    db: AsyncSession = Depends(get_db)
):
    """Record a new inspection"""
    # Extract violations from data
    violations_data = data.violations
    inspection_data = data.model_dump(exclude={"violations"})

    inspection = Inspection(**inspection_data)
    db.add(inspection)
    await db.flush()  # Get inspection ID

    # Create violations and auto-create corrective actions
    for violation_data in violations_data:
        violation = InspectionViolation(
            inspection_id=inspection.id,
            **violation_data.model_dump()
        )
        db.add(violation)
        await db.flush()  # Get violation ID

        # Auto-create corrective action for non-observation violations
        if violation_data.severity != ViolationSeverity.OBSERVATION:
            corrective_action = CorrectiveAction(
                inspection_violation_id=violation.id,
                action_description=f"Correct violation: {violation_data.description[:200]}",
                due_date=violation_data.correction_deadline,
                status=CorrectiveActionStatus.PENDING
            )
            db.add(corrective_action)

    await db.commit()
    await db.refresh(inspection)

    # Reload with violations
    query = select(Inspection).options(
        selectinload(Inspection.violations).selectinload(InspectionViolation.corrective_actions)
    ).where(Inspection.id == inspection.id)
    result = await db.execute(query)
    inspection = result.scalar_one()

    logger.info(f"Recorded inspection for location {data.location_id} on {data.inspection_date}")
    return InspectionWithViolations.model_validate(inspection)


@router.put("/{inspection_id}", response_model=InspectionResponse)
async def update_inspection(
    inspection_id: int,
    data: InspectionUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update an inspection"""
    query = select(Inspection).where(Inspection.id == inspection_id)
    result = await db.execute(query)
    inspection = result.scalar_one_or_none()

    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(inspection, field, value)

    await db.commit()
    await db.refresh(inspection)

    logger.info(f"Updated inspection {inspection_id}")
    return inspection


@router.post("/{inspection_id}/violations", response_model=InspectionViolationResponse, status_code=201)
async def add_violation(
    inspection_id: int,
    data: InspectionViolationCreate,
    db: AsyncSession = Depends(get_db)
):
    """Add a violation to an inspection"""
    # Verify inspection exists
    query = select(Inspection.id).where(Inspection.id == inspection_id)
    result = await db.execute(query)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Inspection not found")

    violation = InspectionViolation(
        inspection_id=inspection_id,
        **data.model_dump()
    )
    db.add(violation)
    await db.flush()

    # Auto-create corrective action for non-observation violations
    if data.severity != ViolationSeverity.OBSERVATION:
        corrective_action = CorrectiveAction(
            inspection_violation_id=violation.id,
            action_description=f"Correct violation: {data.description[:200]}",
            due_date=data.correction_deadline,
            status=CorrectiveActionStatus.PENDING
        )
        db.add(corrective_action)

    await db.commit()
    await db.refresh(violation)

    logger.info(f"Added violation to inspection {inspection_id}")
    return violation


@router.post("/violations/{violation_id}/correct", response_model=InspectionViolationResponse)
async def mark_violation_corrected(
    violation_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Mark a violation as corrected"""
    query = select(InspectionViolation).where(InspectionViolation.id == violation_id)
    result = await db.execute(query)
    violation = result.scalar_one_or_none()

    if not violation:
        raise HTTPException(status_code=404, detail="Violation not found")

    violation.is_corrected = True
    violation.corrected_at = datetime.utcnow()

    await db.commit()
    await db.refresh(violation)

    logger.info(f"Marked violation {violation_id} as corrected")
    return violation


@router.get("/upcoming-followups", response_model=List[InspectionResponse])
async def list_upcoming_followups(
    days: int = Query(30, le=90),
    db: AsyncSession = Depends(get_db)
):
    """List inspections with upcoming follow-ups"""
    today = date.today()
    end_date = date.today()

    # Calculate end date manually
    from datetime import timedelta
    end_date = today + timedelta(days=days)

    query = select(Inspection).where(
        Inspection.follow_up_required == True,
        Inspection.follow_up_date >= today,
        Inspection.follow_up_date <= end_date
    ).order_by(Inspection.follow_up_date)

    result = await db.execute(query)
    return result.scalars().all()
