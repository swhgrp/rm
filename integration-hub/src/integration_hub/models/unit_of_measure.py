"""
Unit of Measure models for Integration Hub

Hub is the source of truth for UOM data.
Inventory references Hub UOMs via dblink or ID.

Architecture (Location-Aware Costing):
- Hub owns: UOM (global), Categories (global), Vendor Items (per location)
- Inventory owns: Master Items, Count Units, Location Costs
"""

from sqlalchemy import Column, Integer, String, Numeric, Boolean, ForeignKey, DateTime, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from integration_hub.db.database import Base
import enum


class MeasureType(enum.Enum):
    """
    Strict measure types for units of measure.
    Simplified from previous "dimension" concept.

    Only 3 types allowed (per MarginEdge/R365 hybrid design):
    - each: Discrete countable items (each, case, bottle, dozen, can)
    - weight: Mass measures (oz, lb, kg, g)
    - volume: Liquid measures (fl oz, gallon, liter, ml)

    Note: LENGTH removed - not needed for restaurant inventory.
    """
    each = "each"        # Base: each (ea) = 1.0
    weight = "weight"    # Base: ounce (oz) = 1.0
    volume = "volume"    # Base: fluid ounce (fl oz) = 1.0


# Keep old enum for backward compatibility during migration
class UnitDimension(enum.Enum):
    """DEPRECATED: Use MeasureType instead. Kept for migration compatibility."""
    count = "count"
    volume = "volume"
    weight = "weight"
    length = "length"  # Will be removed


class UnitCategory(Base):
    """
    Categories for units of measure (Count, Weight, Volume)
    Maps to R365's "Type" concept on UOM.
    """
    __tablename__ = "unit_categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False, unique=True)  # Count, Weight, Volume
    description = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    units = relationship("UnitOfMeasure", back_populates="category", cascade="all, delete-orphan")


class UnitOfMeasure(Base):
    """
    Individual units of measure with dimension-based conversion system.

    Hub is source of truth - Inventory references these by ID.

    IMPORTANT: Units should be PURE units, not compound descriptions.
    - CORRECT: "Bottle", "Case", "Gallon", "Pound"
    - INCORRECT: "Bottle 750ml", "Case - 12", "Keg 1/2 Barrel"

    The size/quantity information belongs on:
    - VendorItem.pack_to_primary_factor (how many primary units per purchase unit)
    - MasterItemCountUnit.conversion_to_primary (for alternative count units)

    Measure type conversion:
    - each: base = each (ea), factor 1.0; dozen = 12.0, case = depends on item
    - volume: base = fluid ounce (fl oz), factor 1.0; gallon = 128.0
    - weight: base = ounce (oz), factor 1.0; pound = 16.0

    Example: Gallon has measure_type=volume, to_base_factor=128.0 (128 fl oz per gallon)
    """
    __tablename__ = "units_of_measure"

    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(Integer, ForeignKey("unit_categories.id"), nullable=False)
    name = Column(String(50), nullable=False)  # e.g., "Gallon", "Each", "Dozen"
    abbreviation = Column(String(20), nullable=False)  # e.g., "gal", "ea", "dz"

    # New: Simplified measure type (3 types only)
    measure_type = Column(Enum(MeasureType), nullable=True)  # each, weight, volume

    # Conversion factor to base unit within measure type
    to_base_factor = Column(Numeric(20, 10), nullable=False, default=1.0)  # How many base units this equals
    is_base_unit = Column(Boolean, default=False)  # True if this is the base unit for its measure_type

    # DEPRECATED: Old dimension field - kept for migration, will be removed
    dimension = Column(Enum(UnitDimension), nullable=True)  # count, volume, weight, length

    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    category = relationship("UnitCategory", back_populates="units")

    @property
    def effective_measure_type(self):
        """Get measure_type, falling back to dimension for migration compatibility."""
        if self.measure_type:
            return self.measure_type
        # Map old dimension to new measure_type
        if self.dimension:
            if self.dimension.value == 'count':
                return MeasureType.each
            elif self.dimension.value == 'volume':
                return MeasureType.volume
            elif self.dimension.value == 'weight':
                return MeasureType.weight
        return None

    def convert_to(self, target_unit: 'UnitOfMeasure', quantity: float) -> float:
        """
        Convert a quantity from this unit to the target unit.
        Both units must have the same measure_type.

        Example: 2 gallons -> fluid ounces = 2 * 128.0 = 256 fl oz
        """
        self_type = self.effective_measure_type
        target_type = target_unit.effective_measure_type

        if self_type != target_type:
            raise ValueError(f"Cannot convert between measure types: {self_type} -> {target_type}")

        if not self.to_base_factor or not target_unit.to_base_factor:
            raise ValueError("Missing to_base_factor for conversion")

        # Convert to base units, then to target units
        base_quantity = float(quantity) * float(self.to_base_factor)
        return base_quantity / float(target_unit.to_base_factor)

    def to_base(self, quantity: float) -> float:
        """Convert quantity to base units of this measure_type."""
        if not self.to_base_factor:
            raise ValueError("Missing to_base_factor")
        return float(quantity) * float(self.to_base_factor)

    def __repr__(self):
        mt = self.measure_type.value if self.measure_type else (self.dimension.value if self.dimension else 'none')
        return f"<UnitOfMeasure(id={self.id}, name={self.name}, abbr={self.abbreviation}, measure_type={mt})>"
