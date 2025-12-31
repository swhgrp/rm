from sqlalchemy import Column, Integer, String, Numeric, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from restaurant_inventory.db.database import Base


class UnitCategory(Base):
    """
    Categories for units of measure (Weight, Volume, Length, etc.)
    """
    __tablename__ = "unit_categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False, unique=True)  # Weight, Volume, Length, etc.
    description = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    units = relationship("UnitOfMeasure", back_populates="category", cascade="all, delete-orphan")


class UnitOfMeasure(Base):
    """
    Individual units of measure with reference-based conversion system.
    Example: "Case - 6" contains 6.0 of "Each"
    """
    __tablename__ = "units_of_measure"

    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(Integer, ForeignKey("unit_categories.id"), nullable=False)
    name = Column(String(50), nullable=False)  # e.g., "Case - 6", "Each", "Dozen"
    abbreviation = Column(String(50), nullable=False)  # e.g., "cs", "ea", "dz"

    # Dimension for unit type compatibility (count, volume, weight, length)
    dimension = Column(String(20), nullable=True)

    # Reference-based conversion: this unit contains X quantity of the reference unit
    reference_unit_id = Column(Integer, ForeignKey("units_of_measure.id"), nullable=True)
    contains_quantity = Column(Numeric(20, 10), nullable=True)  # How many reference units this contains

    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    category = relationship("UnitCategory", back_populates="units")
    reference_unit = relationship("UnitOfMeasure", remote_side=[id], foreign_keys=[reference_unit_id])

    # Constraints: name and abbreviation should be unique within a category
    __table_args__ = (
        # UniqueConstraint('category_id', 'name', name='uq_category_unit_name'),
        # UniqueConstraint('category_id', 'abbreviation', name='uq_category_unit_abbr'),
    )
