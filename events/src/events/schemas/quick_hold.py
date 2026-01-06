"""Quick Hold schemas"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime
from uuid import UUID
from events.models.quick_hold import QuickHoldStatus, QuickHoldSource


class QuickHoldBase(BaseModel):
    """Base quick hold schema"""
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    start_at: datetime
    end_at: datetime
    all_day: bool = False
    location_text: Optional[str] = None


class QuickHoldCreate(QuickHoldBase):
    """Schema for creating a quick hold"""
    source: QuickHoldSource = QuickHoldSource.WEB_APP


class QuickHoldCreateFromCalDAV(BaseModel):
    """Schema for creating a quick hold from CalDAV sync"""
    title: str
    description: Optional[str] = None
    start_at: datetime
    end_at: datetime
    all_day: bool = False
    location_text: Optional[str] = None
    caldav_uid: str
    caldav_etag: Optional[str] = None
    caldav_href: Optional[str] = None


class QuickHoldUpdate(BaseModel):
    """Schema for updating a quick hold"""
    title: Optional[str] = None
    description: Optional[str] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    all_day: Optional[bool] = None
    location_text: Optional[str] = None
    status: Optional[QuickHoldStatus] = None


class QuickHoldResponse(QuickHoldBase):
    """Schema for quick hold response"""
    id: UUID
    status: QuickHoldStatus
    source: QuickHoldSource
    caldav_uid: Optional[str] = None
    created_by: Optional[UUID] = None
    converted_to_event_id: Optional[UUID] = None
    converted_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class QuickHoldListResponse(BaseModel):
    """Schema for listing quick holds"""
    items: list[QuickHoldResponse]
    total: int


class ConvertToEventRequest(BaseModel):
    """Schema for converting a quick hold to an event"""
    event_type: str = Field(..., description="Event type (Wedding, Corporate, etc.)")
    venue_id: UUID = Field(..., description="Venue ID")
    client_id: Optional[UUID] = Field(None, description="Existing client ID, or create new if not provided")
    # If no client_id, create a new client with these fields
    client_name: Optional[str] = None
    client_email: Optional[str] = None
    client_phone: Optional[str] = None
    client_organization: Optional[str] = None
    guest_count: Optional[int] = None
