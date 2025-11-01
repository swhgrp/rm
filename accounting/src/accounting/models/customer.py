"""
Customer model for Accounts Receivable
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, DECIMAL
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from accounting.db.database import Base


class Customer(Base):
    """
    Customers for Accounts Receivable
    Tracks customer information for catering, events, and invoicing
    """
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)

    # Basic customer information
    customer_name = Column(String(200), nullable=False, unique=True, index=True)
    customer_code = Column(String(50), nullable=True, unique=True, index=True)  # Short code/abbreviation
    customer_type = Column(String(50), nullable=True)  # Catering, Events, Corporate, etc.

    # Contact information
    contact_name = Column(String(200), nullable=True)
    email = Column(String(100), nullable=True)
    phone = Column(String(20), nullable=True)
    mobile = Column(String(20), nullable=True)
    fax = Column(String(20), nullable=True)
    website = Column(String(200), nullable=True)

    # Address information
    address_line1 = Column(String(200), nullable=True)
    address_line2 = Column(String(200), nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(50), nullable=True)
    zip_code = Column(String(20), nullable=True)
    country = Column(String(100), nullable=True, default="United States")

    # Billing information
    billing_email = Column(String(100), nullable=True)  # Separate billing contact
    billing_contact = Column(String(200), nullable=True)

    # Tax information
    tax_exempt = Column(Boolean, nullable=False, default=False)
    tax_exempt_id = Column(String(50), nullable=True)  # Tax exemption certificate number
    tax_rate = Column(DECIMAL(5, 2), nullable=True)  # Override default tax rate if needed

    # Payment terms
    payment_terms = Column(String(50), nullable=True)  # e.g., "Net 30", "Net 15", "Due on Receipt"
    credit_limit = Column(DECIMAL(15, 2), nullable=True)  # Credit limit in dollars

    # Pricing
    discount_percentage = Column(DECIMAL(5, 2), nullable=True)  # Default discount %

    # Notes
    notes = Column(Text, nullable=True)

    # Status
    is_active = Column(Boolean, nullable=False, default=True)

    # Audit fields
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=True, onupdate=func.now())

    # Relationships
    # customer_invoices = relationship("CustomerInvoice", back_populates="customer")
    recurring_invoices = relationship("RecurringInvoice", back_populates="customer")

    def __repr__(self):
        return f"<Customer {self.customer_code or self.id}: {self.customer_name}>"
