"""
Count Template models for predefined item lists per storage area
"""

from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from restaurant_inventory.db.database import Base

class CountTemplate(Base):
    __tablename__ = "count_templates"

    id = Column(Integer, primary_key=True, index=True)
    storage_area_id = Column(Integer, ForeignKey("storage_areas.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    storage_area = relationship("StorageArea")
    created_by_user = relationship("User")
    items = relationship("CountTemplateItem", back_populates="template", cascade="all, delete-orphan")


class CountTemplateItem(Base):
    __tablename__ = "count_template_items"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("count_templates.id"), nullable=False)
    master_item_id = Column(Integer, ForeignKey("master_items.id"), nullable=False)
    sort_order = Column(Integer, default=0)  # For custom ordering in the count list

    # Relationships
    template = relationship("CountTemplate", back_populates="items")
    master_item = relationship("MasterItem")