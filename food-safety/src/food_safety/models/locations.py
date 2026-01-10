"""Location and equipment threshold models for Food Safety Service"""
from datetime import datetime, time
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean,
    ForeignKey, Numeric, Time, Index
)
from sqlalchemy.orm import relationship
from food_safety.database import Base


class Location(Base):
    """Restaurant locations (synced from inventory service)"""
    __tablename__ = "locations"

    id = Column(Integer, primary_key=True, index=True)
    inventory_location_id = Column(Integer, nullable=False, unique=True, index=True)  # From inventory service

    name = Column(String(200), nullable=False)
    address = Column(Text, nullable=True)

    # Status
    is_active = Column(Boolean, default=True)

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    shifts = relationship("Shift", back_populates="location", cascade="all, delete-orphan")
    equipment_thresholds = relationship("EquipmentTempThreshold", back_populates="location", cascade="all, delete-orphan")


class Shift(Base):
    """Configurable shifts per location"""
    __tablename__ = "shifts"

    id = Column(Integer, primary_key=True, index=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False, index=True)

    name = Column(String(100), nullable=False)  # e.g., "Morning", "Afternoon", "Evening"
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)

    # Status
    is_active = Column(Boolean, default=True)

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    location = relationship("Location", back_populates="shifts")

    __table_args__ = (
        Index("ix_shifts_location_active", "location_id", "is_active"),
    )


class EquipmentTempThreshold(Base):
    """Temperature thresholds for equipment (references equipment in Maintenance service)"""
    __tablename__ = "equipment_temp_thresholds"

    id = Column(Integer, primary_key=True, index=True)

    # Reference to Maintenance service equipment
    maintenance_equipment_id = Column(Integer, nullable=False, unique=True, index=True)

    # Location reference (for easier querying)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False, index=True)

    # Equipment info cached from Maintenance (for display when service unavailable)
    equipment_name = Column(String(200), nullable=False)
    equipment_type = Column(String(100), nullable=True)  # cooler, freezer, hot_holding

    # Temperature thresholds (override defaults)
    min_temp = Column(Numeric(5, 2), nullable=True)
    max_temp = Column(Numeric(5, 2), nullable=True)
    temp_unit = Column(String(1), default="F")  # F or C

    # Alert settings
    alert_on_violation = Column(Boolean, default=True)

    # Status
    is_active = Column(Boolean, default=True)

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    location = relationship("Location", back_populates="equipment_thresholds")

    __table_args__ = (
        Index("ix_eq_thresholds_location_active", "location_id", "is_active"),
    )
