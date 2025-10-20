"""
Inventory Transaction model for tracking all inventory movements

This model provides a complete audit trail of all inventory changes:
- POS sales deductions
- Receiving/purchases
- Transfers between locations
- Waste
- Manual adjustments
- Physical counts
"""

from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, Text, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from restaurant_inventory.db.database import Base


class TransactionType(str, enum.Enum):
    """Types of inventory transactions"""
    POS_SALE = "pos_sale"  # Deduction from POS sale
    PURCHASE = "purchase"  # Receiving from vendor
    TRANSFER_OUT = "transfer_out"  # Transfer to another location
    TRANSFER_IN = "transfer_in"  # Transfer from another location
    WASTE = "waste"  # Waste/spoilage
    ADJUSTMENT = "adjustment"  # Manual adjustment
    COUNT = "count"  # Physical count adjustment
    PRODUCTION = "production"  # Recipe production (deduct ingredients, add finished item)


class InventoryTransaction(Base):
    """
    Records all inventory movements for audit trail and reporting.
    Each transaction affects the current_quantity in the Inventory table.
    """
    __tablename__ = "inventory_transactions"

    id = Column(Integer, primary_key=True, index=True)

    # What item and where
    master_item_id = Column(Integer, ForeignKey("master_items.id"), nullable=False, index=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True, index=True)
    storage_area_id = Column(Integer, ForeignKey("storage_areas.id"), nullable=True)

    # Transaction details
    transaction_type = Column(String(50), nullable=False, index=True)  # Use String for Postgres enum
    transaction_date = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # Quantity changes (positive = increase, negative = decrease)
    quantity_change = Column(Numeric(10, 3), nullable=False)  # The delta applied to inventory
    unit_of_measure = Column(String(50), nullable=True)

    # Before/after snapshot
    quantity_before = Column(Numeric(10, 3), nullable=True)
    quantity_after = Column(Numeric(10, 3), nullable=True)

    # Costing
    unit_cost = Column(Numeric(10, 4), nullable=True)  # Cost per unit at time of transaction
    total_cost = Column(Numeric(12, 4), nullable=True)  # quantity_change * unit_cost

    # References to source documents
    pos_sale_id = Column(Integer, ForeignKey("pos_sales.id"), nullable=True, index=True)
    pos_sale_item_id = Column(Integer, ForeignKey("pos_sale_items.id"), nullable=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=True)
    transfer_id = Column(Integer, ForeignKey("transfers.id"), nullable=True)
    waste_id = Column(Integer, ForeignKey("waste.id"), nullable=True)
    count_session_id = Column(Integer, ForeignKey("count_sessions.id"), nullable=True)
    recipe_id = Column(Integer, ForeignKey("recipes.id"), nullable=True)  # If from recipe production

    # Audit info
    reason = Column(Text, nullable=True)  # Human-readable reason for transaction
    notes = Column(Text, nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    master_item = relationship("MasterItem")
    location = relationship("Location")
    storage_area = relationship("StorageArea")
    pos_sale = relationship("POSSale")
    pos_sale_item = relationship("POSSaleItem")
    created_by = relationship("User")
    recipe = relationship("Recipe")

    def __repr__(self):
        return f"<InventoryTransaction(id={self.id}, item_id={self.master_item_id}, type={self.transaction_type}, qty={self.quantity_change})>"
