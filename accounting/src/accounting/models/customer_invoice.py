"""
Customer Invoice models for Accounts Receivable
"""
from sqlalchemy import Column, Integer, String, DECIMAL, Date, DateTime, Text, ForeignKey, Boolean, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from accounting.db.database import Base
import enum


class InvoiceStatus(str, enum.Enum):
    """Invoice lifecycle status"""
    DRAFT = "draft"  # Being created, not sent
    SENT = "sent"  # Sent to customer, awaiting payment
    PARTIALLY_PAID = "partially_paid"  # Some payments received
    PAID = "paid"  # Fully paid
    OVERDUE = "overdue"  # Past due date, not paid
    VOID = "void"  # Cancelled/voided


class CustomerInvoice(Base):
    """
    Customer invoices for Accounts Receivable
    Tracks what customers owe for catering, events, etc.
    """
    __tablename__ = "customer_invoices"

    id = Column(Integer, primary_key=True, index=True)

    # Customer information - link to customers table
    customer_id = Column(Integer, ForeignKey('customers.id', ondelete='RESTRICT'), nullable=False, index=True)

    # Invoice identification
    invoice_number = Column(String(100), nullable=False, unique=True, index=True)

    # Dates
    invoice_date = Column(Date, nullable=False, index=True)
    due_date = Column(Date, nullable=False, index=True)
    event_date = Column(Date, nullable=True)  # For catering/events

    # Event/Catering details
    event_type = Column(String(100), nullable=True)  # Catering, Wedding, Corporate Event, etc.
    event_location = Column(String(200), nullable=True)
    guest_count = Column(Integer, nullable=True)

    # Amounts
    subtotal = Column(DECIMAL(15, 2), nullable=False, default=0)
    discount_amount = Column(DECIMAL(15, 2), nullable=False, default=0)  # Total discount
    tax_amount = Column(DECIMAL(15, 2), nullable=False, default=0)
    deposit_amount = Column(DECIMAL(15, 2), nullable=False, default=0)  # Deposit/prepayment received
    total_amount = Column(DECIMAL(15, 2), nullable=False)  # Final amount owed
    paid_amount = Column(DECIMAL(15, 2), nullable=False, default=0)  # Amount paid so far

    # Location/Area
    area_id = Column(Integer, ForeignKey('areas.id', ondelete='SET NULL'), nullable=True, index=True)

    # Status
    status = Column(SQLEnum(InvoiceStatus), nullable=False, default=InvoiceStatus.DRAFT, index=True)

    # Tax
    is_tax_exempt = Column(Boolean, nullable=False, default=False)
    tax_rate = Column(DECIMAL(5, 2), nullable=True)  # Tax rate used

    # Reference and notes
    po_number = Column(String(100), nullable=True)  # Customer's PO number
    reference_number = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    terms_conditions = Column(Text, nullable=True)

    # Accounting integration
    journal_entry_id = Column(Integer, ForeignKey('journal_entries.id', ondelete='SET NULL'), nullable=True)

    # Recurring invoice tracking
    recurring_invoice_id = Column(Integer, ForeignKey('recurring_invoices.id', ondelete='SET NULL'), nullable=True)

    # Audit fields
    created_by = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    sent_date = Column(DateTime, nullable=True)  # When invoice was sent to customer

    # Relationships
    customer = relationship("Customer", foreign_keys=[customer_id])
    recurring_invoice = relationship("RecurringInvoice")
    area = relationship("Area")
    line_items = relationship("CustomerInvoiceLine", back_populates="invoice", cascade="all, delete-orphan")
    payments = relationship("InvoicePayment", back_populates="invoice", cascade="all, delete-orphan")
    creator = relationship("User", foreign_keys=[created_by])
    journal_entry = relationship("JournalEntry", foreign_keys=[journal_entry_id])

    @property
    def balance_due(self):
        """Calculate remaining balance after deposits and payments"""
        return self.total_amount - self.deposit_amount - self.paid_amount

    @property
    def is_overdue(self):
        """Check if invoice is past due date"""
        from datetime import date
        if self.status in [InvoiceStatus.PAID, InvoiceStatus.VOID]:
            return False
        return self.due_date < date.today() and self.balance_due > 0

    @property
    def days_until_due(self):
        """Calculate days until due (negative if overdue)"""
        from datetime import date
        return (self.due_date - date.today()).days


class CustomerInvoiceLine(Base):
    """
    Line items for customer invoices
    Allows invoices to have multiple items/services
    """
    __tablename__ = "customer_invoice_lines"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey('customer_invoices.id', ondelete='CASCADE'), nullable=False, index=True)

    # GL Account (where this revenue is recorded)
    account_id = Column(Integer, ForeignKey('accounts.id', ondelete='RESTRICT'), nullable=False)

    # Location (can differ from invoice header for allocated revenue)
    area_id = Column(Integer, ForeignKey('areas.id', ondelete='SET NULL'), nullable=True, index=True)

    # Line details
    description = Column(Text, nullable=True)
    quantity = Column(DECIMAL(10, 2), nullable=True, default=1)
    unit_price = Column(DECIMAL(15, 2), nullable=False)
    amount = Column(DECIMAL(15, 2), nullable=False)  # Line total (qty * price before discount/tax)

    # Discount
    discount_percentage = Column(DECIMAL(5, 2), nullable=True)
    discount_amount = Column(DECIMAL(15, 2), nullable=False, default=0)

    # Tax tracking
    is_taxable = Column(Boolean, nullable=False, default=True)
    tax_amount = Column(DECIMAL(15, 2), nullable=False, default=0)

    # Ordering
    line_number = Column(Integer, nullable=True)

    # Relationships
    invoice = relationship("CustomerInvoice", back_populates="line_items")
    account = relationship("Account")
    area = relationship("Area")


class InvoicePayment(Base):
    """
    Payments received from customers against invoices
    Tracks payment history and methods
    """
    __tablename__ = "invoice_payments"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey('customer_invoices.id', ondelete='CASCADE'), nullable=False, index=True)

    # Payment details
    payment_date = Column(Date, nullable=False, index=True)
    amount = Column(DECIMAL(15, 2), nullable=False)
    payment_method = Column(String(50), nullable=False)  # Cash, Check, Credit Card, ACH, etc.

    # Payment reference
    reference_number = Column(String(100), nullable=True, index=True)  # Check number, confirmation, etc.

    # Bank account where deposited (link to GL account)
    bank_account_id = Column(Integer, ForeignKey('accounts.id', ondelete='RESTRICT'), nullable=False)

    # Is this a deposit/prepayment?
    is_deposit = Column(Boolean, nullable=False, default=False)

    # Notes
    notes = Column(Text, nullable=True)

    # Accounting integration
    journal_entry_id = Column(Integer, ForeignKey('journal_entries.id', ondelete='SET NULL'), nullable=True)

    # Audit fields
    created_by = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    # Relationships
    invoice = relationship("CustomerInvoice", back_populates="payments")
    bank_account = relationship("Account", foreign_keys=[bank_account_id])
    creator = relationship("User", foreign_keys=[created_by])
    journal_entry = relationship("JournalEntry", foreign_keys=[journal_entry_id])
