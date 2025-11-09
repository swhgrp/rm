"""Calendar item models for meetings, reminders, notes, and blocked time"""
from sqlalchemy import Column, String, DateTime, Text, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from .base import BaseModel
import enum


class CalendarItemType(str, enum.Enum):
    """Calendar item type enum"""
    MEETING = "MEETING"
    REMINDER = "REMINDER"
    NOTE = "NOTE"
    BLOCKED_TIME = "BLOCKED_TIME"


class CalendarItem(BaseModel):
    """Calendar item model for non-event calendar entries"""
    __tablename__ = "calendar_items"

    title = Column(String(255), nullable=False)
    item_type = Column(SQLEnum(CalendarItemType, name='calendar_item_type'), nullable=False)
    description = Column(Text, nullable=True)

    # Time fields
    start_at = Column(DateTime(timezone=True), nullable=False)
    end_at = Column(DateTime(timezone=True), nullable=True)  # Optional for reminders/notes

    # Location
    location_id = Column(UUID(as_uuid=True), ForeignKey('locations.id', ondelete='SET NULL'), nullable=True)

    # Ownership
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)

    # Relationships
    location = relationship("Location")
    creator = relationship("User", foreign_keys=[created_by])

    def __repr__(self):
        return f"<CalendarItem(id={self.id}, type={self.item_type}, title={self.title})>"
