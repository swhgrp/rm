"""Calendar item schemas"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime
from uuid import UUID
from events.models.calendar_item import CalendarItemType


class CalendarItemBase(BaseModel):
    """Base calendar item schema"""
    title: str = Field(..., min_length=1, max_length=255)
    item_type: CalendarItemType
    description: Optional[str] = None
    start_at: datetime
    end_at: Optional[datetime] = None
    venue_id: Optional[UUID] = None


class CalendarItemCreate(CalendarItemBase):
    """Schema for creating a calendar item"""
    pass


class CalendarItemUpdate(BaseModel):
    """Schema for updating a calendar item"""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    item_type: Optional[CalendarItemType] = None
    description: Optional[str] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    venue_id: Optional[UUID] = None


class VenueInfo(BaseModel):
    """Basic venue info for calendar item response"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    color: Optional[str] = None


class UserInfo(BaseModel):
    """Basic user info for calendar item response"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str


class CalendarItemResponse(CalendarItemBase):
    """Schema for calendar item response"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    venue: Optional[VenueInfo] = None
    creator: Optional[UserInfo] = None
