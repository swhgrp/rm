"""Quick Holds API endpoints"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timezone
from uuid import UUID
import logging

from events.core.database import get_db
from events.core.deps import require_auth
from events.core.config import settings
from events.models import QuickHold, QuickHoldStatus, QuickHoldSource, Event, EventStatus, Client, User
from events.schemas.quick_hold import (
    QuickHoldCreate,
    QuickHoldUpdate,
    QuickHoldResponse,
    QuickHoldListResponse,
    ConvertToEventRequest
)
from events.services.caldav_sync_service import CalDAVSyncService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/", response_model=QuickHoldListResponse)
async def list_quick_holds(
    status: Optional[QuickHoldStatus] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """
    List quick holds with optional filters.

    By default returns only HOLD status (active holds).
    """
    query = db.query(QuickHold)

    # Default to active holds only
    if status:
        query = query.filter(QuickHold.status == status)
    else:
        query = query.filter(QuickHold.status == QuickHoldStatus.HOLD)

    # Date range filter
    if start_date:
        query = query.filter(QuickHold.start_at >= start_date)
    if end_date:
        query = query.filter(QuickHold.start_at <= end_date)

    # Order by start date
    query = query.order_by(QuickHold.start_at)

    holds = query.all()

    return QuickHoldListResponse(
        items=[QuickHoldResponse.model_validate(h) for h in holds],
        total=len(holds)
    )


@router.post("/", response_model=QuickHoldResponse, status_code=status.HTTP_201_CREATED)
async def create_quick_hold(
    hold_data: QuickHoldCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Create a new quick hold."""
    hold = QuickHold(
        title=hold_data.title,
        description=hold_data.description,
        start_at=hold_data.start_at,
        end_at=hold_data.end_at,
        all_day=hold_data.all_day,
        location_text=hold_data.location_text,
        source=hold_data.source,
        status=QuickHoldStatus.HOLD,
        created_by=current_user.id
    )

    db.add(hold)
    db.commit()
    db.refresh(hold)

    logger.info(f"Created quick hold: {hold.title} on {hold.start_at}")

    return QuickHoldResponse.model_validate(hold)


@router.get("/{hold_id}", response_model=QuickHoldResponse)
async def get_quick_hold(
    hold_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Get a specific quick hold by ID."""
    hold = db.query(QuickHold).filter(QuickHold.id == hold_id).first()

    if not hold:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quick hold not found"
        )

    return QuickHoldResponse.model_validate(hold)


@router.patch("/{hold_id}", response_model=QuickHoldResponse)
async def update_quick_hold(
    hold_id: UUID,
    hold_data: QuickHoldUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Update a quick hold."""
    hold = db.query(QuickHold).filter(QuickHold.id == hold_id).first()

    if not hold:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quick hold not found"
        )

    # Only allow updates to active holds
    if hold.status != QuickHoldStatus.HOLD:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot update a {hold.status.value} quick hold"
        )

    # Update fields
    update_data = hold_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(hold, field, value)

    db.commit()
    db.refresh(hold)

    logger.info(f"Updated quick hold: {hold.id}")

    return QuickHoldResponse.model_validate(hold)


@router.delete("/{hold_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_quick_hold(
    hold_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Delete (cancel) a quick hold."""
    hold = db.query(QuickHold).filter(QuickHold.id == hold_id).first()

    if not hold:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quick hold not found"
        )

    # Mark as canceled rather than hard delete
    hold.status = QuickHoldStatus.CANCELED
    db.commit()

    logger.info(f"Canceled quick hold: {hold.id}")


@router.post("/{hold_id}/convert", response_model=dict)
async def convert_to_event(
    hold_id: UUID,
    convert_data: ConvertToEventRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """
    Convert a quick hold to a full event.

    This creates a new Event from the quick hold data and marks
    the quick hold as CONVERTED.
    """
    hold = db.query(QuickHold).filter(QuickHold.id == hold_id).first()

    if not hold:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quick hold not found"
        )

    if hold.status != QuickHoldStatus.HOLD:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot convert a {hold.status.value} quick hold"
        )

    # Get or create client
    client_id = convert_data.client_id
    if not client_id:
        # Create a new client
        if not convert_data.client_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either client_id or client_name is required"
            )

        client = Client(
            name=convert_data.client_name,
            email=convert_data.client_email,
            phone=convert_data.client_phone,
            organization=convert_data.client_organization
        )
        db.add(client)
        db.flush()
        client_id = client.id

    # Create the event
    event = Event(
        title=hold.title,
        event_type=convert_data.event_type,
        venue_id=convert_data.venue_id,
        client_id=client_id,
        start_at=hold.start_at,
        end_at=hold.end_at,
        description=hold.description,
        guest_count=convert_data.guest_count,
        status=EventStatus.DRAFT,
        created_by=current_user.id
    )

    db.add(event)
    db.flush()

    # Mark quick hold as converted
    hold.status = QuickHoldStatus.CONVERTED
    hold.converted_to_event_id = event.id
    hold.converted_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(event)

    logger.info(f"Converted quick hold {hold.id} to event {event.id}")

    return {
        "message": "Quick hold converted to event successfully",
        "quick_hold_id": str(hold.id),
        "event_id": str(event.id)
    }


@router.get("/calendar/view")
async def get_quick_holds_for_calendar(
    start: datetime = Query(..., description="Start of date range"),
    end: datetime = Query(..., description="End of date range"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """
    Get quick holds for calendar view.

    Returns holds in a format suitable for calendar display,
    similar to the events calendar endpoint.
    """
    holds = db.query(QuickHold).filter(
        QuickHold.status == QuickHoldStatus.HOLD,
        QuickHold.start_at >= start,
        QuickHold.start_at <= end
    ).order_by(QuickHold.start_at).all()

    return [
        {
            "id": str(h.id),
            "title": h.title,
            "start": h.start_at.isoformat(),
            "end": h.end_at.isoformat(),
            "allDay": h.all_day,
            "type": "quick_hold",
            "status": h.status.value,
            "source": h.source.value,
            "location": h.location_text,
            "description": h.description,
            "color": "#FFA500",  # Orange for holds
            "borderColor": "#FF8C00",
            "textColor": "#000000"
        }
        for h in holds
    ]


@router.post("/sync/from-caldav")
async def sync_from_caldav(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """
    Sync quick holds from CalDAV (phone calendar).

    This polls the user's CalDAV calendars and imports any events
    that weren't created by the Events app as Quick Holds.

    Requires CalDAV to be enabled in settings.
    """
    if not settings.CALDAV_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CalDAV sync is not enabled. Enable CALDAV_ENABLED in settings."
        )

    sync_service = CalDAVSyncService()

    # Poll for new events and import as Quick Holds
    poll_results = sync_service.poll_caldav_for_quick_holds(db, current_user.email)

    # Check for changes to existing Quick Holds
    change_results = sync_service.sync_quick_hold_changes(db, current_user.email)

    return {
        "message": "CalDAV sync completed",
        "imported": poll_results.get('imported', 0),
        "skipped": poll_results.get('skipped', 0),
        "updated": change_results.get('updated', 0),
        "deleted": change_results.get('deleted', 0),
        "errors": poll_results.get('errors', 0) + change_results.get('errors', 0),
        "details": poll_results.get('details', [])
    }
