"""
Master Item model for inventory items

Master Items represent the restaurant's standardized catalog.
Used for: inventory counts, recipe costing, COGS reporting.
Must be unique across the system.

Architecture (Location-Aware Costing):
- Hub owns: UOM (global), Categories (global), Vendor Items (per location)
- Inventory owns: Master Items, Count Units, Location Costs

Master Items do NOT store cost data directly. Costs are stored in:
- MasterItemLocationCost: Current weighted average per location
- MasterItemLocationCostHistory: Audit trail of cost changes
"""

from sqlalchemy import Column, Integer, String, Text, Numeric, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from restaurant_inventory.db.database import Base


class MasterItem(Base):
    """
    Master Items are the single source of truth for product data.
    Vendor Items (in Hub) link to Master Items for purchasing.
    Location Costs provide weighted average costs per location.

    NO cost fields here - costs are location-specific and stored in MasterItemLocationCost.
    NO vendor fields here - vendor relationships are in Hub's VendorItem.
    """
    __tablename__ = "master_items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)  # Unique standardized name
    description = Column(Text, nullable=True)

    # Category (references Hub.categories.id, cached name for display)
    category_id = Column(Integer, nullable=True, index=True)  # References Hub.categories.id
    category = Column(String, nullable=True, index=True)  # Cached category name (set by Hub on vendor item sync)

    # Primary UOM for this item (references Hub.units_of_measure.id)
    # This is cached - MasterItemCountUnit has the full list
    primary_uom_id = Column(Integer, nullable=True)  # References Hub.units_of_measure.id
    primary_uom_name = Column(String(50), nullable=True)  # Cached: e.g., "Each", "Pound"
    primary_uom_abbr = Column(String(20), nullable=True)  # Cached: e.g., "ea", "lb"

    # DEPRECATED: Old UOM fields - kept for migration
    unit_of_measure_id = Column(Integer, ForeignKey("units_of_measure.id"), nullable=True)  # DEPRECATED
    unit_of_measure = Column(String, nullable=True)  # DEPRECATED
    secondary_unit = Column(String, nullable=True)  # DEPRECATED
    units_per_secondary = Column(Numeric(10, 3), nullable=True)  # DEPRECATED
    secondary_unit_id = Column(Integer, ForeignKey("units_of_measure.id"), nullable=True)  # DEPRECATED

    # DEPRECATED: Cost fields - moved to MasterItemLocationCost
    current_cost = Column(Numeric(10, 2), nullable=True)  # DEPRECATED: Use location_costs
    average_cost = Column(Numeric(10, 2), nullable=True)  # DEPRECATED: Use location_costs
    last_cost_update = Column(DateTime(timezone=True), nullable=True)  # DEPRECATED
    cost_method = Column(String, nullable=True, default='WEIGHTED_AVERAGE')  # DEPRECATED (always weighted avg)

    # Product details
    internal_sku = Column(String, nullable=True, index=True)  # Internal restaurant SKU
    sku = Column(String, nullable=True, index=True)  # Alias for internal_sku
    barcode = Column(String, nullable=True, index=True)  # For scanning during counts
    barcode_type = Column(String, nullable=True)  # UPC, EAN, CODE128, QR, etc.
    par_level = Column(Numeric(10, 3), nullable=True)  # Default par level for all locations
    shelf_life_days = Column(Integer, nullable=True)  # Shelf life in days (for tracking expiration)

    # Recipe and reporting
    is_recipe_ingredient = Column(Boolean, default=True)  # Can be used in recipes
    reporting_tags = Column(Text, nullable=True)  # Comma-separated tags for reporting

    # DEPRECATED: Vendor field - vendor relationships are in Hub's VendorItem
    vendor_id = Column(Integer, ForeignKey("vendors.id", ondelete="SET NULL"), nullable=True, index=True)  # DEPRECATED

    # Relationships (deprecated - kept for migration)
    vendor = relationship("Vendor", backref="items")  # DEPRECATED
    unit = relationship("UnitOfMeasure", foreign_keys=[unit_of_measure_id], backref="master_items_primary")  # DEPRECATED
    secondary_unit_rel = relationship("UnitOfMeasure", foreign_keys=[secondary_unit_id], backref="master_items_secondary")  # DEPRECATED

    # Key Item flag - highlight important items for tracking
    is_key_item = Column(Boolean, default=False)

    # DEPRECATED: Additional count units - use MasterItemCountUnit instead
    count_unit_2_id = Column(Integer, ForeignKey("units_of_measure.id"), nullable=True)  # DEPRECATED
    count_unit_3_id = Column(Integer, ForeignKey("units_of_measure.id"), nullable=True)  # DEPRECATED
    count_unit_2 = relationship("UnitOfMeasure", foreign_keys=[count_unit_2_id], backref="master_items_count2")  # DEPRECATED
    count_unit_3 = relationship("UnitOfMeasure", foreign_keys=[count_unit_3_id], backref="master_items_count3")  # DEPRECATED

    # NEW: Relationships to new models
    count_units = relationship("MasterItemCountUnit", back_populates="master_item", cascade="all, delete-orphan")
    location_costs = relationship("MasterItemLocationCost", back_populates="master_item", cascade="all, delete-orphan")

    # Status
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<MasterItem(id={self.id}, name={self.name}, category={self.category})>"

    def get_cost_at_location(self, location_id: int) -> float | None:
        """Get the current weighted average cost at a specific location."""
        for loc_cost in self.location_costs:
            if loc_cost.location_id == location_id:
                return float(loc_cost.current_weighted_avg_cost) if loc_cost.current_weighted_avg_cost else None
        return None

    def get_primary_count_unit(self):
        """Get the primary count unit for this item."""
        for cu in self.count_units:
            if cu.is_primary:
                return cu
        return None
