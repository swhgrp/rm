"""Event models"""
from sqlalchemy import Column, String, Integer, DateTime, Enum as SQLEnum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from .base import BaseModel
import enum


class EventStatus(str, enum.Enum):
    """Event status enum"""
    DRAFT = "draft"
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CLOSED = "closed"
    CANCELED = "canceled"


class Event(BaseModel):
    """Event model"""
    __tablename__ = "events"

    external_ref = Column(String(100), nullable=True, index=True)
    title = Column(String(255), nullable=False)
    event_type = Column(String(100), nullable=False)
    status = Column(SQLEnum(EventStatus), default=EventStatus.DRAFT, nullable=False, index=True)

    # Foreign keys
    venue_id = Column(UUID(as_uuid=True), ForeignKey('venues.id'), nullable=False)
    client_id = Column(UUID(as_uuid=True), ForeignKey('clients.id'), nullable=False)
    package_id = Column(UUID(as_uuid=True), ForeignKey('event_packages.id'), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    updated_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)

    # Timing
    start_at = Column(DateTime(timezone=True), nullable=False, index=True)
    end_at = Column(DateTime(timezone=True), nullable=False, index=True)
    setup_start_at = Column(DateTime(timezone=True), nullable=True)
    teardown_end_at = Column(DateTime(timezone=True), nullable=True)

    # Details
    guest_count = Column(Integer, nullable=True)
    lead_source = Column(String(100), nullable=True)

    # JSONB fields
    menu_json = Column(JSONB, nullable=True)  # {"items": [...], "special_requests": "..."}
    requirements_json = Column(JSONB, nullable=True)  # {"room_setup": "...", "av": [...], "equipment": [...]}
    financials_json = Column(JSONB, nullable=True)  # {"pricing": {...}, "deposits": [...], "taxes": {...}}

    # Relationships
    venue = relationship("Venue", back_populates="events")
    client = relationship("Client", back_populates="events")
    package = relationship("EventPackage", back_populates="events")
    creator = relationship("User", foreign_keys=[created_by], back_populates="created_events")
    tasks = relationship("Task", back_populates="event", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="event", cascade="all, delete-orphan")
    emails = relationship("Email", back_populates="event", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Event(id={self.id}, title={self.title}, status={self.status}, start_at={self.start_at})>"


class EventPackage(BaseModel):
    """Event package model"""
    __tablename__ = "event_packages"

    name = Column(String(255), nullable=False)
    event_type = Column(String(100), nullable=False)
    price_components_json = Column(JSONB, nullable=True)  # {"base": 5000, "per_guest": 50, "addons": [...]}

    # Relationships
    events = relationship("Event", back_populates="package")

    def __repr__(self):
        return f"<EventPackage(id={self.id}, name={self.name}, event_type={self.event_type})>"
