"""
Order Sheet Template models for reusable order lists per location.

Templates define which hub vendor items to include and per-item par levels.
Each location can have multiple templates (e.g., "Beverage Order", "Food Order").

Note: Items reference hub vendor item IDs (cross-database, no FK constraint).
Vendor item data (name, sku, category, uom) is stored as denormalized snapshots.
"""

from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text, Boolean, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from restaurant_inventory.db.database import Base


class OrderSheetTemplate(Base):
    __tablename__ = "order_sheet_templates"
    __table_args__ = (
        UniqueConstraint('location_id', 'name', name='uq_ost_location_name'),
    )

    id = Column(Integer, primary_key=True, index=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    location = relationship("Location")
    created_by_user = relationship("User")
    items = relationship("OrderSheetTemplateItem", back_populates="template",
                         cascade="all, delete-orphan", order_by="OrderSheetTemplateItem.sort_order")


class OrderSheetTemplateItem(Base):
    __tablename__ = "order_sheet_template_items"
    __table_args__ = (
        UniqueConstraint('template_id', 'hub_vendor_item_id', name='uq_osti_template_vendor_item'),
    )

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("order_sheet_templates.id", ondelete="CASCADE"),
                         nullable=False)
    hub_vendor_item_id = Column(Integer, nullable=False)  # Cross-DB reference to Hub vendor_items
    par_level = Column(Integer, nullable=False, default=0)
    sort_order = Column(Integer, default=0)

    # Denormalized vendor item snapshot (refreshed on template save)
    item_name = Column(String, nullable=True)
    vendor_sku = Column(String, nullable=True)
    vendor_name = Column(String, nullable=True)
    category = Column(String, nullable=True)
    unit_abbr = Column(String(20), nullable=True)

    # Relationships
    template = relationship("OrderSheetTemplate", back_populates="items")
