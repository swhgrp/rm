"""
Vendor model for Accounts Payable
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from accounting.db.database import Base


class Vendor(Base):
    """
    Vendors/Suppliers for Accounts Payable
    Tracks vendor information for bill entry and payment
    """
    __tablename__ = "vendors"

    id = Column(Integer, primary_key=True, index=True)

    # Basic vendor information
    vendor_name = Column(String(200), nullable=False, unique=True, index=True)
    vendor_code = Column(String(50), nullable=True, unique=True, index=True)  # Short code/abbreviation

    # Contact information
    contact_name = Column(String(200), nullable=True)
    email = Column(String(100), nullable=True)
    phone = Column(String(20), nullable=True)
    fax = Column(String(20), nullable=True)
    website = Column(String(200), nullable=True)

    # Address information
    address_line1 = Column(String(200), nullable=True)
    address_line2 = Column(String(200), nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(50), nullable=True)
    zip_code = Column(String(20), nullable=True)
    country = Column(String(100), nullable=True, default="United States")

    # Tax information
    tax_id = Column(String(50), nullable=True)  # EIN/SSN for 1099 reporting
    is_1099_vendor = Column(Boolean, nullable=False, default=False)  # Subject to 1099 reporting

    # Payment terms
    payment_terms = Column(String(50), nullable=True)  # e.g., "Net 30", "Net 15", "Due on Receipt"
    credit_limit = Column(Integer, nullable=True)  # Credit limit in dollars

    # Account information
    account_number = Column(String(100), nullable=True)  # Our account number with this vendor

    # Notes
    notes = Column(Text, nullable=True)

    # Status
    is_active = Column(Boolean, nullable=False, default=True)

    # Audit fields
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=True, onupdate=func.now())

    # Relationships
    # vendor_bills = relationship("VendorBill", back_populates="vendor")  # Will add after migration

    def __repr__(self):
        return f"<Vendor {self.vendor_code or self.id}: {self.vendor_name}>"
