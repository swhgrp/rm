"""
Category model for organizing items with hierarchical support

Hub is the source of truth for category data.
Inventory reads from Hub via dblink.
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from integration_hub.db.database import Base


class Category(Base):
    """
    Item categories with hierarchical support (parent/child).

    Examples:
    - Beer (parent)
      - Draft (child)
      - Bottled (child)
      - Canned (child)
    - Liquor (parent)
      - Whiskey (child)
      - Vodka (child)
      - Tequila (child)
    """
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    display_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)

    # Hierarchical support: parent_id allows subcategories
    parent_id = Column(Integer, ForeignKey('categories.id', ondelete='CASCADE'), nullable=True, index=True)

    # Relationships
    parent = relationship("Category", remote_side=[id], backref="subcategories")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<Category(id={self.id}, name={self.name}, parent_id={self.parent_id})>"

    @property
    def full_name(self):
        """Returns full hierarchical name like 'Beer - Bottled'"""
        if self.parent:
            return f"{self.parent.name} - {self.name}"
        return self.name
