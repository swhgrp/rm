"""Incident management router for Food Safety Service"""
import logging
from datetime import date, datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload

from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
def get_now(): return datetime.now(_ET)

from food_safety.database import get_db
from food_safety.models import (
    Incident, CorrectiveAction, IncidentType, IncidentStatus,
    CorrectiveActionStatus, Location
)
from food_safety.schemas import (
    IncidentCreate, IncidentUpdate, IncidentResponse, IncidentWithDetails,
    IncidentInvestigate, IncidentResolve,
    CorrectiveActionCreate, CorrectiveActionUpdate, CorrectiveActionResponse,
    CorrectiveActionComplete, CorrectiveActionVerify
)

logger = logging.getLogger(__name__)
router = APIRouter()


async def generate_incident_number(db: AsyncSession) -> str:
    """Generate next incident number in format INC-YYYY-NNNN"""
    year = get_now().year
    prefix = f"INC-{year}-"

    # Get the highest incident number for this year
    query = select(func.max(Incident.incident_number)).where(
        Incident.incident_number.like(f"{prefix}%")
    )
    result = await db.execute(query)
    max_number = result.scalar_one_or_none()

    if max_number:
        # Extract the sequence number and increment
        try:
            seq = int(max_number.split("-")[-1])
            next_seq = seq + 1
        except (ValueError, IndexError):
            next_seq = 1
    else:
        next_seq = 1

    return f"{prefix}{next_seq:04d}"


# ==================== Incidents ====================

@router.get("", response_model=List[IncidentResponse])
async def list_incidents(
    location_id: Optional[int] = Query(None),
    incident_type: Optional[IncidentType] = Query(None),
    status: Optional[IncidentStatus] = Query(None),
    severity: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db)
):
    """List incidents with optional filters"""
    query = select(Incident)

    if location_id:
        query = query.where(Incident.location_id == location_id)
    if incident_type:
        query = query.where(Incident.incident_type == incident_type)
    if status:
        query = query.where(Incident.status == status)
    if severity:
        query = query.where(Incident.severity == severity)
    if start_date:
        query = query.where(Incident.incident_date >= start_date)
    if end_date:
        query = query.where(Incident.incident_date <= end_date)

    query = query.order_by(Incident.incident_date.desc()).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/open", response_model=List[IncidentResponse])
