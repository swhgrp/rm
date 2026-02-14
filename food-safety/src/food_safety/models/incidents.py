"""Incident tracking models for Safety & Compliance Service"""
from datetime import datetime, date
from enum import Enum as PyEnum
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean,
    ForeignKey, Date, Enum, Index
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from food_safety.database import Base


class IncidentType(str, PyEnum):
    """Types of safety incidents"""
    # Food Safety Incidents
    TEMPERATURE_VIOLATION = "temperature_violation"
    CONTAMINATION = "contamination"
    FOREIGN_OBJECT = "foreign_object"
    PEST_SIGHTING = "pest_sighting"
    EQUIPMENT_FAILURE = "equipment_failure"
    EMPLOYEE_ILLNESS = "employee_illness"
    CUSTOMER_COMPLAINT = "customer_complaint"
    ALLERGEN_ISSUE = "allergen_issue"
    CROSS_CONTAMINATION = "cross_contamination"
    IMPROPER_STORAGE = "improper_storage"
    HYGIENE_VIOLATION = "hygiene_violation"
    # General Workplace Safety Incidents
    WORKPLACE_INJURY = "workplace_injury"
    SLIP_FALL = "slip_fall"
    BURN = "burn"
    CUT_LACERATION = "cut_laceration"
    CHEMICAL_EXPOSURE = "chemical_exposure"
    FIRE_HAZARD = "fire_hazard"
    ELECTRICAL_HAZARD = "electrical_hazard"
    PROPERTY_DAMAGE = "property_damage"
    NEAR_MISS = "near_miss"
    SECURITY_INCIDENT = "security_incident"
    CUSTOMER_INJURY = "customer_injury"
    VEHICLE_INCIDENT = "vehicle_incident"
    OTHER = "other"


class IncidentCategory(str, PyEnum):
    """Category of incidents"""
    FOOD_SAFETY = "food_safety"
    WORKPLACE_SAFETY = "workplace_safety"
    SECURITY = "security"
    GENERAL = "general"


class IncidentStatus(str, PyEnum):
    """Status of safety incidents"""
    OPEN = "open"
    INVESTIGATING = "investigating"
    ACTION_REQUIRED = "action_required"
    RESOLVED = "resolved"
    CLOSED = "closed"


class CorrectiveActionStatus(str, PyEnum):
    """Status of corrective actions"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    VERIFIED = "verified"


class Incident(Base):
    """Safety incident records"""
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, index=True)

    # Auto-generated incident number (INC-YYYY-NNNN)
    incident_number = Column(String(20), nullable=False, unique=True, index=True)

    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False, index=True)

    # Incident details
    category = Column(Enum(IncidentCategory), default=IncidentCategory.FOOD_SAFETY, nullable=False, index=True)
    incident_type = Column(Enum(IncidentType), nullable=False)
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=False)

    # Date/time
    incident_date = Column(Date, nullable=False, index=True)
    incident_time = Column(String(10), nullable=True)  # HH:MM format

    # Status
    status = Column(Enum(IncidentStatus), default=IncidentStatus.OPEN, nullable=False)

    # Severity
    severity = Column(String(20), nullable=False)  # "low", "medium", "high", "critical"

    # Product/area involved
    product_involved = Column(String(200), nullable=True)
    area_involved = Column(String(200), nullable=True)
    extra_data = Column(JSONB, nullable=True, default=dict, server_default='{}')

    # Reporting
    reported_by = Column(Integer, nullable=False)  # HR user ID
    reported_at = Column(DateTime, default=datetime.utcnow)

    # Investigation
    investigated_by = Column(Integer, nullable=True)  # HR user ID
    investigation_notes = Column(Text, nullable=True)
    root_cause = Column(Text, nullable=True)

    # Resolution
    resolved_by = Column(Integer, nullable=True)  # HR user ID
    resolved_at = Column(DateTime, nullable=True)
    resolution_notes = Column(Text, nullable=True)

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    corrective_actions = relationship("CorrectiveAction", back_populates="incident", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_incidents_location_date", "location_id", "incident_date"),
        Index("ix_incidents_type_status", "incident_type", "status"),
        Index("ix_incidents_status", "status"),
    )


class CorrectiveAction(Base):
    """Corrective actions for incidents and inspection violations"""
    __tablename__ = "corrective_actions"

    id = Column(Integer, primary_key=True, index=True)

    # Can be linked to incident or inspection violation
    incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=True, index=True)
    inspection_violation_id = Column(Integer, ForeignKey("inspection_violations.id"), nullable=True, index=True)

    # Action details
    action_description = Column(Text, nullable=False)

    # Assignment
    assigned_to = Column(Integer, nullable=True)  # HR user ID
    due_date = Column(Date, nullable=True)

    # Status
    status = Column(Enum(CorrectiveActionStatus), default=CorrectiveActionStatus.PENDING, nullable=False)

    # Completion
    completed_by = Column(Integer, nullable=True)  # HR user ID
    completed_at = Column(DateTime, nullable=True)
    completion_notes = Column(Text, nullable=True)

    # Verification
    verified_by = Column(Integer, nullable=True)  # HR user ID (manager)
    verified_at = Column(DateTime, nullable=True)
    verification_notes = Column(Text, nullable=True)

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    incident = relationship("Incident", back_populates="corrective_actions")
    inspection_violation = relationship("InspectionViolation", back_populates="corrective_actions")

    __table_args__ = (
        Index("ix_corrective_actions_status", "status"),
        Index("ix_corrective_actions_due_date", "due_date"),
    )
