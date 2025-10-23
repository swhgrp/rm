"""
Payment models for AP payment processing
"""
from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime, Text, Boolean, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from accounting.db.database import Base
from accounting.models.vendor_bill import PaymentMethod  # Use existing enum
import enum


class PaymentStatus(str, enum.Enum):
    """Payment status types"""
    DRAFT = "DRAFT"
    SCHEDULED = "SCHEDULED"
    PENDING = "PENDING"
    PRINTED = "PRINTED"
    SUBMITTED = "SUBMITTED"
    CLEARED = "CLEARED"
    VOIDED = "VOIDED"
    CANCELLED = "CANCELLED"
    STOPPED = "STOPPED"
    RETURNED = "RETURNED"


class CheckBatch(Base):
    """Batch of checks printed together"""
    __tablename__ = "check_batches"

    id = Column(Integer, primary_key=True)
    batch_number = Column(String(50), unique=True, nullable=False)
    batch_date = Column(Date, nullable=False)
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id"), nullable=False)
    starting_check_number = Column(Integer, nullable=False)
    ending_check_number = Column(Integer)
    check_count = Column(Integer, default=0, nullable=False)
    total_amount = Column(Numeric(15, 2), default=0, nullable=False)
    status = Column(String(20), default="DRAFT", nullable=False)
    printed_at = Column(DateTime)
    printed_by = Column(Integer, ForeignKey("users.id"))
    pdf_file_path = Column(String(500))
    notes = Column(Text)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    bank_account = relationship("BankAccount", back_populates="check_batches")
    checks = relationship("Payment", back_populates="check_batch", foreign_keys="Payment.check_batch_id")


class ACHBatch(Base):
    """Batch of ACH payments"""
    __tablename__ = "ach_batches"

    id = Column(Integer, primary_key=True)
    batch_number = Column(String(50), unique=True, nullable=False)
    batch_date = Column(Date, nullable=False)
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id"), nullable=False)
    effective_date = Column(Date, nullable=False)
    payment_count = Column(Integer, default=0, nullable=False)
    total_amount = Column(Numeric(15, 2), default=0, nullable=False)
    status = Column(String(20), default="DRAFT", nullable=False)
    nacha_file_path = Column(String(500))
    generated_at = Column(DateTime)
    generated_by = Column(Integer, ForeignKey("users.id"))
    submitted_at = Column(DateTime)
    submitted_by = Column(Integer, ForeignKey("users.id"))
    notes = Column(Text)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    bank_account = relationship("BankAccount", back_populates="ach_batches")
    payments = relationship("Payment", back_populates="ach_batch", foreign_keys="Payment.ach_batch_id")


class Payment(Base):
    """Payment record"""
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True)
    payment_number = Column(String(50), unique=True, nullable=False)
    payment_method = Column(SQLEnum(PaymentMethod), nullable=False)
    payment_date = Column(Date, nullable=False)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=False)
    area_id = Column(Integer, ForeignKey("areas.id"))
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id"), nullable=False)
    amount = Column(Numeric(15, 2), nullable=False)
    discount_amount = Column(Numeric(15, 2), default=0, nullable=False)
    net_amount = Column(Numeric(15, 2), nullable=False)
    status = Column(SQLEnum(PaymentStatus), default=PaymentStatus.DRAFT, nullable=False)

    # Check-specific fields
    check_number = Column(Integer)
    check_batch_id = Column(Integer, ForeignKey("check_batches.id"))

    # ACH-specific fields
    ach_batch_id = Column(Integer, ForeignKey("ach_batches.id"))
    ach_trace_number = Column(String(50))

    # Wire/Other fields
    reference_number = Column(String(100))
    confirmation_number = Column(String(100))

    # Dates
    scheduled_date = Column(Date)
    cleared_date = Column(Date)
    voided_date = Column(Date)

    # GL integration
    journal_entry_id = Column(Integer, ForeignKey("journal_entries.id"))

    # Metadata
    memo = Column(Text)
    notes = Column(Text)
    void_reason = Column(Text)

    # Audit
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    approved_by = Column(Integer, ForeignKey("users.id"))
    voided_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    vendor = relationship("Vendor", back_populates="payments")
    area = relationship("Area")
    bank_account = relationship("BankAccount", back_populates="payments")
    check_batch = relationship("CheckBatch", back_populates="checks", foreign_keys=[check_batch_id])
    ach_batch = relationship("ACHBatch", back_populates="payments", foreign_keys=[ach_batch_id])
    journal_entry = relationship("JournalEntry")
    applications = relationship("PaymentApplication", back_populates="payment", cascade="all, delete-orphan")
    approvals = relationship("PaymentApproval", back_populates="payment", cascade="all, delete-orphan")


