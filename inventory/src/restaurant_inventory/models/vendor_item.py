"""
Vendor Item model - represents how vendors sell products
Links vendors to master items with vendor-specific details
"""

from sqlalchemy import Column, Integer, String, Numeric, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from restaurant_inventory.db.database import Base


class VendorItem(Base):
    """
    Vendor Items represent how a specific vendor sells a product.
    Many Vendor Items can map to one Master Item.
    """
    __tablename__ = "vendor_items"

    id = Column(Integer, primary_key=True, index=True)

    # Link to vendor and master item
    vendor_id = Column(Integer, ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False, index=True)
    master_item_id = Column(Integer, ForeignKey("master_items.id", ondelete="CASCADE"), nullable=False, index=True)

    # Vendor-specific details
    vendor_sku = Column(String, nullable=True, index=True)  # Vendor's SKU/product code
    vendor_product_name = Column(String, nullable=False)  # How vendor names this product
    vendor_description = Column(Text, nullable=True)  # Vendor's description

    # Purchase unit and conversion
    purchase_unit_id = Column(Integer, ForeignKey("units_of_measure.id"), nullable=False)  # e.g., "Case", "Box - 6"
    pack_size = Column(String, nullable=True)  # e.g., "Case - 6", "Box - 24"

    # Conversion factor: How many Master Item units = 1 purchase unit
    # Example: If master item is in "lbs" and vendor sells in "case",
    # conversion_factor might be 40.0 (1 case = 40 lbs)
    conversion_factor = Column(Numeric(20, 10), nullable=False)
    conversion_unit_id = Column(Integer, ForeignKey("units_of_measure.id"), nullable=True)  # Unit used in conversion

    # Pricing
    unit_price = Column(Numeric(10, 2), nullable=True)  # Price per purchase unit
    last_price = Column(Numeric(10, 2), nullable=True)  # Previous price (for change tracking)
    price_updated_at = Column(DateTime(timezone=True), nullable=True)

    # Additional details
    minimum_order_quantity = Column(Numeric(10, 3), nullable=True)
    lead_time_days = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)

    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    is_preferred = Column(Boolean, default=False, nullable=False)  # Mark as preferred vendor for this master item

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    vendor = relationship("Vendor", backref="vendor_items")
    master_item = relationship("MasterItem", backref="vendor_items")
    purchase_unit = relationship("UnitOfMeasure", foreign_keys=[purchase_unit_id])
    conversion_unit = relationship("UnitOfMeasure", foreign_keys=[conversion_unit_id])

    def __repr__(self):
        return f"<VendorItem(id={self.id}, vendor={self.vendor_id}, master_item={self.master_item_id}, sku={self.vendor_sku})>"
