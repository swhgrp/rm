"""Calendar item schemas"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime, date
from uuid import UUID
from events.models.calendar_item import CalendarItemType, RecurrencePattern


class CalendarItemBase(BaseModel):
    """Base calendar item schema"""
    title: str = Field(..., min_length=1, max_length=255)
    item_type: CalendarItemType
    description: Optional[str] = None
    start_at: datetime
    end_at: Optional[datetime] = None
    location_id: Optional[UUID] = None
    # Recurrence fields
    recurrence_pattern: RecurrencePattern = RecurrencePattern.NONE
    recurrence_end_date: Optional[date] = None
    recurrence_days_of_week: Optional[List[int]] = None  # 0=Mon, 1=Tue, etc.


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
    location_id: Optional[UUID] = None
    # Recurrence fields
    recurrence_pattern: Optional[RecurrencePattern] = None
    recurrence_end_date: Optional[date] = None
    recurrence_days_of_week: Optional[List[int]] = None


class LocationInfo(BaseModel):
    """Basic location info for calendar item response"""
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
    location: Optional[LocationInfo] = None
    creator: Optional[UserInfo] = None
    parent_item_id: Optional[UUID] = None
    is_occurrence: bool = False  # Computed field for virtual occurrences
