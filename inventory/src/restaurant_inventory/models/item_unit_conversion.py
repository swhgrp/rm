"""
Item Unit Conversion model for item-specific unit conversions

Allows defining how to convert between units for a specific item.
Example: Sausage patties - 1 LB = 8 patties (2oz each)
"""

from sqlalchemy import Column, Integer, Numeric, Text, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from restaurant_inventory.db.database import Base


class ItemUnitConversion(Base):
    """
    Item-specific unit conversions.

    Example use case:
    - Item: Sausage, Pork, Oval Patties (2oz each)
    - from_unit: Pound (LB)
    - to_unit: Each (EA)
    - conversion_factor: 8 (16oz in a pound / 2oz per patty = 8 patties per pound)

    This allows:
    - Purchasing in LB
    - Counting inventory in Each (patties)
    - Automatic conversion: 12 LB = 96 patties
    """
    __tablename__ = "item_unit_conversions"

    id = Column(Integer, primary_key=True, index=True)
    master_item_id = Column(Integer, ForeignKey("master_items.id", ondelete="CASCADE"), nullable=False, index=True)

    # Source unit (e.g., Pound)
    from_unit_id = Column(Integer, ForeignKey("units_of_measure.id"), nullable=False)

    # Target unit (e.g., Each)
    to_unit_id = Column(Integer, ForeignKey("units_of_measure.id"), nullable=False)

    # How many "to_units" in one "from_unit"
    # Example: 1 LB = 8 patties -> conversion_factor = 8
    conversion_factor = Column(Numeric(20, 6), nullable=False)

    # Optional: individual unit specifications for reference
    individual_weight_oz = Column(Numeric(10, 4), nullable=True)  # e.g., 2oz per patty
    individual_volume_oz = Column(Numeric(10, 4), nullable=True)  # e.g., 8oz per bottle

    # Notes for clarity
    notes = Column(Text, nullable=True)

    # Status
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    master_item = relationship("MasterItem", backref="unit_conversions")
    from_unit = relationship("UnitOfMeasure", foreign_keys=[from_unit_id])
    to_unit = relationship("UnitOfMeasure", foreign_keys=[to_unit_id])

    # Constraints
    __table_args__ = (
        UniqueConstraint('master_item_id', 'from_unit_id', 'to_unit_id', name='uq_item_unit_conversion'),
    )

    def __repr__(self):
        return f"<ItemUnitConversion(item_id={self.master_item_id}, {self.conversion_factor} {self.to_unit_id} per {self.from_unit_id})>"

    def convert(self, quantity: float, from_unit_id: int) -> float:
        """
        Convert a quantity from one unit to another.

        Args:
            quantity: The amount to convert
            from_unit_id: The source unit ID

        Returns:
            The converted quantity
        """
        if from_unit_id == self.from_unit_id:
            # Converting from -> to (multiply by factor)
            return quantity * float(self.conversion_factor)
        elif from_unit_id == self.to_unit_id:
            # Converting to -> from (divide by factor)
            return quantity / float(self.conversion_factor)
        else:
            raise ValueError(f"Unit {from_unit_id} not in this conversion")
