"""
Item to GL Account Mapping - Master mapping table for automatic matching
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, UniqueConstraint
from sqlalchemy.sql import func
from integration_hub.db.database import Base


class ItemGLMapping(Base):
    """
    Master mapping table: Inventory Item → GL Accounts
    Used for automatic mapping of future invoices
    """
    __tablename__ = "item_gl_mapping"

    id = Column(Integer, primary_key=True, index=True)

    # Inventory system reference
    inventory_item_id = Column(Integer, nullable=False, index=True)
    inventory_item_name = Column(String(200), nullable=False)
    inventory_category = Column(String(100), nullable=False, index=True)

    # Vendor-specific mapping (optional)
    vendor_id = Column(Integer, nullable=True, index=True)
    vendor_item_code = Column(String(100), nullable=True)

    # Accounting GL accounts
    gl_asset_account = Column(Integer, nullable=False)     # 1418 Poultry Inventory
    gl_cogs_account = Column(Integer, nullable=False)      # 5118 Poultry Cost
    gl_waste_account = Column(Integer, nullable=True)      # 7180 Waste Expense
    gl_revenue_account = Column(Integer, nullable=True)    # 4100 Food Sales

    # Account names (for display)
    asset_account_name = Column(String(200), nullable=True)
    cogs_account_name = Column(String(200), nullable=True)

    # Mapping metadata
    is_active = Column(Boolean, default=True, index=True)
    created_by = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Ensure unique mapping per inventory item
    __table_args__ = (
        UniqueConstraint('inventory_item_id', name='uq_inventory_item_mapping'),
    )

    def __repr__(self):
        return f"<ItemGLMapping(item_id={self.inventory_item_id}, asset={self.gl_asset_account}, cogs={self.gl_cogs_account})>"


class CategoryGLMapping(Base):
    """
    Category-level GL account mapping (fallback when specific item not mapped)
    """
    __tablename__ = "category_gl_mapping"

    id = Column(Integer, primary_key=True, index=True)
    inventory_category = Column(String(100), unique=True, nullable=False, index=True)

    # Default GL accounts for this category
    gl_asset_account = Column(Integer, nullable=False)
    gl_cogs_account = Column(Integer, nullable=False)
    gl_waste_account = Column(Integer, nullable=True)
    gl_revenue_account = Column(Integer, nullable=True)

    # Account names
    asset_account_name = Column(String(200), nullable=True)
    cogs_account_name = Column(String(200), nullable=True)

    # Metadata
    is_active = Column(Boolean, default=True)
    notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<CategoryGLMapping(category={self.inventory_category}, asset={self.gl_asset_account})>"
