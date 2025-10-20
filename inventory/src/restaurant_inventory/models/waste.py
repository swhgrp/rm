"""
Waste model for tracking spoiled, damaged, or discarded inventory
"""

from sqlalchemy import Column, Integer, ForeignKey, Numeric, DateTime, String, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from restaurant_inventory.db.database import Base

class WasteRecord(Base):
    __tablename__ = "waste_records"

    id = Column(Integer, primary_key=True, index=True)
    
    # What was wasted
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    master_item_id = Column(Integer, ForeignKey("master_items.id"), nullable=False)
    inventory_id = Column(Integer, ForeignKey("inventory.id"), nullable=True)
    
    # Waste details
    quantity_wasted = Column(Numeric(10, 3), nullable=False)
    unit_cost = Column(Numeric(10, 2), nullable=True)
    total_cost = Column(Numeric(12, 2), nullable=True)
    
    # Reason tracking
    reason_code = Column(String, nullable=False)  # spoiled, damaged, expired, theft, etc.
    description = Column(Text, nullable=True)
    
    # User and timing
    recorded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    waste_date = Column(DateTime(timezone=True), nullable=False)
    recorded_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    location = relationship("Location")
    master_item = relationship("MasterItem")
    inventory_record = relationship("Inventory")
    recorder = relationship("User")
