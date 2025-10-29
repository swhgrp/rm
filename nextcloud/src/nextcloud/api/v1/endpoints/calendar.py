"""
Calendar API endpoints for Nextcloud CalDAV operations
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from datetime import datetime, timedelta
from typing import Optional

from nextcloud.core.deps import get_current_user, require_nextcloud_setup
from nextcloud.models.user import User
from nextcloud.schemas.calendar import (
    CalendarListResponse,
    CalendarInfo,
    EventListResponse,
    CalendarEvent,
    CalendarEventCreate,
    CalendarEventUpdate,
    EventResponse,
    EventOperationResponse
)
from nextcloud.services.caldav_client import NextcloudCalDAVClient

router = APIRouter()


@router.get("/calendars", response_model=CalendarListResponse)
async def list_calendars(
    current_user: User = Depends(require_nextcloud_setup)
):
    """
    List all calendars for the current user

    Returns:
        List of calendars with metadata
    """
    try:
        client = NextcloudCalDAVClient(current_user)
        calendars = client.list_calendars()

        # Convert to Pydantic models
        calendar_items = [CalendarInfo(**cal) for cal in calendars]

        return CalendarListResponse(calendars=calendar_items)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list calendars: {str(e)}"
        )


@router.get("/events", response_model=EventListResponse)
async def list_events(
    calendar_url: Optional[str] = Query(None, description="Calendar URL (all if not specified)"),
    start_date: Optional[datetime] = Query(None, description="Start date for events"),
    end_date: Optional[datetime] = Query(None, description="End date for events"),
    current_user: User = Depends(require_nextcloud_setup)
):
    """
    List calendar events within a date range

    Args:
        calendar_url: Calendar URL (optional, queries all if not specified)
        start_date: Start date (default: 30 days ago)
        end_date: End date (default: 30 days from now)

    Returns:
        List of events
    """
    try:
        client = NextcloudCalDAVClient(current_user)

        # Set defaults
        if start_date is None:
            start_date = datetime.now() - timedelta(days=30)
        if end_date is None:
            end_date = datetime.now() + timedelta(days=30)

        events = client.get_events(
            calendar_url=calendar_url,
            start_date=start_date,
            end_date=end_date
        )

        # Convert to Pydantic models
        event_items = [CalendarEvent(**event) for event in events]

        return EventListResponse(
            events=event_items,
            start_date=start_date,
            end_date=end_date
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list events: {str(e)}"
        )


@router.get("/events/today", response_model=EventListResponse)
async def get_today_events(
    current_user: User = Depends(require_nextcloud_setup)
):
    """
    Get today's events from all calendars

    Returns:
        List of today's events
    """
    try:
        client = NextcloudCalDAVClient(current_user)

        # Get events for today
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)

        events = client.get_events(
            start_date=today_start,
            end_date=today_end
        )

        # Convert to Pydantic models
        event_items = [CalendarEvent(**event) for event in events]

        return EventListResponse(
            events=event_items,
            start_date=today_start,
            end_date=today_end
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get today's events: {str(e)}"
        )


@router.post("/events", response_model=EventOperationResponse)
async def create_event(
    calendar_url: str = Query(..., description="Calendar URL"),
    event: CalendarEventCreate = None,
    current_user: User = Depends(require_nextcloud_setup)
):
    """
    Create a new calendar event

    Args:
        calendar_url: Calendar URL to add event to
        event: Event data

    Returns:
        Operation confirmation with event UID
    """
    try:
        client = NextcloudCalDAVClient(current_user)

        result = client.create_event(
            calendar_url=calendar_url,
            summary=event.summary,
            start=event.start,
            end=event.end,
            description=event.description,
            location=event.location,
            all_day=event.all_day
        )

        return EventOperationResponse(
            success=True,
            message="Event created successfully",
            uid=result.get('uid')
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create event: {str(e)}"
        )


@router.put("/events/{event_uid}", response_model=EventOperationResponse)
async def update_event(
    event_uid: str,
    calendar_url: str = Query(..., description="Calendar URL"),
    event: CalendarEventUpdate = None,
    current_user: User = Depends(require_nextcloud_setup)
):
    """
    Update an existing calendar event

    Args:
        event_uid: Event UID
        calendar_url: Calendar URL
        event: Updated event data

    Returns:
        Operation confirmation
    """
    try:
        client = NextcloudCalDAVClient(current_user)

        client.update_event(
            calendar_url=calendar_url,
            event_uid=event_uid,
            summary=event.summary,
            start=event.start,
            end=event.end,
            description=event.description,
            location=event.location
        )

        return EventOperationResponse(
            success=True,
            message="Event updated successfully",
            uid=event_uid
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update event: {str(e)}"
        )


@router.delete("/events/{event_uid}", response_model=EventOperationResponse)
async def delete_event(
    event_uid: str,
    calendar_url: str = Query(..., description="Calendar URL"),
    current_user: User = Depends(require_nextcloud_setup)
):
    """
    Delete a calendar event

    Args:
        event_uid: Event UID
        calendar_url: Calendar URL

    Returns:
        Operation confirmation
    """
    try:
        client = NextcloudCalDAVClient(current_user)

        client.delete_event(
            calendar_url=calendar_url,
            event_uid=event_uid
        )

        return EventOperationResponse(
            success=True,
            message="Event deleted successfully",
            uid=event_uid
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete event: {str(e)}"
        )
