"""Temperature logging models for Food Safety Service"""
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean,
    ForeignKey, Numeric, Enum, Index
)
from sqlalchemy.orm import relationship
from food_safety.database import Base


class TemperatureAlertStatus(str, PyEnum):
    """Status of temperature alerts"""
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class TemperatureLog(Base):
    """Individual temperature readings"""
    __tablename__ = "temperature_logs"

    id = Column(Integer, primary_key=True, index=True)

    # Reference to Maintenance service equipment (not a foreign key - external service)
    maintenance_equipment_id = Column(Integer, nullable=False, index=True)
    equipment_name = Column(String(200), nullable=False)  # Cached for display

    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False, index=True)

    # Temperature reading
    temperature = Column(Numeric(5, 2), nullable=False)
    temp_unit = Column(String(1), default="F")  # F or C

    # Threshold comparison (at time of logging)
    min_threshold = Column(Numeric(5, 2), nullable=True)
    max_threshold = Column(Numeric(5, 2), nullable=True)
    is_within_range = Column(Boolean, nullable=False)

    # Alert handling
    alert_status = Column(Enum(TemperatureAlertStatus), nullable=True)  # NULL if within range
    alert_acknowledged_by = Column(Integer, nullable=True)  # HR user ID
    alert_acknowledged_at = Column(DateTime, nullable=True)
    alert_notes = Column(Text, nullable=True)

    # Corrective action taken if out of range
    corrective_action = Column(Text, nullable=True)

    # Logging details
    logged_by = Column(Integer, nullable=False)  # HR user ID
    logged_at = Column(DateTime, default=datetime.utcnow, index=True)
    shift_id = Column(Integer, ForeignKey("shifts.id"), nullable=True)

    # Notes
    notes = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_temp_logs_equipment_date", "maintenance_equipment_id", "logged_at"),
        Index("ix_temp_logs_location_date", "location_id", "logged_at"),
        Index("ix_temp_logs_alert_status", "alert_status"),
    )


class TemperatureThreshold(Base):
    """Default temperature thresholds by equipment type"""
    __tablename__ = "temperature_thresholds"

    id = Column(Integer, primary_key=True, index=True)
    equipment_type = Column(String(100), nullable=False, unique=True, index=True)

    # Threshold values
    min_temp = Column(Numeric(5, 2), nullable=False)
    max_temp = Column(Numeric(5, 2), nullable=False)
    temp_unit = Column(String(1), default="F")

    # Description
    name = Column(String(200), nullable=False)  # e.g., "Walk-in Cooler"
    description = Column(Text, nullable=True)

    # Alert settings
    alert_on_violation = Column(Boolean, default=True)

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
