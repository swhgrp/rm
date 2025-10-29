"""
Pydantic schemas for calendar operations
"""
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class CalendarInfo(BaseModel):
    """Calendar information"""
    name: str
    display_name: str
    url: str
    color: Optional[str] = None
    description: Optional[str] = None


class CalendarEvent(BaseModel):
    """Calendar event"""
    uid: str
    summary: str
    description: Optional[str] = None
    location: Optional[str] = None
    start: datetime
    end: datetime
    all_day: bool = False
    calendar_name: Optional[str] = None
    color: Optional[str] = None
    created: Optional[datetime] = None
    last_modified: Optional[datetime] = None


class CalendarEventCreate(BaseModel):
    """Create calendar event"""
    summary: str
    description: Optional[str] = None
    location: Optional[str] = None
    start: datetime
    end: datetime
    all_day: bool = False


class CalendarEventUpdate(BaseModel):
    """Update calendar event"""
    summary: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    all_day: Optional[bool] = None


class CalendarListResponse(BaseModel):
    """Response for calendar listing"""
    calendars: List[CalendarInfo]


class EventListResponse(BaseModel):
    """Response for event listing"""
    events: List[CalendarEvent]
    start_date: datetime
    end_date: datetime


class EventResponse(BaseModel):
    """Response for single event"""
    event: CalendarEvent


class EventOperationResponse(BaseModel):
    """Generic response for event operations"""
    success: bool
    message: str
    uid: Optional[str] = None
