"""
Master Item model for inventory items

Master Items represent the restaurant's standardized catalog.
Used for: inventory counts, recipe costing, COGS reporting.
Must be unique across the system.
"""

from sqlalchemy import Column, Integer, String, Text, Numeric, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from restaurant_inventory.db.database import Base

class MasterItem(Base):
    """
    Master Items are the single source of truth for product data.
    Vendor Items link to Master Items to handle multi-vendor scenarios.
    """
    __tablename__ = "master_items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)  # Unique standardized name
    description = Column(Text, nullable=True)
    category = Column(String, nullable=False, index=True)

    # Default Unit of Measure - the "master" unit for this item
    unit_of_measure_id = Column(Integer, ForeignKey("units_of_measure.id"), nullable=True)

    # Legacy string fields (deprecated - use unit_of_measure_id instead)
    unit_of_measure = Column(String, nullable=True)  # DEPRECATED
    secondary_unit = Column(String, nullable=True)  # DEPRECATED
    units_per_secondary = Column(Numeric(10, 3), nullable=True)  # DEPRECATED

    # Secondary unit of measure (optional, for items with multiple units like bottles/cases)
    secondary_unit_id = Column(Integer, ForeignKey("units_of_measure.id"), nullable=True)

    # Costing information (calculated from vendor items)
    current_cost = Column(Numeric(10, 2), nullable=True)  # Current weighted average cost per master unit
    average_cost = Column(Numeric(10, 2), nullable=True)  # Historical average cost
    last_cost_update = Column(DateTime(timezone=True), nullable=True)
    cost_method = Column(String, nullable=True, default='WEIGHTED_AVERAGE')  # FIFO, LIFO, WEIGHTED_AVERAGE

    # Product details
    internal_sku = Column(String, nullable=True, index=True)  # Internal restaurant SKU (alias for sku)
    sku = Column(String, nullable=True, index=True)  # Internal SKU (keep for compatibility)
    barcode = Column(String, nullable=True, index=True)  # For scanning during counts
    barcode_type = Column(String, nullable=True)  # UPC, EAN, CODE128, QR, etc.
    par_level = Column(Numeric(10, 3), nullable=True)  # Default par level for all locations

    # Recipe and reporting
    is_recipe_ingredient = Column(Boolean, default=True)  # Can be used in recipes
    reporting_tags = Column(Text, nullable=True)  # Comma-separated tags for reporting

    # Legacy vendor field (DEPRECATED - use vendor_items relationship instead)
    vendor_id = Column(Integer, ForeignKey("vendors.id", ondelete="SET NULL"), nullable=True, index=True)

    # Relationships
    vendor = relationship("Vendor", backref="items")  # DEPRECATED - use vendor_items
    unit = relationship("UnitOfMeasure", foreign_keys=[unit_of_measure_id], backref="master_items_primary")
    secondary_unit_rel = relationship("UnitOfMeasure", foreign_keys=[secondary_unit_id], backref="master_items_secondary")

    # Key Item flag - highlight important items for tracking
    is_key_item = Column(Boolean, default=False)

    # Additional count units (for flexible counting - e.g., count by case OR by each)
    count_unit_2_id = Column(Integer, ForeignKey("units_of_measure.id"), nullable=True)
    count_unit_3_id = Column(Integer, ForeignKey("units_of_measure.id"), nullable=True)

    # Relationships for additional count units
    count_unit_2 = relationship("UnitOfMeasure", foreign_keys=[count_unit_2_id], backref="master_items_count2")
    count_unit_3 = relationship("UnitOfMeasure", foreign_keys=[count_unit_3_id], backref="master_items_count3")

    # Status
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<MasterItem(id={self.id}, name={self.name}, category={self.category})>"
