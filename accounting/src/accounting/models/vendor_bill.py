"""
Vendor Bill models for Accounts Payable
"""
from sqlalchemy import Column, Integer, String, DECIMAL, Date, DateTime, Text, ForeignKey, Boolean, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from accounting.db.database import Base
import enum


class BillStatus(str, enum.Enum):
    """Bill lifecycle status"""
    DRAFT = "draft"  # Being created, not submitted
    PENDING_APPROVAL = "pending_approval"  # Submitted, awaiting approval
    APPROVED = "approved"  # Approved, ready for payment
    PARTIALLY_PAID = "partially_paid"  # Some payments made
    PAID = "paid"  # Fully paid
    VOID = "void"  # Cancelled/voided


class PaymentMethod(str, enum.Enum):
    """Payment methods"""
    CHECK = "check"
    ACH = "ach"
    WIRE = "wire"
    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    CASH = "cash"
    OTHER = "other"


class VendorBill(Base):
    """
    Vendor bills/invoices for Accounts Payable
    Tracks what the restaurant owes to vendors
    """
    __tablename__ = "vendor_bills"

    id = Column(Integer, primary_key=True, index=True)

    # Vendor information (will link to inventory system vendors later)
    vendor_name = Column(String(200), nullable=False, index=True)
    vendor_id = Column(String(50), nullable=True, index=True)  # External vendor ID from inventory system

    # Bill identification
    bill_number = Column(String(100), nullable=False, index=True)  # Vendor's invoice/bill number

    # Dates
    bill_date = Column(Date, nullable=False, index=True)  # Date on vendor invoice
    due_date = Column(Date, nullable=False, index=True)  # Payment due date
    received_date = Column(Date, nullable=True)  # When we received the bill

    # Amounts
    subtotal = Column(DECIMAL(15, 2), nullable=False, default=0)
    tax_amount = Column(DECIMAL(15, 2), nullable=False, default=0)
    total_amount = Column(DECIMAL(15, 2), nullable=False)  # Total amount owed
    paid_amount = Column(DECIMAL(15, 2), nullable=False, default=0)  # Amount paid so far

    # Location/Area
    area_id = Column(Integer, ForeignKey('areas.id', ondelete='SET NULL'), nullable=True, index=True)

    # Status and workflow
    status = Column(SQLEnum(BillStatus), nullable=False, default=BillStatus.DRAFT, index=True)

    # Approval tracking
    approved_by = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    approved_date = Column(DateTime, nullable=True)
    approval_notes = Column(Text, nullable=True)

    # 1099 tracking
    is_1099_eligible = Column(Boolean, nullable=False, default=False)

    # Reference and notes
    reference_number = Column(String(100), nullable=True)  # PO number, etc.
    description = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)

    # Accounting integration
    journal_entry_id = Column(Integer, ForeignKey('journal_entries.id', ondelete='SET NULL'), nullable=True)

    # Audit fields
    created_by = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    # Relationships
    area = relationship("Area", back_populates="vendor_bills")
    line_items = relationship("VendorBillLine", back_populates="bill", cascade="all, delete-orphan")
    payments = relationship("BillPayment", back_populates="bill", cascade="all, delete-orphan")
    payment_applications = relationship("PaymentApplication", back_populates="vendor_bill")
    payment_discounts = relationship("PaymentDiscount", back_populates="vendor_bill")
    approver = relationship("User", foreign_keys=[approved_by])
    creator = relationship("User", foreign_keys=[created_by])
    journal_entry = relationship("JournalEntry", foreign_keys=[journal_entry_id])

    @property
    def balance_due(self):
        """Calculate remaining balance"""
        return self.total_amount - self.paid_amount

    @property
    def is_overdue(self):
        """Check if bill is past due date"""
        from datetime import date
        if self.status in [BillStatus.PAID, BillStatus.VOID]:
            return False
        return self.due_date < date.today() and self.balance_due > 0

    @property
    def days_until_due(self):
        """Calculate days until due (negative if overdue)"""
        from datetime import date
        return (self.due_date - date.today()).days


class VendorBillLine(Base):
    """
    Line items for vendor bills
    Allows bills to be split across multiple GL accounts and locations
    """
    __tablename__ = "vendor_bill_lines"

    id = Column(Integer, primary_key=True, index=True)
    bill_id = Column(Integer, ForeignKey('vendor_bills.id', ondelete='CASCADE'), nullable=False, index=True)

    # GL Account (where this expense/asset is recorded)
    account_id = Column(Integer, ForeignKey('accounts.id', ondelete='RESTRICT'), nullable=False)

    # Location (can differ from bill header for allocated expenses)
    area_id = Column(Integer, ForeignKey('areas.id', ondelete='SET NULL'), nullable=True, index=True)

    # Line details
    description = Column(Text, nullable=True)
    quantity = Column(DECIMAL(10, 2), nullable=True)
    unit_price = Column(DECIMAL(15, 2), nullable=True)
    amount = Column(DECIMAL(15, 2), nullable=False)  # Line total

    # Tax tracking
    is_taxable = Column(Boolean, nullable=False, default=True)
    tax_amount = Column(DECIMAL(15, 2), nullable=False, default=0)

    # Ordering
    line_number = Column(Integer, nullable=True)

    # Relationships
    bill = relationship("VendorBill", back_populates="line_items")
    account = relationship("Account")
    area = relationship("Area")


class BillPayment(Base):
    """
    Payments made against vendor bills
    Tracks payment history and methods
    """
    __tablename__ = "bill_payments"

    id = Column(Integer, primary_key=True, index=True)
    bill_id = Column(Integer, ForeignKey('vendor_bills.id', ondelete='CASCADE'), nullable=False, index=True)

    # Payment details
    payment_date = Column(Date, nullable=False, index=True)
    amount = Column(DECIMAL(15, 2), nullable=False)
    payment_method = Column(SQLEnum(PaymentMethod), nullable=False)

    # Payment reference
    reference_number = Column(String(100), nullable=True, index=True)  # Check number, confirmation, etc.

    # Bank account used (link to GL account)
    bank_account_id = Column(Integer, ForeignKey('accounts.id', ondelete='RESTRICT'), nullable=False)

    # Notes
    notes = Column(Text, nullable=True)

    # Accounting integration
    journal_entry_id = Column(Integer, ForeignKey('journal_entries.id', ondelete='SET NULL'), nullable=True)

    # Audit fields
    created_by = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    # Relationships
    bill = relationship("VendorBill", back_populates="payments")
    bank_account = relationship("Account", foreign_keys=[bank_account_id])
    creator = relationship("User", foreign_keys=[created_by])
    journal_entry = relationship("JournalEntry", foreign_keys=[journal_entry_id])
