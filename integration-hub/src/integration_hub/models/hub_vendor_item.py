"""
Hub Vendor Item model

Vendor Items represent how a specific vendor sells a product.
This is the source of truth for vendor items - Inventory reads from here.

Links vendors to Inventory's master items with vendor-specific details.
"""

from sqlalchemy import Column, Integer, String, Numeric, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from integration_hub.db.database import Base


class HubVendorItem(Base):
    """
    Hub Vendor Items - source of truth for vendor item data.

    Many Vendor Items can map to one Master Item (in Inventory).
    Created during invoice mapping workflow in Hub.
    """
    __tablename__ = "hub_vendor_items"

    id = Column(Integer, primary_key=True, index=True)

    # Link to Hub vendor
    vendor_id = Column(Integer, ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False, index=True)

    # Link to Inventory master item (by ID reference - not a foreign key since it's in another DB)
    inventory_master_item_id = Column(Integer, nullable=True, index=True)
    inventory_master_item_name = Column(String(200), nullable=True)  # Cached for display

    # Vendor-specific details
    vendor_sku = Column(String(100), nullable=True, index=True)  # Vendor's SKU/product code
    vendor_product_name = Column(String(500), nullable=False)  # How vendor names this product
    vendor_description = Column(Text, nullable=True)  # Vendor's description

    # Purchase unit - references Inventory's UOM by ID
    purchase_unit_id = Column(Integer, nullable=False)  # ID from Inventory's units_of_measure
    purchase_unit_name = Column(String(50), nullable=True)  # Cached: e.g., "Case", "Each"
    purchase_unit_abbr = Column(String(20), nullable=True)  # Cached: e.g., "CS", "EA"

    # Pack size info
    pack_size = Column(String(100), nullable=True)  # e.g., "Case - 6", "Box - 24", "12 x 750ml"

    # Conversion factor: How many base units = 1 purchase unit
    # Example: If purchase unit is "Case" containing 6 bottles,
    # conversion_factor = 6
    conversion_factor = Column(Numeric(20, 10), nullable=False, default=1.0)
    conversion_unit_id = Column(Integer, nullable=True)  # ID from Inventory's units_of_measure

    # Pricing (updated from invoices)
    unit_price = Column(Numeric(10, 2), nullable=True)  # Current price per purchase unit
    last_price = Column(Numeric(10, 2), nullable=True)  # Previous price (for change tracking)
    price_updated_at = Column(DateTime(timezone=True), nullable=True)

    # Additional details
    minimum_order_quantity = Column(Numeric(10, 3), nullable=True)
    lead_time_days = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)

    # Category (cached from Inventory's master item)
    category = Column(String(100), nullable=True)

    # GL account mappings (from item_gl_mappings)
    gl_asset_account = Column(Integer, nullable=True)
    gl_cogs_account = Column(Integer, nullable=True)
    gl_waste_account = Column(Integer, nullable=True)

    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    is_preferred = Column(Boolean, default=False, nullable=False)

    # Sync tracking
    inventory_vendor_item_id = Column(Integer, nullable=True, index=True)  # ID in Inventory (for migration)
    synced_to_inventory = Column(Boolean, default=False)
    synced_to_inventory_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    vendor = relationship("Vendor", backref="vendor_items")

    def __repr__(self):
        return f"<HubVendorItem(id={self.id}, vendor={self.vendor_id}, sku={self.vendor_sku}, name={self.vendor_product_name[:30] if self.vendor_product_name else None})>"
