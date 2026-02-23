"""
Order Sheet models for filled-out order sheets.

When a user starts an order sheet from a template, vendor item data (par levels,
name, UOM, category) is snapshotted so historical records remain accurate even
if templates or vendor items change.

Note: Items reference hub vendor item IDs (cross-database, no FK constraint).
"""

import enum
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text, Enum as SQLEnum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from restaurant_inventory.db.database import Base


class OrderSheetStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    COMPLETED = "COMPLETED"
    SENT = "SENT"


class OrderSheet(Base):
    __tablename__ = "order_sheets"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("order_sheet_templates.id"), nullable=False)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False, index=True)
    name = Column(String, nullable=True)
    status = Column(SQLEnum(OrderSheetStatus), default=OrderSheetStatus.DRAFT, nullable=False)
    notes = Column(Text, nullable=True)

    # Workflow
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Email tracking
    sent_to_emails = Column(Text, nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    template = relationship("OrderSheetTemplate")
    location = relationship("Location")
    created_by_user = relationship("User")
    items = relationship("OrderSheetItem", back_populates="order_sheet",
                         cascade="all, delete-orphan")


class OrderSheetItem(Base):
    __tablename__ = "order_sheet_items"

    id = Column(Integer, primary_key=True, index=True)
    order_sheet_id = Column(Integer, ForeignKey("order_sheets.id", ondelete="CASCADE"),
                            nullable=False)
    hub_vendor_item_id = Column(Integer, nullable=False)  # Cross-DB reference to Hub vendor_items
    par_level = Column(Integer, nullable=True)
    on_hand = Column(Integer, nullable=True)
    to_order = Column(Integer, nullable=True)
    unit_abbr = Column(String(20), nullable=True)
    notes = Column(Text, nullable=True)

    # Denormalized vendor item snapshot (set at order sheet creation time)
    item_name = Column(String, nullable=True)
    vendor_sku = Column(String, nullable=True)
    vendor_name = Column(String, nullable=True)
    category = Column(String, nullable=True)

    # Relationships
    order_sheet = relationship("OrderSheet", back_populates="items")