class PaymentApplication(Base):
    """Link between payment and vendor bill"""
    __tablename__ = "payment_applications"

    id = Column(Integer, primary_key=True)
    payment_id = Column(Integer, ForeignKey("payments.id", ondelete="CASCADE"), nullable=False)
    vendor_bill_id = Column(Integer, ForeignKey("vendor_bills.id"), nullable=False)
    amount_applied = Column(Numeric(15, 2), nullable=False)
    discount_applied = Column(Numeric(15, 2), default=0, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    # Relationships
    payment = relationship("Payment", back_populates="applications")
    vendor_bill = relationship("VendorBill", back_populates="payment_applications")


class CheckNumberRegistry(Base):
    """Track all check numbers for each bank account"""
    __tablename__ = "check_number_registry"

    id = Column(Integer, primary_key=True)
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id"), nullable=False)
    check_number = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False)  # USED, VOIDED, CANCELLED, SKIPPED
    payment_id = Column(Integer, ForeignKey("payments.id"))
    used_date = Column(Date)
    notes = Column(Text)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    # Relationships
    bank_account = relationship("BankAccount")
    payment = relationship("Payment")


class PaymentSchedule(Base):
    """Recurring payment schedules"""
    __tablename__ = "payment_schedules"

    id = Column(Integer, primary_key=True)
    schedule_name = Column(String(200), nullable=False)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=False)
    payment_method = Column(SQLEnum(PaymentMethod), nullable=False)
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id"), nullable=False)
    amount = Column(Numeric(15, 2), nullable=False)
    frequency = Column(String(20), nullable=False)  # WEEKLY, BIWEEKLY, MONTHLY, QUARTERLY
    start_date = Column(Date, nullable=False)
    end_date = Column(Date)
    next_payment_date = Column(Date, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    auto_approve = Column(Boolean, default=False, nullable=False)
    memo_template = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    vendor = relationship("Vendor")
    bank_account = relationship("BankAccount")


class PaymentApproval(Base):
    """Payment approval workflow"""
    __tablename__ = "payment_approvals"

    id = Column(Integer, primary_key=True)
    payment_id = Column(Integer, ForeignKey("payments.id", ondelete="CASCADE"), nullable=False)
    approver_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    approval_status = Column(String(20), nullable=False)  # PENDING, APPROVED, REJECTED
    approved_at = Column(DateTime)
    rejection_reason = Column(Text)
    notes = Column(Text)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    # Relationships
    payment = relationship("Payment", back_populates="approvals")
    approver = relationship("User")


class PaymentDiscount(Base):
    """Early payment discount tracking"""
    __tablename__ = "payment_discounts"

    id = Column(Integer, primary_key=True)
    vendor_bill_id = Column(Integer, ForeignKey("vendor_bills.id"), nullable=False)
    discount_terms = Column(String(50), nullable=False)  # e.g., "2/10 Net 30"
    discount_percent = Column(Numeric(5, 2), nullable=False)
    discount_days = Column(Integer, nullable=False)
    discount_deadline = Column(Date, nullable=False)
    max_discount_amount = Column(Numeric(15, 2), nullable=False)
    discount_taken = Column(Numeric(15, 2), default=0, nullable=False)
    payment_id = Column(Integer, ForeignKey("payments.id"))
    taken_date = Column(Date)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    # Relationships
    vendor_bill = relationship("VendorBill", back_populates="payment_discounts")
    payment = relationship("Payment")
