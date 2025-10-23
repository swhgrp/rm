"""Budget schemas for API validation"""
from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import date, datetime
from decimal import Decimal


# Budget Line Schemas
class BudgetLineBase(BaseModel):
    """Base budget line schema"""
    account_id: int
    amount: Decimal = Field(..., ge=0)
    notes: Optional[str] = None


class BudgetLineCreate(BudgetLineBase):
    """Create budget line"""
    budget_period_id: Optional[int] = None


class BudgetLineResponse(BudgetLineBase):
    """Budget line response"""
    id: int
    budget_id: int
    budget_period_id: Optional[int]
    account_number: Optional[str] = None
    account_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Budget Period Schemas
class BudgetPeriodBase(BaseModel):
    """Base budget period schema"""
    period_type: str  # ANNUAL, QUARTERLY, MONTHLY
    period_number: int
    period_name: str
    start_date: date
    end_date: date


class BudgetPeriodCreate(BudgetPeriodBase):
    """Create budget period"""
    pass


class BudgetPeriodResponse(BudgetPeriodBase):
    """Budget period response"""
    id: int
    budget_id: int
    is_locked: bool
    lines: List[BudgetLineResponse] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Budget Schemas
class BudgetBase(BaseModel):
    """Base budget schema"""
    budget_name: str = Field(..., min_length=1, max_length=200)
    fiscal_year: int = Field(..., ge=2020, le=2100)
    start_date: date
    end_date: date
    budget_type: str = Field(default="OPERATING")  # OPERATING, CAPITAL, CASH_FLOW
    area_id: Optional[int] = None
    department: Optional[str] = None
    description: Optional[str] = None
    notes: Optional[str] = None

    @validator('end_date')
    def end_after_start(cls, v, values):
        if 'start_date' in values and v <= values['start_date']:
            raise ValueError('end_date must be after start_date')
        return v


class BudgetCreate(BudgetBase):
    """Create budget"""
    copy_from_budget_id: Optional[int] = None
    growth_rate: Optional[Decimal] = Field(None, ge=-100, le=1000)  # -100% to 1000%
    create_periods: bool = True  # Auto-create monthly periods


class BudgetUpdate(BaseModel):
    """Update budget"""
    budget_name: Optional[str] = None
    description: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None


class BudgetResponse(BudgetBase):
    """Budget response"""
    id: int
    status: str
    total_revenue: Decimal
    total_expenses: Decimal
    net_income: Decimal
    created_by: int
    approved_by: Optional[int]
    approved_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    # Related data
    area_name: Optional[str] = None
    creator_name: Optional[str] = None
    approver_name: Optional[str] = None
    periods: List[BudgetPeriodResponse] = []

    class Config:
        from_attributes = True


class BudgetSummary(BaseModel):
    """Budget summary for list view"""
    id: int
    budget_name: str
    fiscal_year: int
    budget_type: str
    status: str
    area_name: Optional[str]
    department: Optional[str]
    total_revenue: Decimal
    total_expenses: Decimal
    net_income: Decimal
    start_date: date
    end_date: date
    created_at: datetime

    class Config:
        from_attributes = True


# Budget vs Actual Schemas
class BudgetVsActualLine(BaseModel):
    """Budget vs actual comparison line"""
    account_id: int
    account_number: str
    account_name: str
    account_type: str
    budget_amount: Decimal
    actual_amount: Decimal
    variance: Decimal
    variance_percent: Decimal
    is_favorable: bool


class BudgetVsActualReport(BaseModel):
    """Budget vs actual report"""
    budget_id: int
    budget_name: str
    fiscal_year: int
    period_name: Optional[str] = None
    start_date: date
    end_date: date

    # Summary totals
    total_revenue_budget: Decimal
    total_revenue_actual: Decimal
    total_revenue_variance: Decimal
    total_revenue_variance_percent: Decimal

    total_expenses_budget: Decimal
    total_expenses_actual: Decimal
    total_expenses_variance: Decimal
    total_expenses_variance_percent: Decimal

    net_income_budget: Decimal
    net_income_actual: Decimal
    net_income_variance: Decimal
    net_income_variance_percent: Decimal

    # Detail lines
    revenue_lines: List[BudgetVsActualLine]
    expense_lines: List[BudgetVsActualLine]


# Bulk Budget Line Update
class BulkBudgetLineUpdate(BaseModel):
    """Bulk update budget lines"""
    lines: List[BudgetLineCreate]


class BudgetApprovalRequest(BaseModel):
    """Approve or reject budget"""
    action: str = Field(..., pattern="^(approve|reject)$")
    notes: Optional[str] = None
