"""
Container model for Backbar-style sizing

Containers represent the physical packaging type in a vendor item's size specification.
Examples: bottle, can, keg, bag, box, carton

Used in the Size field: [Quantity] [Unit] [Container]
Example: "1 L bottle" -> quantity=1, unit=L, container=bottle
"""

from sqlalchemy import Column, Integer, String, Boolean
from integration_hub.db.database import Base


class Container(Base):
    """
    Container type for vendor item sizing (Backbar-style).

    Represents the physical packaging: bottle, can, keg, bag, etc.
    """
    __tablename__ = "hub_containers"

    id = Column(Integer, primary_key=True, index=True)

    # Display info
    name = Column(String(50), nullable=False, unique=True)  # "bottle", "can", "bag"

    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0)  # For dropdown ordering

    def __repr__(self):
        return f"<Container(id={self.id}, name='{self.name}')>"