async def list_open_incidents(
    location_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """List all open incidents"""
    query = select(Incident).where(
        Incident.status.in_([
            IncidentStatus.OPEN,
            IncidentStatus.INVESTIGATING,
            IncidentStatus.ACTION_REQUIRED
        ])
    )

    if location_id:
        query = query.where(Incident.location_id == location_id)

    query = query.order_by(Incident.incident_date.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{incident_id}", response_model=IncidentWithDetails)
async def get_incident(
    incident_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get incident with corrective actions"""
    query = select(Incident).options(
        selectinload(Incident.corrective_actions)
    ).where(Incident.id == incident_id)

    result = await db.execute(query)
    incident = result.scalar_one_or_none()

    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Get location name
    loc_query = select(Location.name).where(Location.id == incident.location_id)
    loc_result = await db.execute(loc_query)
    location_name = loc_result.scalar_one_or_none()

    response = IncidentWithDetails.model_validate(incident)
    response.location_name = location_name
    return response


@router.post("", response_model=IncidentResponse, status_code=201)
async def create_incident(
    data: IncidentCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new incident"""
    # Generate incident number
    incident_number = await generate_incident_number(db)

    incident_data = data.model_dump()
    if not incident_data.get("reported_by"):
        incident_data["reported_by"] = 0  # Default when no auth context

    incident = Incident(
        incident_number=incident_number,
        status=IncidentStatus.OPEN,
        **incident_data
    )
    db.add(incident)
    await db.commit()
    await db.refresh(incident)

    logger.info(f"Created incident: {incident_number} - {incident.title}")
    # TODO: Send email alert for new incident
    return incident


@router.put("/{incident_id}", response_model=IncidentResponse)
async def update_incident(
    incident_id: int,
    data: IncidentUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update an incident"""
    query = select(Incident).where(Incident.id == incident_id)
    result = await db.execute(query)
    incident = result.scalar_one_or_none()

    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(incident, field, value)

    await db.commit()
    await db.refresh(incident)

    logger.info(f"Updated incident: {incident.incident_number}")
    return incident


@router.post("/{incident_id}/investigate", response_model=IncidentResponse)
async def start_investigation(
    incident_id: int,
    data: IncidentInvestigate,
    db: AsyncSession = Depends(get_db)
):
    """Start or update investigation on an incident"""
    query = select(Incident).where(Incident.id == incident_id)
    result = await db.execute(query)
    incident = result.scalar_one_or_none()

    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    incident.status = IncidentStatus.INVESTIGATING
    incident.investigated_by = data.investigated_by
    incident.investigation_notes = data.investigation_notes
    if data.root_cause:
        incident.root_cause = data.root_cause

    await db.commit()
    await db.refresh(incident)

    logger.info(f"Started investigation on incident: {incident.incident_number}")
    return incident


@router.post("/{incident_id}/resolve", response_model=IncidentResponse)
async def resolve_incident(
    incident_id: int,
    data: IncidentResolve,
    db: AsyncSession = Depends(get_db)
):
    """Resolve an incident"""
    query = select(Incident).where(Incident.id == incident_id)
    result = await db.execute(query)
    incident = result.scalar_one_or_none()

    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    incident.status = IncidentStatus.RESOLVED
    incident.resolved_by = data.resolved_by
    incident.resolved_at = get_now()
    incident.resolution_notes = data.resolution_notes

    await db.commit()
    await db.refresh(incident)

    logger.info(f"Resolved incident: {incident.incident_number}")
    return incident


@router.post("/{incident_id}/close", response_model=IncidentResponse)
async def close_incident(
    incident_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Close a resolved incident"""
    query = select(Incident).where(Incident.id == incident_id)
    result = await db.execute(query)
    incident = result.scalar_one_or_none()

    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    if incident.status != IncidentStatus.RESOLVED:
        raise HTTPException(status_code=400, detail="Incident must be resolved before closing")

    incident.status = IncidentStatus.CLOSED

    await db.commit()
    await db.refresh(incident)

    logger.info(f"Closed incident: {incident.incident_number}")
    return incident


# ==================== Corrective Actions ====================

@router.get("/{incident_id}/corrective-actions", response_model=List[CorrectiveActionResponse])
async def list_corrective_actions(
    incident_id: int,
    db: AsyncSession = Depends(get_db)
):
    """List corrective actions for an incident"""
    query = select(CorrectiveAction).where(
        CorrectiveAction.incident_id == incident_id
    ).order_by(CorrectiveAction.created_at)

    result = await db.execute(query)
    return result.scalars().all()


@router.post("/{incident_id}/corrective-actions", response_model=CorrectiveActionResponse, status_code=201)
async def add_corrective_action(
    incident_id: int,
    data: CorrectiveActionCreate,
    db: AsyncSession = Depends(get_db)
):
    """Add a corrective action to an incident"""
    # Verify incident exists
    query = select(Incident.id).where(Incident.id == incident_id)
    result = await db.execute(query)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Incident not found")

    action = CorrectiveAction(
        incident_id=incident_id,
        action_description=data.action_description,
        assigned_to=data.assigned_to,
        due_date=data.due_date,
        status=CorrectiveActionStatus.PENDING
    )
    db.add(action)

    # Update incident status to action_required
    incident_query = select(Incident).where(Incident.id == incident_id)
    incident_result = await db.execute(incident_query)
    incident = incident_result.scalar_one()
    if incident.status in [IncidentStatus.OPEN, IncidentStatus.INVESTIGATING]:
        incident.status = IncidentStatus.ACTION_REQUIRED

    await db.commit()
    await db.refresh(action)

    logger.info(f"Added corrective action to incident {incident_id}")
    return action


@router.put("/corrective-actions/{action_id}", response_model=CorrectiveActionResponse)
async def update_corrective_action(
    action_id: int,
    data: CorrectiveActionUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a corrective action"""
    query = select(CorrectiveAction).where(CorrectiveAction.id == action_id)
    result = await db.execute(query)
    action = result.scalar_one_or_none()

    if not action:
        raise HTTPException(status_code=404, detail="Corrective action not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(action, field, value)

    await db.commit()
    await db.refresh(action)

    logger.info(f"Updated corrective action {action_id}")
    return action


@router.post("/corrective-actions/{action_id}/complete", response_model=CorrectiveActionResponse)
async def complete_corrective_action(
    action_id: int,
    data: CorrectiveActionComplete,
    db: AsyncSession = Depends(get_db)
):
    """Mark a corrective action as completed"""
    query = select(CorrectiveAction).where(CorrectiveAction.id == action_id)
    result = await db.execute(query)
    action = result.scalar_one_or_none()

    if not action:
        raise HTTPException(status_code=404, detail="Corrective action not found")

    action.status = CorrectiveActionStatus.COMPLETED
    action.completed_by = data.completed_by
    action.completed_at = get_now()
    action.completion_notes = data.completion_notes

    await db.commit()
    await db.refresh(action)

    logger.info(f"Completed corrective action {action_id}")
    return action


@router.post("/corrective-actions/{action_id}/verify", response_model=CorrectiveActionResponse)
async def verify_corrective_action(
    action_id: int,
    data: CorrectiveActionVerify,
    db: AsyncSession = Depends(get_db)
):
    """Verify a completed corrective action"""
    query = select(CorrectiveAction).where(CorrectiveAction.id == action_id)
    result = await db.execute(query)
    action = result.scalar_one_or_none()

    if not action:
        raise HTTPException(status_code=404, detail="Corrective action not found")

    if action.status != CorrectiveActionStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Action must be completed before verification")

    action.status = CorrectiveActionStatus.VERIFIED
    action.verified_by = data.verified_by
    action.verified_at = get_now()
    action.verification_notes = data.verification_notes

    await db.commit()
    await db.refresh(action)

    logger.info(f"Verified corrective action {action_id}")
    return action


@router.get("/corrective-actions/pending", response_model=List[CorrectiveActionResponse])
async def list_pending_corrective_actions(
    db: AsyncSession = Depends(get_db)
):
    """List all pending corrective actions"""
    query = select(CorrectiveAction).where(
        CorrectiveAction.status.in_([
            CorrectiveActionStatus.PENDING,
            CorrectiveActionStatus.IN_PROGRESS
        ])
    ).order_by(CorrectiveAction.due_date)

    result = await db.execute(query)
    return result.scalars().all()
