"""
Recurring Invoice Model

Defines templates for invoices that are automatically generated on a schedule
"""
from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, Enum as SQLEnum, Text, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from decimal import Decimal
import enum
from accounting.db.database import Base


class RecurringFrequency(str, enum.Enum):
    """Frequency for recurring invoices"""
    WEEKLY = "WEEKLY"
    BIWEEKLY = "BIWEEKLY"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    ANNUALLY = "ANNUALLY"


class RecurringInvoiceStatus(str, enum.Enum):
    """Status of recurring invoice template"""
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class RecurringInvoice(Base):
    """
    Template for recurring invoices

    Automatically generates invoices based on a schedule
    """
    __tablename__ = "recurring_invoices"

    id = Column(Integer, primary_key=True, index=True)

    # Customer
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)

    # Template details
    template_name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    # Schedule
    frequency = Column(SQLEnum(RecurringFrequency), nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=True)  # Null = continues indefinitely
    next_invoice_date = Column(DateTime, nullable=False)

    # Invoice details
    terms_days = Column(Integer, nullable=False, default=30)
    invoice_description = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)

    # Amounts
    subtotal = Column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    discount_percent = Column(Numeric(5, 2), nullable=False, default=Decimal("0.00"))
    discount_amount = Column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    tax_rate = Column(Numeric(5, 2), nullable=False, default=Decimal("0.00"))
    tax_amount = Column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    total_amount = Column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))

    # Email settings
    auto_send_email = Column(Boolean, default=True)
    email_to = Column(String(255), nullable=True)  # Override customer email if needed
    email_cc = Column(Text, nullable=True)  # Comma-separated CC emails

    # Status
    status = Column(SQLEnum(RecurringInvoiceStatus), nullable=False, default=RecurringInvoiceStatus.ACTIVE)

    # Statistics
    invoices_generated = Column(Integer, default=0)
    last_generated_at = Column(DateTime, nullable=True)

    # Audit
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    customer = relationship("Customer", back_populates="recurring_invoices")
    line_items = relationship("RecurringInvoiceLineItem", back_populates="recurring_invoice", cascade="all, delete-orphan")
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])

    def __repr__(self):
        return f"<RecurringInvoice {self.id}: {self.template_name} - {self.customer.name if self.customer else 'N/A'}>"


class RecurringInvoiceLineItem(Base):
    """Line items for recurring invoice templates"""
    __tablename__ = "recurring_invoice_line_items"

    id = Column(Integer, primary_key=True, index=True)
    recurring_invoice_id = Column(Integer, ForeignKey("recurring_invoices.id", ondelete="CASCADE"), nullable=False)

    # Line item details
    line_number = Column(Integer, nullable=False, default=1)
    description = Column(Text, nullable=False)
    quantity = Column(Numeric(10, 2), nullable=False, default=Decimal("1.00"))
    unit_price = Column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    amount = Column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))

    # Optional GL account for direct posting
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    recurring_invoice = relationship("RecurringInvoice", back_populates="line_items")
    account = relationship("Account")

    def __repr__(self):
        return f"<RecurringInvoiceLineItem {self.id}: {self.description[:30]}>"
