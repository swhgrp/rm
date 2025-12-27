"""
Hub Vendor Item model

Vendor Items represent how a specific vendor sells a product.
This is the source of truth for vendor items - Inventory reads from here.

Links vendors to Inventory's master items with vendor-specific details.

Architecture (Location-Aware Costing):
- Hub owns: UOM (global), Categories (global), Vendor Items (per location)
- Inventory owns: Master Items, Count Units, Location Costs

Vendor Item records are per-location because:
- Same item may have different prices at different locations
- Some vendors may only service certain locations
- Review workflow is per-location
"""

from sqlalchemy import Column, Integer, String, Numeric, DateTime, Boolean, ForeignKey, Text, Enum, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from integration_hub.db.database import Base
import enum


class VendorItemStatus(enum.Enum):
    """
    Status for vendor item review workflow.

    - active: Verified, ready for use in costing
    - needs_review: New/changed item, needs human verification before costing
    - inactive: No longer purchased from this vendor
    """
    active = "active"
    needs_review = "needs_review"
    inactive = "inactive"


class HubVendorItem(Base):
    """
    Hub Vendor Items - source of truth for vendor item data.

    Many Vendor Items can map to one Master Item (in Inventory).
    Created during invoice mapping workflow in Hub.

    Location-aware: Each record is for a specific location.
    Unique constraint: (vendor_id, vendor_sku, location_id)
    """
    __tablename__ = "hub_vendor_items"
    __table_args__ = (
        UniqueConstraint('vendor_id', 'vendor_sku', 'location_id', name='uq_vendor_item_location'),
    )

    id = Column(Integer, primary_key=True, index=True)

    # Link to Hub vendor
    vendor_id = Column(Integer, ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False, index=True)

    # Location this vendor item applies to (references Inventory.locations.id)
    # Required for location-aware costing
    location_id = Column(Integer, nullable=True, index=True)  # NULL during migration, required after

    # Link to Inventory master item (by ID reference - not a foreign key since it's in another DB)
    inventory_master_item_id = Column(Integer, nullable=True, index=True)
    inventory_master_item_name = Column(String(200), nullable=True)  # Cached for display

    # Vendor-specific details
    vendor_sku = Column(String(100), nullable=True, index=True)  # Vendor's SKU/product code
    vendor_product_name = Column(String(500), nullable=False)  # How vendor names this product
    vendor_description = Column(Text, nullable=True)  # Vendor's description

    # Purchase unit - references Hub's UOM by ID (Hub is source of truth for UOM)
    purchase_unit_id = Column(Integer, ForeignKey("units_of_measure.id"), nullable=True)  # ID from Hub's units_of_measure
    purchase_unit_name = Column(String(50), nullable=True)  # Cached: e.g., "Case", "Each"
    purchase_unit_abbr = Column(String(20), nullable=True)  # Cached: e.g., "CS", "EA"

    # Pack size info (display only)
    pack_size = Column(String(100), nullable=True)  # e.g., "Case - 6", "Box - 24", "12 x 750ml"

    # NEW: Pack to Primary Factor
    # Converts purchase units to the master item's primary count unit
    # Example: If purchase unit is "Case" containing 6 bottles, and primary count unit is "Each":
    #   pack_to_primary_factor = 6.0 (1 case = 6 each)
    # Example: If purchase unit is "50lb Bag" and primary count unit is "Pound":
    #   pack_to_primary_factor = 50.0 (1 bag = 50 lb)
    pack_to_primary_factor = Column(Numeric(20, 10), nullable=False, default=1.0)

    # DEPRECATED: Old conversion fields - kept for migration
    conversion_factor = Column(Numeric(20, 10), nullable=True)  # DEPRECATED: Use pack_to_primary_factor
    conversion_unit_id = Column(Integer, nullable=True)  # DEPRECATED: Use MasterItemCountUnit in Inventory

    # Pricing (updated from invoices)
    # last_purchase_price = price per purchase unit (e.g., $45.00 per case)
    last_purchase_price = Column(Numeric(10, 2), nullable=True)  # Current price per purchase unit
    previous_purchase_price = Column(Numeric(10, 2), nullable=True)  # Previous price (for change tracking)
    price_updated_at = Column(DateTime(timezone=True), nullable=True)

    # DEPRECATED: Old naming - kept for migration
    unit_price = Column(Numeric(10, 2), nullable=True)  # DEPRECATED: Use last_purchase_price
    last_price = Column(Numeric(10, 2), nullable=True)  # DEPRECATED: Use previous_purchase_price

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

    # Review workflow status
    status = Column(Enum(VendorItemStatus), nullable=False, default=VendorItemStatus.needs_review, index=True)

    # Status flags
    is_active = Column(Boolean, default=True, nullable=False)  # DEPRECATED: Use status instead
    is_preferred = Column(Boolean, default=False, nullable=False)  # Preferred vendor for this item at this location

    # Sync tracking
    inventory_vendor_item_id = Column(Integer, nullable=True, index=True)  # ID in Inventory (for migration)
    synced_to_inventory = Column(Boolean, default=False)
    synced_to_inventory_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    vendor = relationship("Vendor", backref="vendor_items")
    purchase_unit = relationship("UnitOfMeasure", foreign_keys=[purchase_unit_id])

    def __repr__(self):
        name_preview = self.vendor_product_name[:30] if self.vendor_product_name else None
        return f"<HubVendorItem(id={self.id}, vendor={self.vendor_id}, sku={self.vendor_sku}, location={self.location_id}, status={self.status.value if self.status else 'none'}, name={name_preview})>"

    @property
    def cost_per_primary_unit(self) -> float | None:
        """
        Calculate cost per primary count unit.
        Returns None if pricing data is incomplete.

        Example:
          - last_purchase_price = $45.00 (per case)
          - pack_to_primary_factor = 6.0 (6 bottles per case)
          - cost_per_primary_unit = $45.00 / 6 = $7.50 per bottle
        """
        if not self.last_purchase_price or not self.pack_to_primary_factor:
            return None
        if float(self.pack_to_primary_factor) == 0:
            return None
        return float(self.last_purchase_price) / float(self.pack_to_primary_factor)
