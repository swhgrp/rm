"""
Count Session models for tracking physical inventory counts with workflow
"""

from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean, Numeric, Text, Enum as SQLEnum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from restaurant_inventory.db.database import Base
import enum

class CountStatus(str, enum.Enum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    APPROVED = "APPROVED"
    CANCELLED = "CANCELLED"

class InventoryType(str, enum.Enum):
    FULL = "FULL"  # All items must be counted, uncounted items default to 0
    PARTIAL = "PARTIAL"  # Only entered items are updated

class CountSession(Base):
    __tablename__ = "count_sessions"

    id = Column(Integer, primary_key=True, index=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)  # Count is for entire location
    storage_area_id = Column(Integer, ForeignKey("storage_areas.id"), nullable=True)  # Legacy: not used in new workflow
    template_id = Column(Integer, ForeignKey("count_templates.id"), nullable=True)  # Optional: count may not use template

    name = Column(String, nullable=True)  # Optional: "Weekly Count - Main Bar - Jan 15"
    inventory_type = Column(SQLEnum(InventoryType), default=InventoryType.PARTIAL, nullable=False)  # FULL or PARTIAL
    status = Column(SQLEnum(CountStatus), default=CountStatus.IN_PROGRESS, nullable=False)
    locked = Column(Boolean, default=False)  # Lock editing after approval

    # Workflow tracking
    started_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    started_at = Column(DateTime(timezone=True), server_default=func.now())

    completed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)

    notes = Column(Text, nullable=True)

    # Relationships
    location = relationship("Location")
    storage_area = relationship("StorageArea")
    template = relationship("CountTemplate")
    started_by_user = relationship("User", foreign_keys=[started_by])
    completed_by_user = relationship("User", foreign_keys=[completed_by])
    approved_by_user = relationship("User", foreign_keys=[approved_by])
    items = relationship("CountSessionItem", back_populates="session", cascade="all, delete-orphan")


class CountSessionItem(Base):
    __tablename__ = "count_session_items"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("count_sessions.id"), nullable=False)
    storage_area_id = Column(Integer, ForeignKey("storage_areas.id"), nullable=True)  # Which storage area this count is for
    master_item_id = Column(Integer, ForeignKey("master_items.id"), nullable=False)
    inventory_id = Column(Integer, ForeignKey("inventory.id"), nullable=True)  # Link to inventory record

    # Count data
    expected_quantity = Column(Numeric(10, 3), nullable=True)  # From last count or inventory record
    counted_quantity = Column(Numeric(10, 3), nullable=True)  # Actual physical count
    variance = Column(Numeric(10, 3), nullable=True)  # counted - expected
    variance_percent = Column(Numeric(5, 2), nullable=True)  # (variance / expected) * 100

    # Flags and notes
    flagged = Column(Boolean, default=False)  # Flagged for review due to large discrepancy
    is_new_item = Column(Boolean, default=False)  # Item added during count (not in template)
    notes = Column(Text, nullable=True)

    counted_at = Column(DateTime(timezone=True), nullable=True)
    counted_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Relationships
    session = relationship("CountSession", back_populates="items")
    storage_area = relationship("StorageArea")
    master_item = relationship("MasterItem")
    inventory = relationship("Inventory")
    counted_by_user = relationship("User")


class CountSessionStorageArea(Base):
    __tablename__ = "count_session_storage_areas"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("count_sessions.id"), nullable=False)
    storage_area_id = Column(Integer, ForeignKey("storage_areas.id"), nullable=False)
    is_finished = Column(Boolean, default=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    finished_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Relationships
    session = relationship("CountSession")
    storage_area = relationship("StorageArea")
    finished_by_user = relationship("User")