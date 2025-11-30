"""
Storage Area model for sub-locations within a location
Examples: main bar, upstairs bar, walk-in cooler, dry storage
"""

from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from restaurant_inventory.db.database import Base

class StorageArea(Base):
    __tablename__ = "storage_areas"

    id = Column(Integer, primary_key=True, index=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    name = Column(String, nullable=False)  # e.g., "Main Bar", "Walk-in Cooler", "Dry Storage"
    description = Column(String, nullable=True)
    display_order = Column(Integer, nullable=False, default=0)  # Order to display storage areas
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    location = relationship("Location", back_populates="storage_areas")
    default_items = relationship("StorageAreaItem", back_populates="storage_area", cascade="all, delete-orphan")


class StorageAreaItem(Base):
    __tablename__ = "storage_area_items"

    id = Column(Integer, primary_key=True, index=True)
    storage_area_id = Column(Integer, ForeignKey("storage_areas.id", ondelete="CASCADE"), nullable=False)
    master_item_id = Column(Integer, ForeignKey("master_items.id", ondelete="CASCADE"), nullable=False)
    display_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    storage_area = relationship("StorageArea", back_populates="default_items")
    master_item = relationship("MasterItem")
