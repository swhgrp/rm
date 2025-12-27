"""
Master Item Location Cost model

Stores the current weighted average cost for each master item at each location.
This is the core of location-aware costing.

Architecture (Location-Aware Costing):
- Hub owns: UOM (global), Categories (global), Vendor Items (per location)
- Inventory owns: Master Items, Count Units, Location Costs
"""

from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, UniqueConstraint, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from restaurant_inventory.db.database import Base


class MasterItemLocationCost(Base):
    """
    Current cost snapshot for a master item at a specific location.

    This is the single source of truth for item costs used in:
    - Recipe costing
    - Menu pricing
    - Inventory valuation
    - COGS reporting

    Costs are always in terms of the item's PRIMARY count unit.

    Weighted Average Cost Calculation:
    new_cost = (old_cost * old_qty + purchase_cost * purchase_qty) / (old_qty + purchase_qty)

    Example:
    - Current: 50 lbs @ $2.00/lb = $100 value
    - Purchase: 40 lbs @ $2.50/lb = $100 value
    - New weighted avg: (100 + 100) / (50 + 40) = $2.22/lb
    """
    __tablename__ = "master_item_location_costs"
    __table_args__ = (
        UniqueConstraint('master_item_id', 'location_id', name='uq_master_item_location'),
    )

    id = Column(Integer, primary_key=True, index=True)

    # Link to master item
    master_item_id = Column(Integer, ForeignKey("master_items.id", ondelete="CASCADE"), nullable=False, index=True)

    # Link to location
    location_id = Column(Integer, ForeignKey("locations.id", ondelete="CASCADE"), nullable=False, index=True)

    # Current weighted average cost per PRIMARY count unit
    # Example: $2.22 per pound, $7.50 per bottle
    current_weighted_avg_cost = Column(Numeric(12, 4), nullable=True)

    # Total quantity on hand in PRIMARY count units
    # Used for weighted average calculation
    total_qty_on_hand = Column(Numeric(12, 4), default=0.0)

    # Last purchase info (for reference)
    last_purchase_cost = Column(Numeric(12, 4), nullable=True)  # Per primary unit
    last_purchase_qty = Column(Numeric(12, 4), nullable=True)  # In primary units
    last_purchase_date = Column(DateTime(timezone=True), nullable=True)
    last_vendor_id = Column(Integer, nullable=True)  # Hub vendor ID

    # Timestamps
    last_updated = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    master_item = relationship("MasterItem", back_populates="location_costs")
    location = relationship("Location", backref="item_costs")

    def __repr__(self):
        cost = f"${float(self.current_weighted_avg_cost):.4f}" if self.current_weighted_avg_cost else "N/A"
        return f"<MasterItemLocationCost(item={self.master_item_id}, location={self.location_id}, cost={cost})>"

    def apply_purchase(self, purchase_qty: float, purchase_cost_per_unit: float) -> float:
        """
        Apply a purchase to update weighted average cost.

        Args:
            purchase_qty: Quantity purchased (in PRIMARY count units)
            purchase_cost_per_unit: Cost per primary unit

        Returns:
            New weighted average cost
        """
        old_qty = float(self.total_qty_on_hand or 0)
        old_cost = float(self.current_weighted_avg_cost or 0)

        # Calculate total values
        old_value = old_qty * old_cost
        new_value = purchase_qty * purchase_cost_per_unit
        total_qty = old_qty + purchase_qty

        # Calculate new weighted average
        if total_qty > 0:
            new_cost = (old_value + new_value) / total_qty
        else:
            new_cost = purchase_cost_per_unit

        # Update fields
        self.current_weighted_avg_cost = new_cost
        self.total_qty_on_hand = total_qty
        self.last_purchase_cost = purchase_cost_per_unit
        self.last_purchase_qty = purchase_qty

        return new_cost

    def apply_usage(self, usage_qty: float) -> float:
        """
        Apply usage (sales, waste, transfers out) to update quantity on hand.
        Does NOT change the weighted average cost.

        Args:
            usage_qty: Quantity used (in PRIMARY count units)

        Returns:
            Remaining quantity on hand
        """
        current_qty = float(self.total_qty_on_hand or 0)
        new_qty = max(0, current_qty - usage_qty)
        self.total_qty_on_hand = new_qty
        return new_qty


class MasterItemLocationCostHistory(Base):
    """
    History of cost changes for audit and analysis.

    Records every cost change event for a master item at a location.
    Used for:
    - Audit trail
    - Price trend analysis
    - Vendor cost comparison
    """
    __tablename__ = "master_item_location_cost_history"

    id = Column(Integer, primary_key=True, index=True)

    # Link to the cost record
    location_cost_id = Column(Integer, ForeignKey("master_item_location_costs.id", ondelete="CASCADE"), nullable=False, index=True)

    # Denormalized for easier querying
    master_item_id = Column(Integer, nullable=False, index=True)
    location_id = Column(Integer, nullable=False, index=True)

    # What changed
    event_type = Column(String(50), nullable=False)  # 'purchase', 'adjustment', 'transfer_in', 'initial'

    # Before state
    old_cost = Column(Numeric(12, 4), nullable=True)
    old_qty = Column(Numeric(12, 4), nullable=True)

    # Change details
    change_qty = Column(Numeric(12, 4), nullable=True)  # Positive for additions, negative for reductions
    change_cost_per_unit = Column(Numeric(12, 4), nullable=True)  # Cost per unit of the change

    # After state
    new_cost = Column(Numeric(12, 4), nullable=True)
    new_qty = Column(Numeric(12, 4), nullable=True)

    # Source info
    vendor_id = Column(Integer, nullable=True)  # Hub vendor ID
    invoice_id = Column(Integer, nullable=True)  # Hub invoice ID
    notes = Column(Text, nullable=True)

    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    location_cost = relationship("MasterItemLocationCost", backref="history")

    def __repr__(self):
        return f"<CostHistory(item={self.master_item_id}, loc={self.location_id}, event={self.event_type}, old=${self.old_cost} new=${self.new_cost})>"
