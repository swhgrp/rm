"""
Master Item Count Units model

Defines how a master item can be counted in multiple units.
Each item has one primary count unit and optional secondary units.

Architecture (Location-Aware Costing):
- Hub owns: UOM (global), Categories (global), Vendor Items (per location)
- Inventory owns: Master Items, Count Units, Location Costs
"""

from sqlalchemy import Column, Integer, String, Numeric, Boolean, DateTime, ForeignKey, UniqueConstraint
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

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    master_item = relationship("MasterItem", back_populates="count_units")

    def __repr__(self):
        primary = "PRIMARY" if self.is_primary else "secondary"
        return f"<MasterItemCountUnit(id={self.id}, item={self.master_item_id}, uom={self.uom_name}, {primary}, factor={self.conversion_to_primary})>"

    def convert_to_primary(self, quantity: float) -> float:
        """Convert quantity in this unit to primary unit."""
        return float(quantity) * float(self.conversion_to_primary)

    def convert_from_primary(self, quantity: float) -> float:
        """Convert quantity from primary unit to this unit."""
        if float(self.conversion_to_primary) == 0:
            return 0.0
        return float(quantity) / float(self.conversion_to_primary)
