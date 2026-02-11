"""
Hub Invoice Item model - Line items with mapping to inventory and GL accounts
"""
from sqlalchemy import Column, Integer, String, Numeric, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from integration_hub.db.database import Base


class HubInvoiceItem(Base):
    """Invoice line items with mapping information"""
    __tablename__ = "hub_invoice_items"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("hub_invoices.id"), nullable=False, index=True)

    # Item details from invoice
    line_number = Column(Integer, nullable=True)
    item_description = Column(String(500), nullable=False)
    item_code = Column(String(100), nullable=True)  # Vendor's item code
    quantity = Column(Numeric(10, 3), nullable=False)
    unit_of_measure = Column(String(50), nullable=True)  # CS, EA, LB, GAL, etc.
    pack_size = Column(Integer, nullable=True)  # Units per case (e.g., 12 for a 12-pack)
    unit_price = Column(Numeric(10, 4), nullable=False)
    total_amount = Column(Numeric(12, 4), nullable=False)

    # Mapping to inventory system
    inventory_item_id = Column(Integer, nullable=True, index=True)  # Master item ID
    inventory_item_name = Column(String(200), nullable=True)
    inventory_category = Column(String(100), nullable=True)

    # Mapping to accounting system GL accounts
    gl_asset_account = Column(Integer, nullable=True)  # e.g., 1418 Poultry Inventory
    gl_cogs_account = Column(Integer, nullable=True)   # e.g., 5118 Poultry Cost
    gl_waste_account = Column(Integer, nullable=True)  # e.g., 7180 Waste Expense

    # Mapping status
    is_mapped = Column(Boolean, default=False, index=True)
    mapped_by = Column(Integer, nullable=True)  # User ID who mapped it
    mapped_at = Column(DateTime(timezone=True), nullable=True)
    mapping_method = Column(String(50), nullable=True)  # 'auto', 'manual', 'suggested'

    # AI/Auto-mapping confidence
    mapping_confidence = Column(Numeric(3, 2), nullable=True)  # 0.00 to 1.00
    suggested_item_id = Column(Integer, nullable=True)  # AI suggestion

    # UOM pricing flag - set at mapping time from vendor item data
    # True = unit_price is per individual unit (EA/BTL), False = per case (CS)
    price_is_per_unit = Column(Boolean, nullable=True)

    # Notes
    notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    invoice = relationship("HubInvoice", back_populates="items")

    @property
    def line_total(self):
        """Alias for total_amount to match service expectations"""
        return self.total_amount

    def __repr__(self):
        return f"<HubInvoiceItem(id={self.id}, desc={self.item_description[:30]}, mapped={self.is_mapped})>"
