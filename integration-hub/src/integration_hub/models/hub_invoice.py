"""
Hub Invoice model - Central storage for all incoming invoices
"""
from sqlalchemy import Column, Integer, String, Date, Numeric, DateTime, Boolean, Text, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from integration_hub.db.database import Base


class HubInvoice(Base):
    """Central invoice storage before routing to systems"""
    __tablename__ = "hub_invoices"

    id = Column(Integer, primary_key=True, index=True)

    # Vendor information
    vendor_id = Column(Integer, nullable=True)  # If mapped to inventory vendor
    vendor_name = Column(String(200), nullable=False)
    vendor_account_number = Column(String(100), nullable=True)

    # Invoice details
    invoice_number = Column(String(100), nullable=False, index=True)
    invoice_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=True)
    total_amount = Column(Numeric(12, 2), nullable=False)
    tax_amount = Column(Numeric(12, 2), nullable=True)

    # Source tracking
    source = Column(String(50), nullable=False)  # 'email', 'upload', 'api'
    source_email = Column(String(200), nullable=True)  # If from email
    source_filename = Column(String(500), nullable=True)  # If uploaded
    raw_data = Column(JSON, nullable=True)  # Original invoice data

    # Email monitoring fields
    pdf_path = Column(String(1000), nullable=True)  # Path to stored PDF
    invoice_hash = Column(String(64), nullable=True, unique=True, index=True)  # SHA-256 hash for deduplication
    email_subject = Column(String(500), nullable=True)  # Original email subject
    email_from = Column(String(200), nullable=True)  # Sender email address
    email_received_at = Column(DateTime(timezone=True), nullable=True)  # When email was received

    # Location/Area
    location_id = Column(Integer, nullable=True)
    location_name = Column(String(100), nullable=True)

    # Statement flag (statements don't get sent to inventory/accounting)
    is_statement = Column(Boolean, default=False, index=True)

    # Routing status
    sent_to_inventory = Column(Boolean, default=False)
    sent_to_accounting = Column(Boolean, default=False)
    inventory_sync_at = Column(DateTime(timezone=True), nullable=True)
    accounting_sync_at = Column(DateTime(timezone=True), nullable=True)
    inventory_sync_error = Column(Text, nullable=True)
    accounting_sync_error = Column(Text, nullable=True)

    # System references (IDs from remote systems)
    inventory_invoice_id = Column(Integer, nullable=True)
    accounting_je_id = Column(Integer, nullable=True)

    # Service-compatible error columns (aliases for sync_error columns)
    inventory_error = Column(Text, nullable=True)
    accounting_error = Column(Text, nullable=True)

    # Overall status
    status = Column(String(50), default='pending', index=True)
    # 'pending' - just received
    # 'mapping' - items being mapped
    # 'ready' - all items mapped, ready to send
    # 'sent' - sent to both systems
    # 'error' - sync error
    # 'partial' - sent to one system but not other

    # Approval tracking
    approved_by = Column(Integer, nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    items = relationship("HubInvoiceItem", back_populates="invoice", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<HubInvoice(id={self.id}, vendor={self.vendor_name}, invoice_num={self.invoice_number})>"
