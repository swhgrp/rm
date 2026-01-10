"""SQLAlchemy models for Maintenance & Equipment Tracking Service"""
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean,
    ForeignKey, Numeric, Enum, Date, Index
)
from sqlalchemy.orm import relationship
from maintenance.database import Base


class EquipmentStatus(str, PyEnum):
    """Equipment operational status"""
    OPERATIONAL = "operational"
    NEEDS_MAINTENANCE = "needs_maintenance"
    UNDER_REPAIR = "under_repair"
    OUT_OF_SERVICE = "out_of_service"
    RETIRED = "retired"


class WorkOrderStatus(str, PyEnum):
    """Work order status"""
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    ON_HOLD = "on_hold"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class WorkOrderPriority(str, PyEnum):
    """Work order priority levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ScheduleFrequency(str, PyEnum):
    """Maintenance schedule frequency"""
    DAILY = "daily"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    SEMIANNUAL = "semiannual"
    ANNUAL = "annual"
    CUSTOM = "custom"


class EquipmentCategory(Base):
    """Equipment categories for organization"""
    __tablename__ = "equipment_categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    parent_id = Column(Integer, ForeignKey("equipment_categories.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    parent = relationship("EquipmentCategory", remote_side=[id], backref="subcategories")
    equipment = relationship("Equipment", back_populates="category")


class Equipment(Base):
    """Equipment/asset tracking"""
    __tablename__ = "equipment"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    category_id = Column(Integer, ForeignKey("equipment_categories.id"), nullable=True)
    location_id = Column(Integer, nullable=False, index=True)  # References locations in inventory service

    # Identification
    serial_number = Column(String(100), nullable=True, index=True)
    model_number = Column(String(100), nullable=True)
    manufacturer = Column(String(200), nullable=True)
    qr_code = Column(String(100), unique=True, index=True)  # Generated unique QR code identifier

    # Status and dates
    status = Column(Enum(EquipmentStatus), default=EquipmentStatus.OPERATIONAL, nullable=False)
    purchase_date = Column(Date, nullable=True)
    warranty_expiration = Column(Date, nullable=True)
    installation_date = Column(Date, nullable=True)
    last_maintenance_date = Column(Date, nullable=True)
    next_maintenance_date = Column(Date, nullable=True)

    # Financial
    purchase_cost = Column(Numeric(12, 2), nullable=True)

    # Additional info
    notes = Column(Text)
    specifications = Column(Text)  # JSON string for flexible specs

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(Integer, nullable=True)  # User ID from portal

    # Relationships
    category = relationship("EquipmentCategory", back_populates="equipment")
    work_orders = relationship("WorkOrder", back_populates="equipment")
    maintenance_schedules = relationship("MaintenanceSchedule", back_populates="equipment")
    history = relationship("EquipmentHistory", back_populates="equipment", order_by="desc(EquipmentHistory.created_at)")

    __table_args__ = (
        Index("ix_equipment_location_status", "location_id", "status"),
    )


class EquipmentHistory(Base):
    """History/audit log for equipment changes"""
    __tablename__ = "equipment_history"

    id = Column(Integer, primary_key=True, index=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id"), nullable=False, index=True)
    changed_by = Column(Integer, nullable=True)  # User ID from portal
    change_type = Column(String(50), nullable=False)  # status_change, maintenance, repair, etc.
    old_value = Column(Text)
    new_value = Column(Text)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    equipment = relationship("Equipment", back_populates="history")


class MaintenanceSchedule(Base):
    """Preventive maintenance schedules"""
    __tablename__ = "maintenance_schedules"

    id = Column(Integer, primary_key=True, index=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text)

    # Schedule configuration
    frequency = Column(Enum(ScheduleFrequency), nullable=False)
    custom_interval_days = Column(Integer, nullable=True)  # For custom frequency
    last_performed = Column(Date, nullable=True)
    next_due = Column(Date, nullable=False)

    # Task details
    estimated_duration_minutes = Column(Integer, nullable=True)
    checklist = Column(Text)  # JSON string for checklist items

    # Assignment
    assigned_to = Column(Integer, nullable=True)  # User ID or vendor ID
    is_external = Column(Boolean, default=False)  # External vendor vs internal staff

    # Status
    is_active = Column(Boolean, default=True)

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    equipment = relationship("Equipment", back_populates="maintenance_schedules")


class WorkOrder(Base):
    """Work orders for repairs and maintenance"""
    __tablename__ = "work_orders"

    id = Column(Integer, primary_key=True, index=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id"), nullable=True, index=True)
    schedule_id = Column(Integer, ForeignKey("maintenance_schedules.id"), nullable=True)

    # Work order details
    title = Column(String(200), nullable=False)
    description = Column(Text)
    priority = Column(Enum(WorkOrderPriority), default=WorkOrderPriority.MEDIUM, nullable=False)
    status = Column(Enum(WorkOrderStatus), default=WorkOrderStatus.OPEN, nullable=False)

    # Location (can be different from equipment location for general facility work)
    location_id = Column(Integer, nullable=False, index=True)

    # Assignment
    reported_by = Column(Integer, nullable=True)  # User ID
    assigned_to = Column(Integer, nullable=True)  # User ID or vendor ID
    is_external = Column(Boolean, default=False)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=True)

    # Dates
    reported_date = Column(DateTime, default=datetime.utcnow)
    due_date = Column(Date, nullable=True)
    started_date = Column(DateTime, nullable=True)
    completed_date = Column(DateTime, nullable=True)

    # Resolution
    resolution_notes = Column(Text)
    root_cause = Column(Text)

    # Costs
    estimated_cost = Column(Numeric(12, 2), nullable=True)
    actual_cost = Column(Numeric(12, 2), nullable=True)
    labor_hours = Column(Numeric(6, 2), nullable=True)

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    equipment = relationship("Equipment", back_populates="work_orders")
    schedule = relationship("MaintenanceSchedule")
    vendor = relationship("Vendor", back_populates="work_orders")
    comments = relationship("WorkOrderComment", back_populates="work_order", order_by="WorkOrderComment.created_at")
    parts_used = relationship("WorkOrderPart", back_populates="work_order")

    __table_args__ = (
        Index("ix_work_orders_status_priority", "status", "priority"),
        Index("ix_work_orders_location_status", "location_id", "status"),
    )


class WorkOrderComment(Base):
    """Comments/updates on work orders"""
    __tablename__ = "work_order_comments"

    id = Column(Integer, primary_key=True, index=True)
    work_order_id = Column(Integer, ForeignKey("work_orders.id"), nullable=False, index=True)
    user_id = Column(Integer, nullable=True)
    comment = Column(Text, nullable=False)
    is_internal = Column(Boolean, default=False)  # Internal notes vs visible to all
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    work_order = relationship("WorkOrder", back_populates="comments")


class WorkOrderPart(Base):
    """Parts/materials used in work orders"""
    __tablename__ = "work_order_parts"

    id = Column(Integer, primary_key=True, index=True)
    work_order_id = Column(Integer, ForeignKey("work_orders.id"), nullable=False, index=True)
    part_name = Column(String(200), nullable=False)
    part_number = Column(String(100), nullable=True)
    quantity = Column(Numeric(10, 2), nullable=False)
    unit_cost = Column(Numeric(12, 2), nullable=True)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    work_order = relationship("WorkOrder", back_populates="parts_used")


class Vendor(Base):
    """External service vendors"""
    __tablename__ = "vendors"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    contact_name = Column(String(200), nullable=True)
    phone = Column(String(50), nullable=True)
    email = Column(String(200), nullable=True)
    address = Column(Text)

    # Service details
    service_types = Column(Text)  # JSON array of service types
    contract_number = Column(String(100), nullable=True)
    contract_expiration = Column(Date, nullable=True)

    # Status
    is_active = Column(Boolean, default=True)
    notes = Column(Text)

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    work_orders = relationship("WorkOrder", back_populates="vendor")
