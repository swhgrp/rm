"""
CSV Expected Vendor model

Tracks which vendor+location combinations receive CSV invoices via fintech
or other electronic sources. When a PDF arrives for a CSV-expected vendor+location,
it is stored as reference only (not parsed/mapped/sent).
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, UniqueConstraint
from sqlalchemy.sql import func
from integration_hub.db.database import Base


class CsvExpectedVendor(Base):
    """
    Vendor+location combinations where CSV invoices are expected.
    PDFs from these vendors will be marked as 'pdf_reference' instead of being parsed.
    """
    __tablename__ = "csv_expected_vendors"
    __table_args__ = (
        UniqueConstraint('vendor_id', 'location_id', name='uq_csv_expected_vendor_location'),
    )

    id = Column(Integer, primary_key=True, index=True)

    # Vendor (references hub vendors table)
    vendor_id = Column(Integer, nullable=False, index=True)

    # Location (NULL = all locations for this vendor)
    location_id = Column(Integer, nullable=True, index=True)
    location_name = Column(String(100), nullable=True)

    # Source info (for reference)
    distributor_name = Column(String(200), nullable=True)  # Official name from fintech
    customer_id = Column(String(100), nullable=True)  # Account number with distributor
    store_id = Column(String(50), nullable=True)  # Store ID from fintech

    # Control
    is_active = Column(Boolean, default=True, nullable=False)
    notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<CsvExpectedVendor(vendor_id={self.vendor_id}, location_id={self.location_id})>"
