"""Events API endpoints (example implementation)"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
from uuid import UUID
import logging

from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
def get_now(): return datetime.now(_ET)

from events.core.database import get_db
from events.core.deps import require_auth, require_role, require_permission, check_permission, get_current_user
from events.models import Event, EventStatus, Venue, Client, Task, TaskStatus, User
from events.schemas.event import EventCreate, EventUpdate, EventResponse, EventListItem
from events.services.caldav_sync_service import CalDAVSyncService
from events.core.config import settings
from sqlalchemy import func

router = APIRouter()
logger = logging.getLogger(__name__)


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
        Task.due_at < get_now()
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

    # Location-based filtering: Users only see events for their assigned locations
    # Admins see all events
    user_roles = [role.code for role in current_user.roles]
    if "admin" not in user_roles:
        # Get user's assigned venue IDs
        from events.models.user import UserLocation
        user_venues = db.query(UserLocation.venue_id).filter(
            UserLocation.user_id == current_user.id
        ).all()
        user_venue_ids = [v[0] for v in user_venues]

        if user_venue_ids:
            # User has specific venue assignments - filter to only those venues
            query = query.filter(Event.venue_id.in_(user_venue_ids))
        # else: User has no assignments = unrestricted access to all venues

    # By default, exclude only CANCELED events unless a specific status is requested
    # CLOSED (Completed) events should be visible in the list
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

    events = query.order_by(Event.start_at.asc()).offset(skip).limit(limit).all()

    # Add venue_name to each event for display
    result = []
    for event in events:
        event_dict = {
            "id": event.id,
            "title": event.title,
            "event_type": event.event_type,
            "status": event.status,
            "start_at": event.start_at,
            "end_at": event.end_at,
            "guest_count": event.guest_count,
            "venue_id": event.venue_id,
            "venue_name": event.venue.name if event.venue else None,
            "location": event.location,
            "created_at": event.created_at
        }
        result.append(event_dict)

    return result


@router.get("/calendar", response_model=List[EventListItem])
async def get_calendar_events(
    start: datetime = Query(..., description="Calendar start date"),
    end: datetime = Query(..., description="Calendar end date"),
    view: str = Query("month", regex="^(month|week|day)$"),
    location: Optional[str] = None,
    q: Optional[str] = Query(None, description="Search query for event title"),
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

    # Location-based filtering: Users only see events for their assigned locations
    # Admins see all events
    user_roles = [role.code for role in current_user.roles]
    if "admin" not in user_roles:
        # Get user's assigned venue IDs
        from events.models.user import UserLocation
        user_venues = db.query(UserLocation.venue_id).filter(
            UserLocation.user_id == current_user.id
        ).all()
        user_venue_ids = [v[0] for v in user_venues]

        if user_venue_ids:
            # User has specific venue assignments - filter to only those venues
            query = query.filter(Event.venue_id.in_(user_venue_ids))
        # else: User has no assignments = unrestricted access to all venues

    if location:
        query = query.filter(Event.location == location)

    if q:
        query = query.filter(Event.title.ilike(f"%{q}%"))

    # Exclude canceled events from calendar
    query = query.filter(Event.status != EventStatus.CANCELED)

    events = query.order_by(Event.start_at).all()

    # Add venue_name to each event for display
    result = []
    for event in events:
        event_dict = {
            "id": event.id,
            "title": event.title,
            "event_type": event.event_type,
            "status": event.status,
            "start_at": event.start_at,
            "end_at": event.end_at,
            "guest_count": event.guest_count,
            "venue_id": event.venue_id,
            "venue_name": event.venue.name if event.venue else None,
            "location": event.location,
            "created_at": event.created_at
        }
        result.append(event_dict)

    return result


@router.get("/venues")
async def list_venues(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Get locations for calendar (now using locations table instead of venues)"""
    from events.models.settings import Location

    # Get all active locations with their colors
    query = db.query(Location).filter(Location.is_active == True)

    locations = query.order_by(Location.sort_order, Location.name).all()
    return [{"id": str(loc.id), "name": loc.name, "address": loc.description, "color": loc.color} for loc in locations]


