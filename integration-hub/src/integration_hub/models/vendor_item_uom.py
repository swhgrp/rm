"""
Vendor Item UOM model - Multiple purchase UOMs per vendor item

Each vendor item can be purchased in multiple UOMs (e.g., Case of 12 or Each).
Each UOM has a conversion_factor defining how many inventory base units it contains.
This replaces the fragile price_is_per_unit flag with deterministic cost calculation.
"""
from sqlalchemy import Column, Integer, Numeric, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship, backref
from sqlalchemy.sql import func
from integration_hub.db.database import Base


class VendorItemUOM(Base):
    """
    Purchase UOM option for a vendor item.

    Example: Tito's Vodka 80 (vendor_item #464)
      CS → conversion_factor=12, is_default=True   ($306/cs → $25.50/ea)
      EA → conversion_factor=1,  is_default=False   ($25.50/ea)
    """
    __tablename__ = "vendor_item_uoms"
    __table_args__ = (
        UniqueConstraint('vendor_item_id', 'uom_id', name='uq_vendor_item_uom_pair'),
    )

    id = Column(Integer, primary_key=True, index=True)
    vendor_item_id = Column(
        Integer,
        ForeignKey("hub_vendor_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    uom_id = Column(
        Integer,
        ForeignKey("units_of_measure.id"),
        nullable=False
    )

    # How many inventory primary units does 1 of this purchase UOM contain?
    # Case of 12 bottles: conversion_factor = 12
    # Each (1 bottle): conversion_factor = 1
    # 10lb case (weight item): conversion_factor = 10
    conversion_factor = Column(Numeric(20, 10), nullable=False, default=1.0)

    is_default = Column(Boolean, default=False, nullable=False)
    expected_price = Column(Numeric(10, 4), nullable=True)
    last_cost = Column(Numeric(10, 4), nullable=True)
    last_cost_date = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    vendor_item = relationship("HubVendorItem", backref=backref("purchase_uoms", cascade="all, delete-orphan"))
    uom = relationship("UnitOfMeasure")

    def __repr__(self):
        return (
            f"<VendorItemUOM(id={self.id}, "
            f"vendor_item={self.vendor_item_id}, "
            f"uom={self.uom_id}, "
            f"cf={self.conversion_factor}, "
            f"default={self.is_default})>"
        )
