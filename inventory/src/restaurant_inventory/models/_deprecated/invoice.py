"""
Invoice Models
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey, Enum, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from restaurant_inventory.db.database import Base


class InvoiceStatus(str, enum.Enum):
    """Invoice processing status"""
    UPLOADED = "UPLOADED"           # File uploaded, not yet parsed
    PARSING = "PARSING"             # AI parsing in progress
    PARSED = "PARSED"               # Parsed, awaiting review
    NEEDS_MAPPING = "NEEDS_MAPPING" # Has unmapped line items
    REVIEWED = "REVIEWED"           # Reviewed by user, ready to approve
    APPROVED = "APPROVED"           # Approved, inventory updated
    REJECTED = "REJECTED"           # Rejected, won't process


class Invoice(Base):
    """Invoice header information"""
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)

    # File information
    filename = Column(String(500), nullable=False)
    file_path = Column(String(1000), nullable=False)
    file_type = Column(String(50), nullable=False)  # pdf, jpg, png

    # Invoice details (will be auto-filled by AI during parsing)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    invoice_number = Column(String(200), nullable=True)
    invoice_date = Column(DateTime(timezone=True), nullable=True)
    due_date = Column(DateTime(timezone=True), nullable=True)

    # Totals
    subtotal = Column(Float, nullable=True)
    tax = Column(Float, nullable=True)
    total = Column(Float, nullable=True)

    # Processing
    status = Column(Enum(InvoiceStatus), default=InvoiceStatus.UPLOADED, nullable=False)

    # AI parsing results (raw JSON from OpenAI)
    parsed_data = Column(JSON, nullable=True)

    # Confidence score from AI (0-1)
    confidence_score = Column(Float, nullable=True)

    # Notes and anomalies
    notes = Column(Text, nullable=True)
    anomalies = Column(JSON, nullable=True)  # List of detected issues

    # Audit fields
    uploaded_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Nullable for hub imports
    reviewed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    vendor = relationship("Vendor", backref="invoices")
    location = relationship("Location", backref="invoices")
    uploaded_by = relationship("User", foreign_keys=[uploaded_by_id])
    reviewed_by = relationship("User", foreign_keys=[reviewed_by_id])
    approved_by = relationship("User", foreign_keys=[approved_by_id])
    items = relationship("InvoiceItem", back_populates="invoice", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Invoice(id={self.id}, vendor={self.vendor_id}, total={self.total}, status={self.status})>"


class InvoiceItem(Base):
    """Individual line items from invoices"""
    __tablename__ = "invoice_items"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False)

    # Line item details from invoice
    line_number = Column(Integer, nullable=True)
    description = Column(Text, nullable=False)
    vendor_sku = Column(String(200), nullable=True)
    quantity = Column(Float, nullable=False)
    unit = Column(String(50), nullable=True)
    pack_size = Column(String(100), nullable=True)  # e.g., "Case - 6", "Case - 24", "Each"
    unit_price = Column(Float, nullable=False)
    line_total = Column(Float, nullable=False)

    # Mapping to vendor items (primary mapping method)
    vendor_item_id = Column(Integer, ForeignKey("vendor_items.id"), nullable=True)

    # Mapping to master items (legacy/deprecated - use vendor_item_id instead)
    master_item_id = Column(Integer, ForeignKey("master_items.id"), nullable=True)
    mapping_confidence = Column(Float, nullable=True)  # AI confidence in mapping (0-1)
    mapping_method = Column(String(50), nullable=True)  # 'auto', 'manual', 'confirmed'

    # Mapping pack size to unit of measure
    unit_of_measure_id = Column(Integer, ForeignKey("units_of_measure.id"), nullable=True)

    # Price comparison
    last_price = Column(Float, nullable=True)  # Previous price for this item
    price_change_pct = Column(Float, nullable=True)  # % change from last price
    is_anomaly = Column(String(100), nullable=True)  # 'price_spike', 'new_item', etc.

    # Audit
    mapped_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    mapped_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    invoice = relationship("Invoice", back_populates="items")
    vendor_item = relationship("VendorItem", backref="invoice_items")
    master_item = relationship("MasterItem", backref="invoice_items")
    unit_of_measure = relationship("UnitOfMeasure", backref="invoice_items")
    mapped_by = relationship("User", foreign_keys=[mapped_by_id])

    def __repr__(self):
        return f"<InvoiceItem(id={self.id}, description='{self.description}', quantity={self.quantity}, unit_price={self.unit_price})>"
