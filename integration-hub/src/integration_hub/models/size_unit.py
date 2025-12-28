"""
Size Unit model for Backbar-style sizing

Size units represent the measurement unit in a vendor item's size specification.
Examples: L (Liter), ml (Milliliter), lb (Pound), oz (Ounce), fl oz (Fluid Ounce)

Each unit has:
- A display name and symbol
- A measure type (volume, weight, count)
- Conversion factor to a base unit for normalization
"""

from sqlalchemy import Column, Integer, String, Numeric, Boolean
from integration_hub.db.database import Base


class SizeUnit(Base):
    """
    Size unit for vendor item sizing (Backbar-style).

    Used in the Size field: [Quantity] [Unit] [Container]
    Example: "1 L bottle" -> quantity=1, unit=L, container=bottle

    Includes conversion factors for price normalization across different sizes.
    """
    __tablename__ = "hub_size_units"

    id = Column(Integer, primary_key=True, index=True)

    # Display info
    name = Column(String(50), nullable=False)  # "Liter", "Milliliter", "Pound"
    symbol = Column(String(20), nullable=False, unique=True)  # "L", "ml", "lb"

    # Measure type for grouping
    measure_type = Column(String(20), nullable=False)  # "volume", "weight", "count"

    # Conversion to base unit (for price normalization)
    base_unit_symbol = Column(String(20), nullable=False)  # "ml", "g", "each"
    conversion_to_base = Column(Numeric(15, 6), nullable=False, default=1.0)  # e.g., 1000 for L->ml

    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0)  # For dropdown ordering

    def __repr__(self):
        return f"<SizeUnit(id={self.id}, symbol='{self.symbol}', type='{self.measure_type}')>"

    @property
    def display_name(self) -> str:
        """Format for dropdown: 'L (Liter)'"""
        return f"{self.symbol} ({self.name})"
