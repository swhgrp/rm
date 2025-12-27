"""
Location model for multi-location support

Inventory is the source of truth for locations.
Accounting pulls location data from here.
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from restaurant_inventory.db.database import Base


class Location(Base):
    """
    Business locations/entities.

    This is the source of truth for locations across all systems.
    Accounting syncs from this table.
    """
    __tablename__ = "locations"

    id = Column(Integer, primary_key=True, index=True)

    # Identity
    code = Column(String(20), unique=True, nullable=True, index=True)  # Short code like "400", "500"
    name = Column(String(100), nullable=False, index=True)  # DBA name like "Seaside Grill"

    # Legal entity information
    legal_name = Column(String(200), nullable=True)  # Legal business name
    ein = Column(String(20), nullable=True)  # Employer Identification Number

    # Address information
    address = Column(Text, nullable=True)  # Street address
    city = Column(String(100), nullable=True)
    state = Column(String(50), nullable=True)
    zip_code = Column(String(20), nullable=True)

    # Contact
    phone = Column(String(20), nullable=True)
    manager_name = Column(String(100), nullable=True)

    # Status
    is_active = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    storage_areas = relationship("StorageArea", back_populates="location")

    def __repr__(self):
        return f"<Location {self.code}: {self.name}>"
