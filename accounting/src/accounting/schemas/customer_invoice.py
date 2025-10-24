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
    invoice_number: Optional[str] = None
    invoice_date: Optional[date] = None
    due_date: Optional[date] = None
    event_date: Optional[date] = None
    event_type: Optional[str] = None
    event_location: Optional[str] = None
    guest_count: Optional[int] = Field(None, ge=0)
    deposit_amount: Optional[Decimal] = Field(None, ge=0)
    notes: Optional[str] = None


class CustomerInvoiceRead(CustomerInvoiceBase):
    id: int
    status: InvoiceStatus
    subtotal: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    paid_amount: Decimal
    balance_due: Decimal

    created_by: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    # Related data
    line_items: List[CustomerInvoiceLineRead] = []
    payments: List[InvoicePaymentRead] = []

    class Config:
        from_attributes = True


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
