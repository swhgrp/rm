"""Event schemas (example)"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any
from datetime import datetime
from uuid import UUID
from events.models.event import EventStatus


class EventBase(BaseModel):
    """Base event schema"""
    title: str = Field(..., min_length=1, max_length=255)
    event_type: str = Field(..., max_length=100)
    venue_id: Optional[UUID] = None
    client_id: UUID
    start_at: datetime
    end_at: datetime
    guest_count: Optional[int] = None
    location: Optional[str] = None
    setup_start_at: Optional[datetime] = None
    teardown_end_at: Optional[datetime] = None
    menu_json: Optional[Dict[str, Any]] = None
    requirements_json: Optional[Dict[str, Any]] = None
    lead_source: Optional[str] = None


class EventCreate(EventBase):
    """Schema for creating an event"""
    external_ref: Optional[str] = None
    package_id: Optional[UUID] = None
    financials_json: Optional[Dict[str, Any]] = None


class EventUpdate(BaseModel):
    """Schema for updating an event"""
    title: Optional[str] = None
    event_type: Optional[str] = None
    status: Optional[EventStatus] = None
    venue_id: Optional[UUID] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    guest_count: Optional[int] = None
    location: Optional[str] = None  # Deprecated, use venue_id
    setup_start_at: Optional[datetime] = None
    teardown_end_at: Optional[datetime] = None
    menu_json: Optional[Dict[str, Any]] = None
    requirements_json: Optional[Dict[str, Any]] = None
    financials_json: Optional[Dict[str, Any]] = None
    client_id: Optional[UUID] = None


class VenueInfo(BaseModel):
    """Basic venue info for event response"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    capacity: Optional[int] = None


class ClientInfo(BaseModel):
    """Basic client info for event response"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: str
    phone: Optional[str] = None


class EventResponse(EventBase):
    """Schema for event response"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    external_ref: Optional[str] = None
    status: EventStatus
    package_id: Optional[UUID] = None
    financials_json: Optional[Dict[str, Any]] = None
    created_by: Optional[UUID] = None
    updated_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    venue: Optional[VenueInfo] = None
    client: Optional[ClientInfo] = None


class EventListItem(BaseModel):
    """Lightweight event for calendar/list views"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    event_type: str
    status: EventStatus
    start_at: datetime
    end_at: datetime
    guest_count: Optional[int] = None
    location: Optional[str] = None
    created_at: datetime
