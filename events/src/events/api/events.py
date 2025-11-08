"""Events API endpoints (example implementation)"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
from uuid import UUID

from events.core.database import get_db
from events.core.deps import require_auth, require_role, require_permission, check_permission
from events.models import Event, EventStatus, Venue, Client, Task, TaskStatus, User
from events.schemas.event import EventCreate, EventUpdate, EventResponse, EventListItem
from sqlalchemy import func

router = APIRouter()


@router.get("/stats")
async def get_dashboard_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """
    Get dashboard statistics

    Returns counts for:
    - Total events (all non-canceled)
    - Confirmed events
    - Pending tasks
    - Overdue tasks
    """
    from datetime import datetime

    # Count total active events
    total_events = db.query(func.count(Event.id)).filter(
        Event.status != EventStatus.CANCELED
    ).scalar() or 0

    # Count confirmed events
    confirmed_events = db.query(func.count(Event.id)).filter(
        Event.status == EventStatus.CONFIRMED
    ).scalar() or 0

    # Count pending tasks (TODO and IN_PROGRESS)
    pending_tasks = db.query(func.count(Task.id)).filter(
        Task.status.in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS])
    ).scalar() or 0

    # Count overdue tasks
    overdue_tasks = db.query(func.count(Task.id)).filter(
        Task.status.in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS]),
        Task.due_at < datetime.utcnow()
    ).scalar() or 0

    return {
        "total_events": total_events,
        "confirmed_events": confirmed_events,
        "pending_tasks": pending_tasks,
        "overdue_tasks": overdue_tasks
    }


@router.get("/", response_model=List[EventListItem])
async def list_events(
    skip: int = 0,
    limit: int = 100,
    status: Optional[EventStatus] = None,
    event_type: Optional[str] = None,
    venue_id: Optional[UUID] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """
    List events with optional filters

    - **skip**: Number of records to skip (pagination)
    - **limit**: Max number of records to return
    - **status**: Filter by event status
    - **event_type**: Filter by event type
    - **venue_id**: Filter by venue
    - **start_date**: Events starting after this date
    - **end_date**: Events ending before this date
    """
    # Check permission to read events
    if not check_permission(current_user, "read", "event"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to view events"
        )

    query = db.query(Event)

    # By default, exclude CANCELED events unless explicitly requested
    if status:
        query = query.filter(Event.status == status)
    else:
        query = query.filter(Event.status != EventStatus.CANCELED)

    if event_type:
        query = query.filter(Event.event_type == event_type)
    if venue_id:
        query = query.filter(Event.venue_id == venue_id)
    if start_date:
        query = query.filter(Event.start_at >= start_date)
    if end_date:
        query = query.filter(Event.end_at <= end_date)

    events = query.order_by(Event.start_at.desc()).offset(skip).limit(limit).all()
    return events


@router.get("/calendar", response_model=List[EventListItem])
async def get_calendar_events(
    start: datetime = Query(..., description="Calendar start date"),
    end: datetime = Query(..., description="Calendar end date"),
    view: str = Query("month", regex="^(month|week|day)$"),
    location: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """
    Get events for calendar view

    - **start**: Start of calendar period
    - **end**: End of calendar period
    - **view**: Calendar view mode (month, week, day)
    - **location**: Optional location filter
    """
    query = db.query(Event).filter(
        Event.start_at >= start,
        Event.start_at <= end
    )

    if location:
        query = query.filter(Event.location == location)

    # Exclude canceled events from calendar
    query = query.filter(Event.status != EventStatus.CANCELED)

    events = query.order_by(Event.start_at).all()
    return events


@router.get("/venues")
async def list_venues(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Get all venues"""
    venues = db.query(Venue).order_by(Venue.name).all()
    return [{"id": str(v.id), "name": v.name, "address": v.address} for v in venues]


@router.get("/clients")
async def list_clients(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Get all clients"""
    clients = db.query(Client).order_by(Client.name).all()
    return [{"id": str(c.id), "name": c.name, "email": c.email, "phone": c.phone} for c in clients]


@router.get("/{event_id}", response_model=EventResponse)
async def get_event(
    event_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Get single event by ID"""
    from sqlalchemy.orm import joinedload

    event = db.query(Event).options(
        joinedload(Event.client),
        joinedload(Event.venue)
    ).filter(Event.id == event_id).first()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )

    # TODO: Filter financials based on user role
    # event_data = EventResponse.from_orm(event).dict()
    # event_data = auth_service.filter_financials(current_user, event_data)
    # return event_data

    return event


@router.post("/", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
async def create_event(
    event_data: EventCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """
    Create new event

    Requires: event_manager or admin role
    """
    # Check permissions
    if not check_permission(current_user, "create", "event"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to create events"
        )

    event = Event(**event_data.dict())
    event.created_by = current_user.id

    db.add(event)
    db.commit()
    db.refresh(event)

    # TODO: Generate initial tasks from template
    # TODO: Send confirmation email

    return event


@router.patch("/{event_id}", response_model=EventResponse)
async def update_event(
    event_id: UUID,
    event_data: EventUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("update", "event"))
):
    """
    Update event

    Requires: admin or event_manager role
    """
    event = db.query(Event).filter(Event.id == event_id).first()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    update_data = event_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(event, field, value)

    db.commit()
    db.refresh(event)

    # TODO: If time changed, update task due dates
    # TODO: Send update notifications
    # TODO: Audit log

    return event


@router.post("/{event_id}:confirm", response_model=EventResponse)
async def confirm_event(
    event_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "event_manager"))
):
    """
    Confirm event (change status to confirmed)

    Requires: admin or event_manager role

    Triggers:
    - Generate BEO PDF
    - Send notifications to departments
    - Send confirmation to client
    """
    event = db.query(Event).filter(Event.id == event_id).first()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    if event.status == EventStatus.CONFIRMED:
        raise HTTPException(status_code=400, detail="Event already confirmed")

    event.status = EventStatus.CONFIRMED

    db.commit()
    db.refresh(event)

    # TODO: Generate documents
    # TODO: Send notifications
    # TODO: Audit log

    return event


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(
    event_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    """
    Delete event (soft delete - mark as canceled)

    Requires: admin role only
    """
    event = db.query(Event).filter(Event.id == event_id).first()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # Soft delete - mark as canceled
    event.status = EventStatus.CANCELED

    db.commit()

    # TODO: Cancel associated tasks
    # TODO: Send cancellation notifications
    # TODO: Audit log

    return None
