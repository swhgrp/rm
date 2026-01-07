"""
Pydantic schemas for Daily Sales Summary
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, List, Any
from datetime import date, datetime
from decimal import Decimal


# ============================================================================
# Sales Line Item Schemas
# ============================================================================

class SalesLineItemBase(BaseModel):
    category: Optional[str] = None
    item_name: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    gross_amount: Decimal
    discount_amount: Decimal = Decimal("0.00")
    net_amount: Decimal
    tax_amount: Decimal = Decimal("0.00")
    revenue_account_id: Optional[int] = None


class SalesLineItemCreate(SalesLineItemBase):
    pass


class SalesLineItem(SalesLineItemBase):
    id: int
    dss_id: int

    class Config:
        from_attributes = True


# ============================================================================
# Sales Payment Schemas
# ============================================================================

class SalesPaymentBase(BaseModel):
    payment_type: str
    amount: Decimal
    tips: Decimal = Decimal("0.00")
    deposit_account_id: Optional[int] = None
    processor: Optional[str] = None
    reference_number: Optional[str] = None


class SalesPaymentCreate(SalesPaymentBase):
    pass


class SalesPayment(SalesPaymentBase):
    id: int
    dss_id: int

    class Config:
        from_attributes = True


# ============================================================================
# Daily Sales Summary Schemas
# ============================================================================

class DailySalesSummaryBase(BaseModel):
    business_date: date
    area_id: int
    pos_system: Optional[str] = None
    pos_location_id: Optional[str] = None
    gross_sales: Decimal = Decimal("0.00")
    discounts: Decimal = Decimal("0.00")
    refunds: Decimal = Decimal("0.00")
    net_sales: Decimal = Decimal("0.00")
    tax_collected: Decimal = Decimal("0.00")
    tips: Decimal = Decimal("0.00")
    total_collected: Decimal = Decimal("0.00")
    payment_breakdown: Optional[Dict[str, Any]] = None
    category_breakdown: Optional[Dict[str, Any]] = None
    discount_breakdown: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None
    imported_from: Optional[str] = None
    imported_from_pos: Optional[bool] = False
    pos_sync_date: Optional[datetime] = None
    pos_transaction_count: Optional[int] = None


class DailySalesSummaryCreate(DailySalesSummaryBase):
    line_items: Optional[List[SalesLineItemCreate]] = []
    payments: Optional[List[SalesPaymentCreate]] = []

    @field_validator('business_date')
    @classmethod
    def validate_business_date(cls, v):
        if v > date.today():
            raise ValueError("Business date cannot be in the future")
        return v


class DailySalesSummaryUpdate(BaseModel):
    gross_sales: Optional[Decimal] = None
    discounts: Optional[Decimal] = None
    refunds: Optional[Decimal] = None
    net_sales: Optional[Decimal] = None
    tax_collected: Optional[Decimal] = None
    tips: Optional[Decimal] = None
    total_collected: Optional[Decimal] = None
    payment_breakdown: Optional[Dict[str, Any]] = None
    category_breakdown: Optional[Dict[str, Any]] = None
    discount_breakdown: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None
    line_items: Optional[List[SalesLineItemCreate]] = None
    payments: Optional[List[SalesPaymentCreate]] = None


class DailySalesSummary(DailySalesSummaryBase):
    id: int
    status: str
    journal_entry_id: Optional[int] = None
    imported_at: Optional[datetime] = None
    created_by: int
    created_at: datetime
    verified_by: Optional[int] = None
    verified_at: Optional[datetime] = None
    posted_by: Optional[int] = None
    posted_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # Deposit and payout fields
    card_deposit: Optional[Decimal] = None
    cash_tips_paid: Optional[Decimal] = None
    cash_payouts: Optional[Decimal] = None
    payout_breakdown: Optional[List[Dict[str, Any]]] = None

    # Cash reconciliation fields
    expected_cash_deposit: Optional[Decimal] = None
    actual_cash_deposit: Optional[Decimal] = None
    cash_variance: Optional[Decimal] = None
    cash_reconciled_by: Optional[int] = None
    cash_reconciled_at: Optional[datetime] = None
    deposit_amount: Optional[Decimal] = None

    # Nested relationships
    line_items: List[SalesLineItem] = []
    payments: List[SalesPayment] = []

    class Config:
        from_attributes = True


class DailySalesSummaryList(BaseModel):
    """List view without nested items"""
    id: int
    business_date: date
    area_id: int
    pos_system: Optional[str] = None
    net_sales: Decimal
    tax_collected: Decimal
    tips: Decimal
    total_collected: Decimal
    status: str
    journal_entry_id: Optional[int] = None
    created_at: datetime

    # Cash reconciliation fields
    expected_cash_deposit: Optional[Decimal] = None
    actual_cash_deposit: Optional[Decimal] = None
    cash_variance: Optional[Decimal] = None
    cash_reconciled_by: Optional[int] = None
    cash_reconciled_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ============================================================================
# Action Schemas
# ============================================================================

class DSSVerifyRequest(BaseModel):
    notes: Optional[str] = None


class DSSPostRequest(BaseModel):
    notes: Optional[str] = None
    # Mapping of categories to revenue account IDs
    category_account_mapping: Optional[Dict[str, int]] = None
    # Mapping of payment types to asset account IDs (cash, bank, etc.)
    payment_account_mapping: Optional[Dict[str, int]] = None
    # Variance adjustment (for rounding differences)
    variance_account_id: Optional[int] = None
    variance_amount: Optional[Decimal] = None


# ============================================================================
# Import Schemas
# ============================================================================

class DSSImportRequest(BaseModel):
    """Request schema for importing sales data from external sources"""
    source_system: str  # 'CLOVER', 'SQUARE', 'MANUAL', etc.
    business_date: date
    area_id: int
    sales_data: Dict[str, Any]  # Flexible JSON structure from POS

    @field_validator('business_date')
    @classmethod
    def validate_business_date(cls, v):
        if v > date.today():
            raise ValueError("Business date cannot be in the future")
        return v


class DSSBulkImportRequest(BaseModel):
    """Request schema for bulk import of multiple days"""
    source_system: str
    area_id: int
    sales_data: List[Dict[str, Any]]  # List of daily sales


class DSSImportResponse(BaseModel):
    """Response after import"""
    success: bool
    message: str
    dss_id: Optional[int] = None
    business_date: Optional[date] = None
    net_sales: Optional[Decimal] = None