@router.get("/venues/actual")
async def list_actual_venues(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Get actual venues from venues table (for event detail page)"""
    venues = db.query(Venue).order_by(Venue.name).all()
    return [{"id": str(v.id), "name": v.name, "address": v.address, "color": v.color} for v in venues]


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

    # Sync to CalDAV if enabled — push to ALL users with access to this venue
    if settings.CALDAV_ENABLED:
        try:
            from events.models.user import UserLocation
            caldav_service = CalDAVSyncService()

            users_to_sync = []
            if event.venue_id:
                user_venue_assignments = db.query(UserLocation).filter(
                    UserLocation.venue_id == event.venue_id
                ).all()
                for assignment in user_venue_assignments:
                    user = db.query(User).filter(User.id == assignment.user_id).first()
                    if user and user.is_active:
                        users_to_sync.append(user)

            if not users_to_sync:
                users_to_sync = [current_user]

            for user in users_to_sync:
                try:
                    caldav_service.sync_event_to_caldav(event, user.email)
                    logger.info(f"Event {event.id} synced to CalDAV for user {user.email}")
                except Exception as e:
                    logger.error(f"Failed to sync event {event.id} to CalDAV for {user.email}: {e}")
        except Exception as e:
            logger.error(f"Failed to sync event {event.id} to CalDAV: {e}")

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
    import logging
    logger = logging.getLogger(__name__)

    event = db.query(Event).filter(Event.id == event_id).first()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    update_data = event_data.dict(exclude_unset=True)
    logger.info(f"Updating event {event_id} with data: {update_data}")
    logger.info(f"Current event status: {event.status}, venue_id: {event.venue_id}")

    for field, value in update_data.items():
        setattr(event, field, value)

    db.commit()
    db.refresh(event)

    logger.info(f"After update - event status: {event.status}, venue_id: {event.venue_id}")

    # Sync to CalDAV if enabled — push to ALL users with access to this venue
    if settings.CALDAV_ENABLED:
        try:
            from events.models.user import UserLocation
            caldav_service = CalDAVSyncService()

            # Get all users who have access to this event's venue
            users_to_sync = []
            if event.venue_id:
                user_venue_assignments = db.query(UserLocation).filter(
                    UserLocation.venue_id == event.venue_id
                ).all()
                for assignment in user_venue_assignments:
                    user = db.query(User).filter(User.id == assignment.user_id).first()
                    if user and user.is_active:
                        users_to_sync.append(user)

            # Fallback to current user if no venue assignments found
            if not users_to_sync:
                users_to_sync = [current_user]

            for user in users_to_sync:
                try:
                    if event.status in [EventStatus.CANCELED, EventStatus.CLOSED]:
                        caldav_service.remove_event_from_caldav(event, user.email)
                        logger.info(f"Event {event.id} removed from CalDAV for user {user.email}")
                    else:
                        caldav_service.sync_event_to_caldav(event, user.email)
                        logger.info(f"Event {event.id} synced to CalDAV for user {user.email}")
                except Exception as e:
                    logger.error(f"Failed to sync event {event.id} to CalDAV for {user.email}: {e}")
        except Exception as e:
            logger.error(f"Failed to sync event {event.id} to CalDAV: {e}")
            # Don't fail the request if CalDAV sync fails

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

    # Remove from CalDAV for all users with access to this venue
    if settings.CALDAV_ENABLED:
        try:
            from events.models.user import UserLocation
            caldav_service = CalDAVSyncService()

            # Get all users who have access to this event's venue
            if event.venue_id:
                user_venue_assignments = db.query(UserLocation).filter(
                    UserLocation.venue_id == event.venue_id
                ).all()

                for assignment in user_venue_assignments:
                    user = db.query(User).filter(User.id == assignment.user_id).first()
                    if user and user.is_active:
                        try:
                            caldav_service.remove_event_from_caldav(event, user.email)
                            logger.info(f"Event {event.id} removed from CalDAV for user {user.email}")
                        except Exception as e:
                            logger.error(f"Failed to remove event {event.id} from CalDAV for {user.email}: {e}")
        except Exception as e:
            logger.error(f"Failed to remove event {event.id} from CalDAV: {e}")
            # Don't fail the request if CalDAV removal fails

    # TODO: Cancel associated tasks
    # TODO: Send cancellation notifications
    # TODO: Audit log

    return None


@router.post("/caldav/initial-sync", status_code=status.HTTP_200_OK)
async def caldav_initial_sync(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Initial bulk CalDAV sync for user joining calendar.
    Pushes all events from 1 month back + all future events to user's CalDAV calendar.

    This should be called when a user first connects their calendar via CalDAV.
    """
    if not settings.CALDAV_ENABLED:
        raise HTTPException(status_code=400, detail="CalDAV sync is not enabled")

    try:
        caldav_service = CalDAVSyncService()
        results = caldav_service.initial_sync_for_user(db, current_user.email, lookback_months=1)
        return {
            "success": True,
            "message": f"Initial sync complete: {results['synced']} events synced",
            "results": results
        }
    except Exception as e:
        logger.error(f"Initial CalDAV sync failed for {current_user.email}: {e}")
        raise HTTPException(status_code=500, detail=f"Initial sync failed: {str(e)}")


@router.post("/caldav/pull-changes", status_code=status.HTTP_200_OK)
async def caldav_pull_changes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Pull changes from CalDAV back to Events database (bidirectional sync).
    Checks for events that were updated or deleted in CalDAV and syncs changes back.

    This enables two-way sync:
    - Events created/updated/deleted in web app → automatically pushed to CalDAV
    - Events updated/deleted in phone calendar → pulled back via this endpoint
    """
    if not settings.CALDAV_ENABLED:
        raise HTTPException(status_code=400, detail="CalDAV sync is not enabled")

    try:
        caldav_service = CalDAVSyncService()
        results = caldav_service.pull_caldav_changes(db, current_user.email)
        return {
            "success": True,
            "message": f"CalDAV pull complete: {results['updated']} updated, {results['deleted']} deleted",
            "results": results
        }
    except Exception as e:
        logger.error(f"CalDAV pull sync failed for {current_user.email}: {e}")
        raise HTTPException(status_code=500, detail=f"Pull sync failed: {str(e)}")


@router.post("/caldav/cleanup-canceled", status_code=status.HTTP_200_OK)
async def caldav_cleanup_canceled(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    """
    Clean up canceled events from CalDAV.
    Removes all CANCELED events from CalDAV calendars for all users.

    Requires: admin role
    """
    if not settings.CALDAV_ENABLED:
        raise HTTPException(status_code=400, detail="CalDAV sync is not enabled")

    try:
        from events.models.user import UserLocation
        caldav_service = CalDAVSyncService()

        # Get all canceled events
        canceled_events = db.query(Event).filter(
            Event.status == EventStatus.CANCELED
        ).all()

        removed_count = 0
        error_count = 0

        for event in canceled_events:
            if event.venue_id:
                # Get all users who have access to this event's venue
                user_venue_assignments = db.query(UserLocation).filter(
                    UserLocation.venue_id == event.venue_id
                ).all()

                for assignment in user_venue_assignments:
                    user = db.query(User).filter(User.id == assignment.user_id).first()
                    if user and user.is_active:
                        try:
                            caldav_service.remove_event_from_caldav(event, user.email)
                            removed_count += 1
                        except Exception as e:
                            logger.error(f"Failed to remove event {event.id} from CalDAV for {user.email}: {e}")
                            error_count += 1

        return {
            "success": True,
            "message": f"Cleanup complete: {removed_count} events removed from CalDAV",
            "removed": removed_count,
            "errors": error_count,
            "total_canceled_events": len(canceled_events)
        }
    except Exception as e:
        logger.error(f"CalDAV cleanup failed: {e}")
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {str(e)}")
