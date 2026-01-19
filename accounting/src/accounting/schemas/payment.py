"""
Payment schemas for API validation
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import date, datetime
from decimal import Decimal
from enum import Enum


class PaymentMethodEnum(str, Enum):
    """Payment method types - values match database enum"""
    CHECK = "check"
    ACH = "ach"
    WIRE = "wire"
    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    CASH = "cash"
    OTHER = "other"


class PaymentStatusEnum(str, Enum):
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


# ============================================================================
# Payment Application Schemas
# ============================================================================

class PaymentApplicationBase(BaseModel):
    """Base schema for payment application"""
    vendor_bill_id: int
    amount_applied: Decimal
    discount_applied: Decimal = Decimal("0.00")


class PaymentApplicationCreate(PaymentApplicationBase):
    """Create payment application"""
    pass


class PaymentApplicationResponse(PaymentApplicationBase):
    """Payment application response"""
    id: int
    payment_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Payment Schemas
# ============================================================================

class PaymentBase(BaseModel):
    """Base payment schema"""
    payment_method: PaymentMethodEnum
    payment_date: date
    vendor_id: int
    area_id: Optional[int] = None
    bank_account_id: int
    amount: Decimal
    discount_amount: Decimal = Decimal("0.00")
    memo: Optional[str] = None
    notes: Optional[str] = None


class PaymentCreate(PaymentBase):
    """Create payment"""
    applications: List[PaymentApplicationCreate]
    scheduled_date: Optional[date] = None

    # Check-specific
    check_number: Optional[int] = None

    # ACH-specific
    reference_number: Optional[str] = None

    @validator('applications')
    def validate_applications(cls, v, values):
        """Ensure applications sum to payment amount"""
        if not v:
            raise ValueError("At least one bill application is required")

        total = sum(app.amount_applied for app in v)
        if 'amount' in values and 'discount_amount' in values:
            net_amount = values['amount'] - values['discount_amount']
            if abs(total - net_amount) > Decimal("0.01"):
                raise ValueError(f"Applications total ({total}) must equal net payment amount ({net_amount})")

        return v


class PaymentUpdate(BaseModel):
    """Update payment"""
    payment_date: Optional[date] = None
    status: Optional[PaymentStatusEnum] = None
    memo: Optional[str] = None
    notes: Optional[str] = None
    cleared_date: Optional[date] = None


class PaymentResponse(PaymentBase):
    """Payment response"""
    id: int
    payment_number: str
    net_amount: Decimal
    status: PaymentStatusEnum
    vendor_name: Optional[str] = None
    check_number: Optional[int] = None
    check_batch_id: Optional[int] = None
    ach_batch_id: Optional[int] = None
    ach_trace_number: Optional[str] = None
    reference_number: Optional[str] = None
    confirmation_number: Optional[str] = None
    scheduled_date: Optional[date] = None
    cleared_date: Optional[date] = None
    voided_date: Optional[date] = None
    journal_entry_id: Optional[int] = None
    void_reason: Optional[str] = None
    created_by: int
    approved_by: Optional[int] = None
    voided_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    applications: List[PaymentApplicationResponse] = []

    class Config:
        from_attributes = True


# ============================================================================
# Batch Payment Schemas
# ============================================================================

class BatchPaymentRequest(BaseModel):
    """Request to create batch payment"""
    payment_method: PaymentMethodEnum
    payment_date: date
    bank_account_id: int
    bill_ids: List[int]
    area_id: Optional[int] = None
    memo_template: Optional[str] = None

    # For check batches
    starting_check_number: Optional[int] = None

    # For ACH batches
    effective_date: Optional[date] = None


class BatchPaymentResponse(BaseModel):
    """Batch payment response"""
    batch_id: int
    batch_number: str
    payment_count: int
    total_amount: Decimal
    payment_ids: List[int]

    # Check batch specific
    check_batch_id: Optional[int] = None
    starting_check_number: Optional[int] = None
    ending_check_number: Optional[int] = None

    # ACH batch specific
    ach_batch_id: Optional[int] = None

    class Config:
        from_attributes = True


# ============================================================================
# Check Batch Schemas
# ============================================================================

class CheckBatchBase(BaseModel):
    """Base check batch schema"""
    batch_date: date
    bank_account_id: int
    starting_check_number: Optional[int] = None


class CheckBatchCreate(BaseModel):
    """Create check batch from existing payments"""
    batch_date: date
    bank_account_id: int
    payment_ids: List[int]


class CheckBatchResponse(CheckBatchBase):
    """Check batch response"""
    id: int
    batch_number: str
    ending_check_number: Optional[int] = None
    check_count: int
    total_amount: Decimal
    status: str
    printed_at: Optional[datetime] = None
    printed_by: Optional[int] = None
    pdf_file_path: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CheckPrintRequest(BaseModel):
    """Request to print checks"""
    check_batch_id: int
    print_alignment_test: bool = False


class CheckPrintResponse(BaseModel):
    """Check print response"""
    check_batch_id: int
    pdf_url: str
    check_count: int
    total_amount: Decimal
    checks: List[dict]  # List of check details


# ============================================================================
# ACH Batch Schemas
# ============================================================================

class ACHBatchBase(BaseModel):
    """Base ACH batch schema"""
    batch_date: date
    bank_account_id: int
    effective_date: date


class ACHBatchCreate(ACHBatchBase):
    """Create ACH batch"""
    payment_ids: List[int]


class ACHBatchResponse(ACHBatchBase):
    """ACH batch response"""
    id: int
    batch_number: str
    payment_count: int
    total_amount: Decimal
    status: str
    nacha_file_path: Optional[str] = None
    generated_at: Optional[datetime] = None
    generated_by: Optional[int] = None
    submitted_at: Optional[datetime] = None
    submitted_by: Optional[int] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ACHFileGenerateRequest(BaseModel):
    """Request to generate ACH file"""
    ach_batch_id: int
    company_name: str
    company_id: str  # Company EIN or tax ID
    company_discretionary_data: Optional[str] = None


class ACHFileGenerateResponse(BaseModel):
    """ACH file generation response"""
    ach_batch_id: int
    file_url: str
    file_path: str
    payment_count: int
    total_amount: Decimal


# ============================================================================
# Payment Void/Reissue Schemas
# ============================================================================

class PaymentVoidRequest(BaseModel):
    """Request to void payment"""
    void_reason: str
    void_date: date = Field(default_factory=date.today)


class PaymentReissueRequest(BaseModel):
    """Request to reissue voided payment"""
    new_check_number: Optional[int] = None
    new_payment_date: date = Field(default_factory=date.today)
    notes: Optional[str] = None


# ============================================================================
# Payment Schedule Schemas
# ============================================================================

class PaymentScheduleBase(BaseModel):
    """Base payment schedule schema"""
    schedule_name: str
    vendor_id: int
    payment_method: PaymentMethodEnum
    bank_account_id: int
    amount: Decimal
    frequency: str  # WEEKLY, BIWEEKLY, MONTHLY, QUARTERLY
    start_date: date
    end_date: Optional[date] = None
    auto_approve: bool = False
    memo_template: Optional[str] = None


class PaymentScheduleCreate(PaymentScheduleBase):
    """Create payment schedule"""
    pass


class PaymentScheduleUpdate(BaseModel):
    """Update payment schedule"""
    schedule_name: Optional[str] = None
    amount: Optional[Decimal] = None
    frequency: Optional[str] = None
    end_date: Optional[date] = None
    is_active: Optional[bool] = None
    auto_approve: Optional[bool] = None
    memo_template: Optional[str] = None


class PaymentScheduleResponse(PaymentScheduleBase):
    """Payment schedule response"""
    id: int
    next_payment_date: date
    is_active: bool
    created_by: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Payment Discount Schemas
# ============================================================================

class PaymentDiscountBase(BaseModel):
    """Base payment discount schema"""
    discount_terms: str
    discount_percent: Decimal
    discount_days: int
    discount_deadline: date
    max_discount_amount: Decimal


class PaymentDiscountCreate(PaymentDiscountBase):
    """Create payment discount"""
    vendor_bill_id: int


class PaymentDiscountResponse(PaymentDiscountBase):
    """Payment discount response"""
    id: int
    vendor_bill_id: int
    discount_taken: Decimal
    payment_id: Optional[int] = None
    taken_date: Optional[date] = None
    created_at: datetime

    class Config:
        from_attributes = True


class DiscountCalculationRequest(BaseModel):
    """Request to calculate available discount"""
    vendor_bill_id: int
    payment_date: date


class DiscountCalculationResponse(BaseModel):
    """Discount calculation response"""
    vendor_bill_id: int
    discount_available: bool
    discount_amount: Decimal
    discount_percent: Decimal
    discount_deadline: date
    days_remaining: int
    net_payment_amount: Decimal


# ============================================================================
# Payment Approval Schemas
# ============================================================================

class PaymentApprovalRequest(BaseModel):
    """Request payment approval"""
    payment_id: int
    notes: Optional[str] = None


class PaymentApprovalResponse(BaseModel):
    """Payment approval response"""
    id: int
    payment_id: int
    approver_id: int
    approval_status: str
    approved_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ApprovePaymentRequest(BaseModel):
    """Approve or reject payment"""
    approval_status: str  # APPROVED or REJECTED
    rejection_reason: Optional[str] = None
    notes: Optional[str] = None


# ============================================================================
# Payment Report Schemas
# ============================================================================

class PaymentHistoryFilter(BaseModel):
    """Filter for payment history"""
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    vendor_id: Optional[int] = None
    area_id: Optional[int] = None
    payment_method: Optional[PaymentMethodEnum] = None
    status: Optional[PaymentStatusEnum] = None
    min_amount: Optional[Decimal] = None
    max_amount: Optional[Decimal] = None


class PaymentSummary(BaseModel):
    """Payment summary for reporting"""
    total_payments: int
    total_amount: Decimal
    by_method: dict  # Payment method -> count & amount
    by_status: dict  # Payment status -> count & amount
    by_vendor: dict  # Vendor -> count & amount
    average_payment: Decimal
    largest_payment: Decimal
    smallest_payment: Decimal


class CashDisbursementEntry(BaseModel):
    """Cash disbursement journal entry"""
    payment_date: date
    payment_number: str
    vendor_name: str
    check_number: Optional[int] = None
    amount: Decimal
    account_debited: str
    memo: Optional[str] = None

    class Config:
        from_attributes = True


class OutstandingCheckReport(BaseModel):
    """Outstanding check report entry"""
    check_number: int
    payment_date: date
    vendor_name: str
    amount: Decimal
    days_outstanding: int
    status: str

    class Config:
        from_attributes = True
