"""HACCP (Hazard Analysis Critical Control Points) models for Food Safety Service"""
from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean,
    ForeignKey, Date, Numeric, Index
)
from sqlalchemy.orm import relationship
from food_safety.database import Base


class HACCPPlan(Base):
    """HACCP plan definitions per location"""
    __tablename__ = "haccp_plans"

    id = Column(Integer, primary_key=True, index=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False, index=True)

    # Plan details
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    # Version control
    version = Column(String(20), nullable=False, default="1.0")
    effective_date = Column(Date, nullable=False)
    review_date = Column(Date, nullable=True)  # Next scheduled review

    # Status
    is_active = Column(Boolean, default=True)

    # Approval
    approved_by = Column(Integer, nullable=True)  # HR user ID
    approved_at = Column(DateTime, nullable=True)

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(Integer, nullable=True)

    # Relationships
    critical_control_points = relationship("CriticalControlPoint", back_populates="haccp_plan",
                                          cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_haccp_plans_location_active", "location_id", "is_active"),
    )


class CriticalControlPoint(Base):
    """Critical Control Points within HACCP plans"""
    __tablename__ = "critical_control_points"

    id = Column(Integer, primary_key=True, index=True)
    haccp_plan_id = Column(Integer, ForeignKey("haccp_plans.id"), nullable=False, index=True)

    # CCP identification
    ccp_number = Column(String(20), nullable=False)  # e.g., "CCP-1", "CCP-2"
    name = Column(String(200), nullable=False)

    # Process step
    process_step = Column(String(200), nullable=False)
    hazard_description = Column(Text, nullable=False)

    # Critical limits
    critical_limits = Column(Text, nullable=False)  # Description of critical limits

    # For temperature-based CCPs
    min_temp = Column(Numeric(5, 2), nullable=True)
    max_temp = Column(Numeric(5, 2), nullable=True)
    temp_unit = Column(String(1), default="F")

    # Time limits
    max_time_minutes = Column(Integer, nullable=True)

    # Monitoring
    monitoring_procedure = Column(Text, nullable=False)
    monitoring_frequency = Column(String(100), nullable=False)  # e.g., "Every 2 hours", "Each batch"

    # Corrective actions if limits exceeded
    corrective_action_procedure = Column(Text, nullable=False)

    # Verification
    verification_procedure = Column(Text, nullable=True)

    # Recordkeeping
    records_required = Column(Text, nullable=True)

    # Display order
    sort_order = Column(Integer, default=0)

    # Status
    is_active = Column(Boolean, default=True)

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    haccp_plan = relationship("HACCPPlan", back_populates="critical_control_points")
