"""Quick Hold model for phone-created calendar entries"""
from sqlalchemy import Column, String, DateTime, Enum as SQLEnum, ForeignKey, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from .base import BaseModel
import enum


class QuickHoldStatus(str, enum.Enum):
    """Quick hold status enum"""
    HOLD = "HOLD"  # Active hold
    CONVERTED = "CONVERTED"  # Converted to full event
    CANCELED = "CANCELED"  # Canceled/removed


class QuickHoldSource(str, enum.Enum):
    """Source of the quick hold"""
    PHONE_CALENDAR = "PHONE_CALENDAR"  # Created via CalDAV from phone
    WEB_APP = "WEB_APP"  # Created in Events web app
    MANUAL = "MANUAL"  # Manually created


class QuickHold(BaseModel):
    """
    Quick Hold model for placeholder calendar entries.

    These are lightweight entries created from phone calendars or quickly
    in the app to hold a date/time. They can later be converted to full Events.

    Key differences from Events:
    - No client required
    - No venue required (just optional text)
    - No guest count, menu, financials, etc.
    - Simple status: HOLD, CONVERTED, CANCELED
    """
    __tablename__ = "quick_holds"

    # Basic info
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)  # Notes from calendar

    # Timing
    start_at = Column(DateTime(timezone=True), nullable=False, index=True)
    end_at = Column(DateTime(timezone=True), nullable=False, index=True)
    all_day = Column(Boolean, default=False)  # All-day event flag

    # Location (optional text, not a venue FK)
    location_text = Column(String(255), nullable=True)

    # Status and source tracking
    status = Column(SQLEnum(QuickHoldStatus), default=QuickHoldStatus.HOLD, nullable=False, index=True)
    source = Column(SQLEnum(QuickHoldSource), default=QuickHoldSource.PHONE_CALENDAR, nullable=False)

    # CalDAV tracking
    caldav_uid = Column(String(255), nullable=True, unique=True, index=True)  # UID from iCalendar
    caldav_etag = Column(String(255), nullable=True)  # ETag for change detection
    caldav_href = Column(String(500), nullable=True)  # Full CalDAV path to the event

    # Who created it
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)

    # If converted to an event, track which one
    converted_to_event_id = Column(UUID(as_uuid=True), ForeignKey('events.id'), nullable=True)
    converted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    creator = relationship("User", foreign_keys=[created_by])
    converted_event = relationship("Event", foreign_keys=[converted_to_event_id])

    def __repr__(self):
        return f"<QuickHold {self.title} on {self.start_at}>"
