"""Calendar item models for meetings, reminders, notes, and blocked time"""
from sqlalchemy import Column, String, DateTime, Text, ForeignKey, Enum as SQLEnum, Integer, Date
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship
from .base import BaseModel
import enum


class CalendarItemType(str, enum.Enum):
    """Calendar item type enum"""
    MEETING = "MEETING"
    REMINDER = "REMINDER"
    NOTE = "NOTE"
    BLOCKED_TIME = "BLOCKED_TIME"


class RecurrencePattern(str, enum.Enum):
    """Recurrence pattern enum"""
    NONE = "NONE"
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    BIWEEKLY = "BIWEEKLY"
    MONTHLY = "MONTHLY"
    YEARLY = "YEARLY"


class CalendarItem(BaseModel):
    """Calendar item model for non-event calendar entries"""
    __tablename__ = "calendar_items"

    title = Column(String(255), nullable=False)
    item_type = Column(SQLEnum(CalendarItemType, name='calendar_item_type'), nullable=False)
    description = Column(Text, nullable=True)

    # Time fields
    start_at = Column(DateTime(timezone=True), nullable=False)
    end_at = Column(DateTime(timezone=True), nullable=True)  # Optional for reminders/notes

    # Recurrence fields
    recurrence_pattern = Column(SQLEnum(RecurrencePattern, name='recurrence_pattern'), default=RecurrencePattern.NONE, nullable=False)
    recurrence_end_date = Column(Date, nullable=True)  # When the recurrence stops (null = forever)
    recurrence_days_of_week = Column(ARRAY(Integer), nullable=True)  # For weekly: 0=Mon, 1=Tue, etc.
    parent_item_id = Column(UUID(as_uuid=True), ForeignKey('calendar_items.id', ondelete='CASCADE'), nullable=True)  # Links occurrences to parent

    # Location
    location_id = Column(UUID(as_uuid=True), ForeignKey('locations.id', ondelete='SET NULL'), nullable=True)

    # Ownership
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)

    # Relationships
    location = relationship("Location")
    creator = relationship("User", foreign_keys=[created_by])
    parent_item = relationship("CalendarItem", remote_side="CalendarItem.id", foreign_keys=[parent_item_id])

    def __repr__(self):
        return f"<CalendarItem(id={self.id}, type={self.item_type}, title={self.title})>"
