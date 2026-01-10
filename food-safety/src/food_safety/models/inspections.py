"""Inspection and compliance models for Food Safety Service"""
from datetime import datetime, date
from enum import Enum as PyEnum
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean,
    ForeignKey, Date, Numeric, Enum, Index
)
from sqlalchemy.orm import relationship
from food_safety.database import Base


class InspectionType(str, PyEnum):
    """Types of inspections"""
    HEALTH_DEPARTMENT = "health_department"
    INTERNAL_AUDIT = "internal_audit"
    CORPORATE = "corporate"
    THIRD_PARTY = "third_party"
    SELF_INSPECTION = "self_inspection"


class ViolationSeverity(str, PyEnum):
    """Severity of inspection violations"""
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    OBSERVATION = "observation"


class Inspection(Base):
    """Health inspection records"""
    __tablename__ = "inspections"

    id = Column(Integer, primary_key=True, index=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False, index=True)

    # Inspection details
    inspection_type = Column(Enum(InspectionType), nullable=False)
    inspection_date = Column(Date, nullable=False, index=True)

    # Inspector info
    inspector_name = Column(String(200), nullable=True)
    inspector_agency = Column(String(200), nullable=True)

    # Results
    score = Column(Numeric(5, 2), nullable=True)  # Numeric score if applicable
    grade = Column(String(10), nullable=True)     # Letter grade if applicable (A, B, C, etc.)
    passed = Column(Boolean, nullable=True)

    # Follow-up
    follow_up_required = Column(Boolean, default=False)
    follow_up_date = Column(Date, nullable=True)
    follow_up_notes = Column(Text, nullable=True)

    # Documentation
    notes = Column(Text, nullable=True)
    report_url = Column(String(500), nullable=True)  # Link to uploaded report

    # Recorded by
    recorded_by = Column(Integer, nullable=True)  # HR user ID

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    violations = relationship("InspectionViolation", back_populates="inspection", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_inspections_location_date", "location_id", "inspection_date"),
        Index("ix_inspections_type", "inspection_type"),
    )


class InspectionViolation(Base):
    """Violations found during inspections"""
    __tablename__ = "inspection_violations"

    id = Column(Integer, primary_key=True, index=True)
    inspection_id = Column(Integer, ForeignKey("inspections.id"), nullable=False, index=True)

    # Violation details
    code = Column(String(50), nullable=True)  # Health code reference
    description = Column(Text, nullable=False)
    severity = Column(Enum(ViolationSeverity), nullable=False)

    # Location within restaurant
    area = Column(String(100), nullable=True)

    # Corrective action deadline
    correction_deadline = Column(Date, nullable=True)

    # Status
    is_corrected = Column(Boolean, default=False)
    corrected_at = Column(DateTime, nullable=True)

    # Notes
    notes = Column(Text, nullable=True)

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    inspection = relationship("Inspection", back_populates="violations")
    corrective_actions = relationship("CorrectiveAction", back_populates="inspection_violation")

    __table_args__ = (
        Index("ix_inspection_violations_severity", "severity"),
        Index("ix_inspection_violations_corrected", "is_corrected"),
    )
