"""
POS Sales models for tracking sales from point-of-sale systems like Clover
"""

from sqlalchemy import Column, Integer, String, Numeric, DateTime, Boolean, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from restaurant_inventory.db.database import Base


class POSProvider(str, enum.Enum):
    """Supported POS providers"""
    CLOVER = "clover"
    SQUARE = "square"
    TOAST = "toast"
    MANUAL = "manual"


class POSSale(Base):
    """Sales transactions from POS systems"""
    __tablename__ = "pos_sales"

    id = Column(Integer, primary_key=True, index=True)

    # POS Integration
    pos_provider = Column(String(50), nullable=False, default=POSProvider.CLOVER.value)
    pos_order_id = Column(String(255), nullable=False, unique=True, index=True)  # Clover order ID
    pos_merchant_id = Column(String(255), nullable=True)  # Clover merchant ID

    # Order Details
    order_number = Column(String(100), nullable=True)  # Human-readable order number
    order_date = Column(DateTime(timezone=True), nullable=False, index=True)

    # Amounts
    subtotal = Column(Numeric(10, 2), nullable=False)
    tax = Column(Numeric(10, 2), nullable=False, default=0)
    tip = Column(Numeric(10, 2), nullable=False, default=0)
    discount = Column(Numeric(10, 2), nullable=False, default=0)
    total = Column(Numeric(10, 2), nullable=False)

    # Customer Info
    customer_name = Column(String(200), nullable=True)
    customer_id = Column(String(255), nullable=True)  # POS customer ID

    # Order Type
    order_type = Column(String(50), nullable=True)  # "dine-in", "takeout", "delivery", etc.
    table_number = Column(String(50), nullable=True)

    # Status
    status = Column(String(50), nullable=False, default="completed")  # "completed", "refunded", "voided"
    is_synced = Column(Boolean, default=True)  # Already synced from POS
    inventory_deducted = Column(Boolean, default=False)  # Whether inventory was deducted for this sale

    # Location
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)

    # Metadata
    notes = Column(Text, nullable=True)
    raw_data = Column(Text, nullable=True)  # Store raw JSON from POS for debugging
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    synced_at = Column(DateTime(timezone=True), nullable=True)  # When imported from POS

    # Relationships
    line_items = relationship("POSSaleItem", back_populates="sale", cascade="all, delete-orphan")
    location = relationship("Location", foreign_keys=[location_id])

    def __repr__(self):
        return f"<POSSale(id={self.id}, pos_order_id='{self.pos_order_id}', total={self.total})>"


class POSSaleItem(Base):
    """Individual line items from POS sales"""
    __tablename__ = "pos_sale_items"

    id = Column(Integer, primary_key=True, index=True)
    sale_id = Column(Integer, ForeignKey("pos_sales.id", ondelete="CASCADE"), nullable=False)

    # POS Item Info
    pos_item_id = Column(String(255), nullable=True)  # Clover item ID
    item_name = Column(String(200), nullable=False)
    category = Column(String(100), nullable=True)

    # Mapped Recipe (if linked to our recipe system)
    recipe_id = Column(Integer, ForeignKey("recipes.id"), nullable=True)

    # Quantity and Pricing
    quantity = Column(Numeric(10, 3), nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)
    total_price = Column(Numeric(10, 2), nullable=False)

    # Modifiers/Notes
    modifiers = Column(Text, nullable=True)  # JSON string of modifiers
    notes = Column(Text, nullable=True)

    # Costing (if recipe is linked)
    recipe_cost = Column(Numeric(10, 4), nullable=True)  # Cost of recipe ingredients
    profit_margin = Column(Numeric(10, 2), nullable=True)  # total_price - recipe_cost

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    sale = relationship("POSSale", back_populates="line_items")
    recipe = relationship("Recipe", foreign_keys=[recipe_id])

    def __repr__(self):
        return f"<POSSaleItem(id={self.id}, item_name='{self.item_name}', qty={self.quantity})>"


class POSConfiguration(Base):
    """POS integration configuration for each location"""
    __tablename__ = "pos_configurations"

    id = Column(Integer, primary_key=True, index=True)

    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False, unique=True)

    # POS Provider
    provider = Column(String(50), nullable=False, default=POSProvider.CLOVER.value)

    # API Credentials (encrypted in production!)
    merchant_id = Column(String(255), nullable=True)
    api_key = Column(Text, nullable=True)  # Should be encrypted
    access_token = Column(Text, nullable=True)  # OAuth token, should be encrypted
    refresh_token = Column(Text, nullable=True)  # OAuth refresh token

    # API Configuration
    api_environment = Column(String(50), default="production")  # "sandbox" or "production"
    base_url = Column(String(255), nullable=True)  # Custom base URL

    # Sync Settings
    auto_sync_enabled = Column(Boolean, default=False)
    sync_frequency_minutes = Column(Integer, default=60)  # How often to sync
    last_sync_date = Column(DateTime(timezone=True), nullable=True)

    # Inventory Integration
    auto_deduct_inventory = Column(Boolean, default=False)  # Auto-deduct inventory on sale

    # Active Status
    is_active = Column(Boolean, default=True)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    location = relationship("Location", foreign_keys=[location_id])

    def __repr__(self):
        return f"<POSConfiguration(location_id={self.location_id}, provider='{self.provider}')>"


class POSItemMapping(Base):
    """Maps POS menu items to recipes or master items for cost tracking"""
    __tablename__ = "pos_item_mappings"

    id = Column(Integer, primary_key=True, index=True)

    # POS Item
    pos_provider = Column(String(50), nullable=False)
    pos_item_id = Column(String(255), nullable=False)  # Clover item ID
    pos_item_name = Column(String(200), nullable=False)

    # Mapping Options (must have at least one)
    recipe_id = Column(Integer, ForeignKey("recipes.id"), nullable=True)  # Map to recipe (for complex items)
    master_item_id = Column(Integer, ForeignKey("master_items.id"), nullable=True)  # Map to inventory item (for simple items)

    # Portion Multiplier (if POS portion differs from recipe yield)
    portion_multiplier = Column(Numeric(10, 3), default=1.0)  # e.g., 0.5 for half portion

    # Location (optional - different mappings per location)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)

    # Active Status
    is_active = Column(Boolean, default=True)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    recipe = relationship("Recipe")
    master_item = relationship("MasterItem")
    location = relationship("Location", foreign_keys=[location_id])

    def __repr__(self):
        target = f"recipe={self.recipe_id}" if self.recipe_id else f"item={self.master_item_id}"
        return f"<POSItemMapping(pos_item='{self.pos_item_name}', {target})>"
