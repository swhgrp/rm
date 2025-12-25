"""
Price History model

Tracks price changes for vendor items over time.
Records are created when invoice prices differ from the current unit_price.
"""

from sqlalchemy import Column, Integer, Numeric, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from integration_hub.db.database import Base


class PriceHistory(Base):
    """
    Price History - tracks historical prices for vendor items.

    A new record is created whenever an invoice has a different price
    than the current vendor item unit_price.
    """
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, index=True)

    # Link to vendor item
    vendor_item_id = Column(Integer, ForeignKey("hub_vendor_items.id", ondelete="CASCADE"), nullable=False, index=True)

    # Price info
    old_price = Column(Numeric(10, 2), nullable=True)  # Previous price (NULL if first record)
    new_price = Column(Numeric(10, 2), nullable=False)  # New price from invoice
    price_change = Column(Numeric(10, 2), nullable=True)  # Difference (new - old)
    price_change_pct = Column(Numeric(8, 4), nullable=True)  # Percentage change

    # Source info
    invoice_id = Column(Integer, ForeignKey("hub_invoices.id", ondelete="SET NULL"), nullable=True, index=True)
    invoice_number = Column(String(100), nullable=True)
    invoice_date = Column(DateTime(timezone=True), nullable=True)

    # Quantity from invoice (for reference)
    quantity = Column(Numeric(10, 3), nullable=True)

    # Notes
    notes = Column(Text, nullable=True)

    # Timestamps
    recorded_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    vendor_item = relationship("HubVendorItem", backref="price_history")
    invoice = relationship("HubInvoice", backref="price_changes")

    def __repr__(self):
        return f"<PriceHistory(id={self.id}, vendor_item={self.vendor_item_id}, old={self.old_price}, new={self.new_price})>"
