"""
Pydantic schemas for Vendor Bills (Accounts Payable)
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import date, datetime
from decimal import Decimal
from accounting.models.vendor_bill import BillStatus, PaymentMethod


# ========== Helper Schemas ==========

class AreaInBill(BaseModel):
    """Simplified area info for bill responses"""
    id: int
    code: str
    name: str

    class Config:
        from_attributes = True


class AccountInBill(BaseModel):
    """Simplified account info for bill line responses"""
    id: int
    account_number: str
    account_name: str

    class Config:
        from_attributes = True


class UserInBill(BaseModel):
    """Simplified user info for bill responses"""
    id: int
    username: str
    full_name: Optional[str] = None

    class Config:
        from_attributes = True


# ========== Vendor Bill Line Schemas ==========

class VendorBillLineCreate(BaseModel):
    """Schema for creating a bill line item"""
    account_id: int = Field(..., gt=0, description="GL account ID for this expense")
    area_id: Optional[int] = Field(None, gt=0, description="Location/area for this line (optional)")
    description: Optional[str] = Field(None, max_length=500)
    quantity: Optional[Decimal] = Field(None, ge=0)
    unit_price: Optional[Decimal] = Field(None, ge=0)
    amount: Decimal = Field(..., gt=0, description="Line total amount")
    is_taxable: bool = Field(True, description="Whether this line is subject to tax")
    tax_amount: Decimal = Field(Decimal('0.00'), ge=0)
    line_number: Optional[int] = Field(None, ge=1)

    @field_validator('amount')
    @classmethod
    def amount_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError('Amount must be greater than zero')
        return v


class VendorBillLineUpdate(BaseModel):
    """Schema for updating a bill line item"""
    account_id: Optional[int] = Field(None, gt=0)
    area_id: Optional[int] = Field(None, gt=0)
    description: Optional[str] = Field(None, max_length=500)
    quantity: Optional[Decimal] = Field(None, ge=0)
    unit_price: Optional[Decimal] = Field(None, ge=0)
    amount: Optional[Decimal] = Field(None, gt=0)
    is_taxable: Optional[bool] = None
    tax_amount: Optional[Decimal] = Field(None, ge=0)
    line_number: Optional[int] = Field(None, ge=1)


class VendorBillLineResponse(BaseModel):
    """Schema for bill line item responses"""
    id: int
    bill_id: int
    account_id: int
    account: Optional[AccountInBill] = None
    area_id: Optional[int] = None
    area: Optional[AreaInBill] = None
    description: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    amount: Decimal
    is_taxable: bool
    tax_amount: Decimal
    line_number: Optional[int] = None

    class Config:
        from_attributes = True


# ========== Vendor Bill Schemas ==========

class VendorBillCreate(BaseModel):
    """Schema for creating a new vendor bill"""
    vendor_name: str = Field(..., min_length=1, max_length=200)
    vendor_id: Optional[str] = Field(None, max_length=50, description="External vendor ID from inventory system")
    bill_number: str = Field(..., min_length=1, max_length=100, description="Vendor's invoice/bill number")
    bill_date: date = Field(..., description="Date on vendor invoice")
    due_date: date = Field(..., description="Payment due date")
    received_date: Optional[date] = Field(None, description="When bill was received")
    area_id: Optional[int] = Field(None, gt=0, description="Primary location for this bill")
    subtotal: Decimal = Field(Decimal('0.00'), ge=0)
    tax_amount: Decimal = Field(Decimal('0.00'), ge=0)
    total_amount: Decimal = Field(..., gt=0)
    is_1099_eligible: bool = Field(False, description="Track for 1099 reporting")
    reference_number: Optional[str] = Field(None, max_length=100, description="PO number, etc.")
    description: Optional[str] = Field(None, max_length=1000)
    notes: Optional[str] = Field(None, max_length=2000)
    line_items: List[VendorBillLineCreate] = Field(default_factory=list, description="Bill line items")

    @field_validator('due_date')
    @classmethod
    def due_date_must_be_after_or_equal_bill_date(cls, v, info):
        if 'bill_date' in info.data and v < info.data['bill_date']:
            raise ValueError('Due date must be on or after bill date')
        return v

    @field_validator('total_amount')
    @classmethod
    def total_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError('Total amount must be greater than zero')
        return v


class VendorBillUpdate(BaseModel):
    """Schema for updating a vendor bill"""
    vendor_name: Optional[str] = Field(None, min_length=1, max_length=200)
    vendor_id: Optional[str] = Field(None, max_length=50)
    bill_number: Optional[str] = Field(None, min_length=1, max_length=100)
    bill_date: Optional[date] = None
    due_date: Optional[date] = None
    received_date: Optional[date] = None
    area_id: Optional[int] = Field(None, gt=0)
    subtotal: Optional[Decimal] = Field(None, ge=0)
    tax_amount: Optional[Decimal] = Field(None, ge=0)
    total_amount: Optional[Decimal] = Field(None, gt=0)
    is_1099_eligible: Optional[bool] = None
    reference_number: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=1000)
    notes: Optional[str] = Field(None, max_length=2000)
    status: Optional[BillStatus] = None


class VendorBillResponse(BaseModel):
    """Schema for vendor bill responses"""
    id: int
    vendor_name: str
    vendor_id: Optional[str] = None
    bill_number: str
    bill_date: date
    due_date: date
    received_date: Optional[date] = None
    subtotal: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    paid_amount: Decimal
    balance_due: Decimal  # Computed property
    area_id: Optional[int] = None
    area: Optional[AreaInBill] = None
    status: BillStatus
    approved_by: Optional[int] = None
    approver: Optional[UserInBill] = None
    approved_date: Optional[datetime] = None
    approval_notes: Optional[str] = None
    is_1099_eligible: bool
    reference_number: Optional[str] = None
    description: Optional[str] = None
    notes: Optional[str] = None
    journal_entry_id: Optional[int] = None
    created_by: Optional[int] = None
    creator: Optional[UserInBill] = None
    created_at: datetime
    updated_at: datetime
    line_items: List[VendorBillLineResponse] = []
    is_overdue: bool  # Computed property
    days_until_due: int  # Computed property

    class Config:
        from_attributes = True


class VendorBillListResponse(BaseModel):
    """Simplified schema for bill lists (without line items)"""
    id: int
    vendor_name: str
    bill_number: str
    bill_date: date
    due_date: date
    total_amount: Decimal
    paid_amount: Decimal
    balance_due: Decimal
    area_id: Optional[int] = None
    area: Optional[AreaInBill] = None
    status: BillStatus
    is_overdue: bool
    days_until_due: int
    created_at: datetime

    class Config:
        from_attributes = True


# ========== Bill Approval Schemas ==========

class BillApprovalRequest(BaseModel):
    """Schema for approving/rejecting a bill"""
    approve: bool = Field(..., description="True to approve, False to reject")
    notes: Optional[str] = Field(None, max_length=1000, description="Approval/rejection notes")


# ========== Bill Payment Schemas ==========

class BillPaymentCreate(BaseModel):
    """Schema for creating a bill payment"""
    bill_id: int = Field(..., gt=0)
    payment_date: date = Field(..., description="Date payment was made")
    amount: Decimal = Field(..., gt=0, description="Payment amount")
    payment_method: PaymentMethod = Field(..., description="How payment was made")
    reference_number: Optional[str] = Field(None, max_length=100, description="Check number, confirmation, etc.")
    bank_account_id: int = Field(..., gt=0, description="Bank account (GL account) used for payment")
    notes: Optional[str] = Field(None, max_length=1000)

    @field_validator('amount')
    @classmethod
    def amount_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError('Payment amount must be greater than zero')
        return v


class BillPaymentResponse(BaseModel):
    """Schema for bill payment responses"""
    id: int
    bill_id: int
    payment_date: date
    amount: Decimal
    payment_method: PaymentMethod
    reference_number: Optional[str] = None
    bank_account_id: int
    bank_account: Optional[AccountInBill] = None
    notes: Optional[str] = None
    journal_entry_id: Optional[int] = None
    created_by: Optional[int] = None
    creator: Optional[UserInBill] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ========== AP Aging Report Schemas ==========

class AgingBucket(BaseModel):
    """Aging bucket for AP aging report"""
    current: Decimal = Field(Decimal('0.00'), description="0-30 days")
    days_31_60: Decimal = Field(Decimal('0.00'), description="31-60 days")
    days_61_90: Decimal = Field(Decimal('0.00'), description="61-90 days")
    over_90_days: Decimal = Field(Decimal('0.00'), description="Over 90 days")
    total: Decimal = Field(Decimal('0.00'), description="Total outstanding")


class VendorAgingDetail(BaseModel):
    """Vendor detail in aging report"""
    vendor_name: str
    vendor_id: Optional[str] = None
    current: Decimal = Decimal('0.00')
    days_31_60: Decimal = Decimal('0.00')
    days_61_90: Decimal = Decimal('0.00')
    over_90_days: Decimal = Decimal('0.00')
    total: Decimal = Decimal('0.00')


class APAgingReportResponse(BaseModel):
    """AP Aging Report response"""
    as_of_date: date
    area_id: Optional[int] = None
    area_name: Optional[str] = None
    vendors: List[VendorAgingDetail] = []
    totals: AgingBucket

    class Config:
        from_attributes = True
