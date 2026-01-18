"""
Master Item Count Units model

Defines how a master item can be counted in multiple units.
Each item has one primary count unit and optional secondary units.

This model consolidates:
- Count units (primary + secondary units for inventory counting)
- Unit conversions (item-specific conversions, e.g., 1 lb = 8 patties)

Architecture (Location-Aware Costing):
- Hub owns: UOM (global), Categories (global), Vendor Items (per location)
- Inventory owns: Master Items, Count Units, Location Costs

NOTE: The item_unit_conversions table is deprecated. All unit conversion
functionality is now handled by this model's conversion_to_primary field
combined with the individual_weight_oz/individual_volume_oz specifications.
"""

from sqlalchemy import Column, Integer, String, Numeric, Boolean, DateTime, ForeignKey, UniqueConstraint, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from restaurant_inventory.db.database import Base


class MasterItemCountUnit(Base):
    """
    Count units for a master item.

    Each master item can be counted in multiple units:
    - One primary unit (is_primary=True)
    - Zero or more secondary units (is_primary=False)

    The primary unit is used for:
    - Weighted average cost calculation
    - Display in inventory counts (default)
    - Recipe costing

    Secondary units allow counting in alternative units:
    - Cases instead of each
    - Weight instead of count
    - Volume conversions

    Example for "Chicken Breast":
    - Primary: Pound (lb) - is_primary=True, conversion_to_primary=1.0
    - Secondary: Case (40 lb) - is_primary=False, conversion_to_primary=40.0
    - Secondary: Each (~8 oz) - is_primary=False, conversion_to_primary=0.5

    All costs are stored in primary unit ($/lb in this case).
    """
    __tablename__ = "master_item_count_units"
    __table_args__ = (
        UniqueConstraint('master_item_id', 'uom_id', name='uq_master_item_uom'),
    )

    id = Column(Integer, primary_key=True, index=True)

    # Link to master item
    master_item_id = Column(Integer, ForeignKey("master_items.id", ondelete="CASCADE"), nullable=False, index=True)

    # Link to Hub UOM (by ID reference - not a foreign key since it's in another DB)
    # Hub is source of truth for UOM
    uom_id = Column(Integer, nullable=False, index=True)  # References Hub.units_of_measure.id
    uom_name = Column(String(50), nullable=True)  # Cached: e.g., "Case", "Each", "Pound"
    uom_abbreviation = Column(String(20), nullable=True)  # Cached: e.g., "cs", "ea", "lb"

    # Is this the primary count unit?
    is_primary = Column(Boolean, default=False, nullable=False, index=True)

    # Conversion to primary unit
    # Example: If primary is "Each" and this unit is "Dozen":
    #   conversion_to_primary = 12.0 (1 dozen = 12 each)
    # Primary unit always has conversion_to_primary = 1.0
    conversion_to_primary = Column(Numeric(20, 10), nullable=False, default=1.0)

    # Display order for UI
    display_order = Column(Integer, default=0)

    # Individual unit specifications (consolidated from ItemUnitConversion)
    # These track physical specifications for portion-controlled items
    # Example: Sausage patties - 2oz per patty, or 750ml bottle = 25.36 fl oz
    individual_weight_oz = Column(Numeric(10, 4), nullable=True)  # Weight per unit in oz
    individual_volume_oz = Column(Numeric(10, 4), nullable=True)  # Volume per unit in fl oz
    notes = Column(Text, nullable=True)  # Contextual notes (e.g., "2oz oval patties")

    # Soft delete support
    is_active = Column(Boolean, default=True, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    master_item = relationship("MasterItem", back_populates="count_units")

    def __repr__(self):
        primary = "PRIMARY" if self.is_primary else "secondary"
        active = "" if self.is_active else " INACTIVE"
        return f"<MasterItemCountUnit(id={self.id}, item={self.master_item_id}, uom={self.uom_name}, {primary}, factor={self.conversion_to_primary}{active})>"

    def convert_to_primary(self, quantity: float) -> float:
        """Convert quantity in this unit to primary unit."""
        return float(quantity) * float(self.conversion_to_primary)

    def convert_from_primary(self, quantity: float) -> float:
        """Convert quantity from primary unit to this unit."""
        if float(self.conversion_to_primary) == 0:
            return 0.0
        return float(quantity) / float(self.conversion_to_primary)
