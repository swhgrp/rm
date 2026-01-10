"""Checklist models for Food Safety Service"""
from datetime import datetime, date
from enum import Enum as PyEnum
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean,
    ForeignKey, Date, Enum, Index
)
from sqlalchemy.orm import relationship
from food_safety.database import Base


class ChecklistType(str, PyEnum):
    """Types of food safety checklists"""
    OPENING = "opening"
    CLOSING = "closing"
    SHIFT_CHANGE = "shift_change"
    TEMPERATURE = "temperature"
    CLEANING = "cleaning"
    RECEIVING = "receiving"
    PREP = "prep"
    CUSTOM = "custom"


class ChecklistStatus(str, PyEnum):
    """Status of checklist submissions"""
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    PENDING_SIGNOFF = "pending_signoff"
    SIGNED_OFF = "signed_off"
    REJECTED = "rejected"


class ChecklistTemplate(Base):
    """Reusable checklist definitions"""
    __tablename__ = "checklist_templates"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    checklist_type = Column(Enum(ChecklistType), nullable=False)

    # Location assignment (NULL means all locations)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True, index=True)

    # Shift assignment (NULL means all shifts)
    shift_id = Column(Integer, ForeignKey("shifts.id"), nullable=True)

    # Schedule
    frequency = Column(String(50), nullable=False)  # "daily", "weekly", "monthly", "per_shift"

    # Manager sign-off requirement (configurable per checklist type)
    requires_manager_signoff = Column(Boolean, default=False)

    # Status
    is_active = Column(Boolean, default=True)

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(Integer, nullable=True)

    # Relationships
    items = relationship("ChecklistItem", back_populates="template", cascade="all, delete-orphan",
                        order_by="ChecklistItem.sort_order")
    submissions = relationship("ChecklistSubmission", back_populates="template")

    __table_args__ = (
        Index("ix_checklist_templates_type_active", "checklist_type", "is_active"),
        Index("ix_checklist_templates_location", "location_id", "is_active"),
    )


class ChecklistItem(Base):
    """Individual items within a checklist template"""
    __tablename__ = "checklist_items"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("checklist_templates.id"), nullable=False, index=True)

    # Item details
    text = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)  # Help text or instructions

    # Response type
    response_type = Column(String(50), nullable=False)  # "yes_no", "pass_fail", "numeric", "text", "temperature"

    # For numeric responses
    min_value = Column(String(50), nullable=True)  # Can be numeric or text threshold
    max_value = Column(String(50), nullable=True)

    # Required field
    is_required = Column(Boolean, default=True)

    # Display order
    sort_order = Column(Integer, default=0)

    # Section grouping
    section = Column(String(100), nullable=True)

    # Corrective action required if failed
    requires_corrective_action = Column(Boolean, default=True)

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    template = relationship("ChecklistTemplate", back_populates="items")
    responses = relationship("ChecklistResponse", back_populates="item")


class ChecklistSubmission(Base):
    """Completed checklist instances"""
    __tablename__ = "checklist_submissions"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("checklist_templates.id"), nullable=False, index=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False, index=True)

    # Submission details
    submission_date = Column(Date, nullable=False, index=True)
    shift_id = Column(Integer, ForeignKey("shifts.id"), nullable=True)

    # Status
    status = Column(Enum(ChecklistStatus), default=ChecklistStatus.IN_PROGRESS, nullable=False)

    # Completion details
    completed_by = Column(Integer, nullable=True)  # HR user ID
    completed_at = Column(DateTime, nullable=True)

    # Overall notes
    notes = Column(Text, nullable=True)

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    template = relationship("ChecklistTemplate", back_populates="submissions")
    responses = relationship("ChecklistResponse", back_populates="submission", cascade="all, delete-orphan")
    signoffs = relationship("ManagerSignoff", back_populates="submission", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_checklist_submissions_location_date", "location_id", "submission_date"),
        Index("ix_checklist_submissions_status", "status"),
    )


class ChecklistResponse(Base):
    """Responses to individual checklist items"""
    __tablename__ = "checklist_responses"

    id = Column(Integer, primary_key=True, index=True)
    submission_id = Column(Integer, ForeignKey("checklist_submissions.id"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("checklist_items.id"), nullable=False, index=True)

    # Response value
    response_value = Column(String(500), nullable=True)  # Stores all response types as string
    is_passing = Column(Boolean, nullable=True)  # NULL for non-pass/fail items

    # Corrective action if failed
    corrective_action = Column(Text, nullable=True)

    # Notes
    notes = Column(Text, nullable=True)

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow)
    responded_by = Column(Integer, nullable=True)  # HR user ID

    # Relationships
    submission = relationship("ChecklistSubmission", back_populates="responses")
    item = relationship("ChecklistItem", back_populates="responses")


class ManagerSignoff(Base):
    """Manager sign-offs for checklists requiring approval"""
    __tablename__ = "manager_signoffs"

    id = Column(Integer, primary_key=True, index=True)
    submission_id = Column(Integer, ForeignKey("checklist_submissions.id"), nullable=False, index=True)

    # Sign-off details
    signed_off_by = Column(Integer, nullable=False)  # HR user ID (must have signoff permission)
    signed_off_at = Column(DateTime, default=datetime.utcnow)

    # Approval
    is_approved = Column(Boolean, nullable=False)
    rejection_reason = Column(Text, nullable=True)

    # Notes
    notes = Column(Text, nullable=True)

    # Relationships
    submission = relationship("ChecklistSubmission", back_populates="signoffs")
