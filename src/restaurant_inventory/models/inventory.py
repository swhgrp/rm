"""
Inventory model for location-specific item quantities
"""

from sqlalchemy import Column, Integer, ForeignKey, Numeric, DateTime, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from restaurant_inventory.db.database import Base

class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True, index=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)  # Optional: can be inferred from storage_area
    storage_area_id = Column(Integer, ForeignKey("storage_areas.id"), nullable=True)  # Optional: specific area within location
    master_item_id = Column(Integer, ForeignKey("master_items.id"), nullable=False)

    # Quantity tracking
    current_quantity = Column(Numeric(10, 3), nullable=False, default=0)
    unit_cost = Column(Numeric(10, 2), nullable=True)
    total_value = Column(Numeric(12, 2), nullable=True)

    # Reorder management
    reorder_level = Column(Numeric(10, 3), nullable=True)
    max_level = Column(Numeric(10, 3), nullable=True)

    # Tracking
    last_count_date = Column(DateTime(timezone=True), nullable=True)
    last_updated = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    location = relationship("Location")
    storage_area = relationship("StorageArea")
    master_item = relationship("MasterItem")
