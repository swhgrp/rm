"""
Pydantic schemas for Customer Invoices
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import date, datetime
from decimal import Decimal
from enum import Enum


class InvoiceStatus(str, Enum):
    DRAFT = "draft"
    SENT = "sent"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    OVERDUE = "overdue"
    VOID = "void"


class PaymentMethod(str, Enum):
    CASH = "cash"
    CHECK = "check"
    CREDIT_CARD = "credit_card"
    ACH = "ach"
    WIRE = "wire"
    OTHER = "other"


# Invoice Line Schemas
class CustomerInvoiceLineBase(BaseModel):
    account_id: Optional[int] = None
    description: Optional[str] = None
    quantity: Decimal = Field(default=Decimal("1"), ge=0)
    unit_price: Decimal = Field(ge=0)
    discount_percentage: Optional[Decimal] = Field(None, ge=0, le=100)
    is_taxable: bool = True


class CustomerInvoiceLineCreate(CustomerInvoiceLineBase):
    pass


class CustomerInvoiceLineRead(CustomerInvoiceLineBase):
    id: int
    invoice_id: int
    amount: Decimal
    discount_amount: Decimal
    tax_amount: Decimal

    class Config:
        from_attributes = True


# Payment Schemas
class InvoicePaymentBase(BaseModel):
    payment_date: date
    amount: Decimal = Field(gt=0)
    payment_method: PaymentMethod
    bank_account_id: int  # GL account where payment is deposited
    reference_number: Optional[str] = None
    notes: Optional[str] = None
    is_deposit: bool = False


class InvoicePaymentCreate(InvoicePaymentBase):
    pass


class InvoicePaymentRead(InvoicePaymentBase):
    id: int
    invoice_id: int
    created_by: int
    created_at: datetime

    class Config:
        from_attributes = True


# Invoice Schemas
class CustomerInvoiceBase(BaseModel):
    customer_id: int
    area_id: Optional[int] = None
    invoice_number: str
    invoice_date: date
    due_date: date

    # Event/Catering specific
    event_date: Optional[date] = None
    event_type: Optional[str] = None
    event_location: Optional[str] = None
    guest_count: Optional[int] = Field(None, ge=0)

    # Tax
    is_tax_exempt: bool = False
    tax_rate: Optional[Decimal] = Field(None, ge=0, le=100)

    # Deposits
    deposit_amount: Optional[Decimal] = Field(Decimal("0"), ge=0)

    notes: Optional[str] = None


class CustomerInvoiceCreate(CustomerInvoiceBase):
    lines: List[CustomerInvoiceLineCreate] = Field(min_length=1)

    @validator('due_date')
    def due_date_must_be_after_invoice_date(cls, v, values):
        if 'invoice_date' in values and v < values['invoice_date']:
            raise ValueError('Due date must be on or after invoice date')
        return v


class CustomerInvoiceUpdate(BaseModel):
    customer_id: Optional[int] = None
    area_id: Optional[int] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[date] = None
    due_date: Optional[date] = None
    event_date: Optional[date] = None
    event_type: Optional[str] = None
    event_location: Optional[str] = None
    guest_count: Optional[int] = Field(None, ge=0)
    is_tax_exempt: Optional[bool] = None
    tax_rate: Optional[Decimal] = Field(None, ge=0, le=100)
    deposit_amount: Optional[Decimal] = Field(None, ge=0)
    notes: Optional[str] = None
    lines: Optional[List[CustomerInvoiceLineCreate]] = None


class CustomerInvoiceRead(CustomerInvoiceBase):
    id: int
    status: InvoiceStatus
    customer_name: Optional[str] = None
    subtotal: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    paid_amount: Decimal
    balance_due: Decimal

    created_by: Optional[int] = None
    created_by_name: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    # Related data
    line_items: List[CustomerInvoiceLineRead] = []
    payments: List[InvoicePaymentRead] = []

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_with_creator(cls, invoice):
        """Create instance with creator name populated"""
        data = {
            'id': invoice.id,
            'customer_id': invoice.customer_id,
            'customer_name': invoice.customer.customer_name if invoice.customer else None,
            'area_id': invoice.area_id,
            'invoice_number': invoice.invoice_number,
            'invoice_date': invoice.invoice_date,
            'due_date': invoice.due_date,
            'event_date': invoice.event_date,
            'event_type': invoice.event_type,
            'event_location': invoice.event_location,
            'guest_count': invoice.guest_count,
            'is_tax_exempt': invoice.is_tax_exempt,
            'tax_rate': invoice.tax_rate,
            'deposit_amount': invoice.deposit_amount,
            'notes': invoice.notes,
            'status': invoice.status,
            'subtotal': invoice.subtotal,
            'discount_amount': invoice.discount_amount,
            'tax_amount': invoice.tax_amount,
            'total_amount': invoice.total_amount,
            'paid_amount': invoice.paid_amount,
            'balance_due': invoice.balance_due,
            'created_by': invoice.created_by,
            'created_by_name': invoice.creator.full_name if invoice.creator else None,
            'created_at': invoice.created_at,
            'updated_at': invoice.updated_at,
            'line_items': invoice.line_items,
            'payments': invoice.payments,
        }
        return cls(**data)


# ============================================================================
# AR Aging Report Schema
# ============================================================================

class ARAgingReportResponse(BaseModel):
    """AR Aging Report response"""
    as_of_date: date
    current: float = Field(description="Outstanding balance 0-30 days")
    days_31_60: float = Field(description="Outstanding balance 31-60 days")
    days_61_90: float = Field(description="Outstanding balance 61-90 days")
    over_90: float = Field(description="Outstanding balance over 90 days")
    total_outstanding: float = Field(description="Total outstanding balance")

    class Config:
        from_attributes = True
