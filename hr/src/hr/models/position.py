"""
Position model for HR Management System
"""

from sqlalchemy import Column, Integer, String, Boolean, Numeric, Text, ForeignKey
from sqlalchemy.orm import relationship
from hr.db.database import Base


class Position(Base):
    """Position model - stores job positions and pay ranges"""

    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False, index=True)  # Server, Cook, Manager, etc.
    department_id = Column(Integer, ForeignKey('departments.id', ondelete='SET NULL'), nullable=True)
    department = Column(String)  # Legacy field - kept for backwards compatibility
    description = Column(Text)

    # Pay Range
    hourly_rate_min = Column(Numeric(10, 2))
    hourly_rate_max = Column(Numeric(10, 2))

    # Status
    is_active = Column(Boolean, default=True)

    # Relationships
    department_rel = relationship("Department", backref="positions")

    def __repr__(self):
        return f"<Position {self.title}>"
