"""
Pydantic schemas for General Accounting Dashboard
"""
from pydantic import BaseModel, Field
from decimal import Decimal
from datetime import date, datetime
from typing import List, Optional


# ============================================================================
# Executive Summary Schemas
# ============================================================================

class ExecutiveSummaryMetrics(BaseModel):
    """Top-level financial metrics for executive dashboard"""
    # Current period
    net_income_mtd: Decimal = Field(description="Net income month-to-date")
    net_income_ytd: Decimal = Field(description="Net income year-to-date")
    total_revenue_mtd: Decimal = Field(description="Total revenue month-to-date")
    total_revenue_ytd: Decimal = Field(description="Total revenue year-to-date")

    # Margins
    gross_profit_margin: Decimal = Field(description="Gross profit margin percentage")
    operating_margin: Decimal = Field(description="Operating margin percentage")
    prime_cost_percentage: Decimal = Field(description="Prime cost percentage (COGS + Labor)")

    # Comparisons
    revenue_vs_prior_month: Decimal = Field(description="Revenue change vs prior month (%)")
    net_income_vs_prior_month: Decimal = Field(description="Net income change vs prior month (%)")

    class Config:
        from_attributes = True


class TopExpenseCategory(BaseModel):
    """Top expense category item"""
    category_name: str
    amount: Decimal
    pct_of_revenue: Decimal
    pct_change_mom: Optional[Decimal] = None
    rank: int

    class Config:
        from_attributes = True


class LocationRevenue(BaseModel):
    """Revenue by location"""
    area_id: int
    area_name: str
    revenue: Decimal
    pct_of_total: Decimal
    vs_prior_month: Optional[Decimal] = None

    class Config:
        from_attributes = True


class ExecutiveSummaryResponse(BaseModel):
    """Complete executive summary"""
    metrics: ExecutiveSummaryMetrics
    top_expenses: List[TopExpenseCategory]
    revenue_by_location: List[LocationRevenue]
    as_of_date: date

    class Config:
        from_attributes = True


# ============================================================================
# Real-Time Tracking Schemas
# ============================================================================

class DailySalesMetrics(BaseModel):
    """Daily sales summary metrics"""
    today_sales: Decimal
    mtd_sales: Decimal
    mtd_avg_daily: Decimal
    vs_prior_day: Decimal
    vs_prior_month_same_day: Optional[Decimal] = None
    transaction_count: int
    average_check: Decimal

    class Config:
        from_attributes = True


class COGSMetrics(BaseModel):
    """COGS tracking metrics"""
    current_cogs_pct: Decimal
    target_cogs_pct: Decimal = Field(default=Decimal("32.0"))
    variance_from_target: Decimal
    mtd_cogs_pct: Decimal
    food_cogs_pct: Decimal
    beverage_cogs_pct: Decimal

    class Config:
        from_attributes = True


class BankBalanceSummary(BaseModel):
    """Current bank balance summary"""
    total_cash: Decimal
    bank_account_count: int
    last_reconciled: Optional[date] = None
    unreconciled_count: int
    oldest_unreconciled_days: Optional[int] = None

    class Config:
        from_attributes = True


class CashFlowForecast(BaseModel):
    """Cash flow forecast"""
    current_cash: Decimal
    open_ap: Decimal
    open_ar: Decimal
    projected_cash: Decimal
    days_of_cash: Optional[int] = Field(None, description="Days of operating expenses covered")

    class Config:
        from_attributes = True


class APAgingSummary(BaseModel):
    """AP aging summary"""
    total_outstanding: Decimal
    bucket_0_30: Decimal
    bucket_31_60: Decimal
    bucket_61_90: Decimal
    bucket_over_90: Decimal
    average_age_days: Decimal
    vendor_count: int

    class Config:
        from_attributes = True


class AccountingHealthMetrics(BaseModel):
    """Accounting control health metrics"""
    unposted_journals: int
    pending_reconciliations: int
    missing_dss_mappings: int
    gl_outliers: int
    last_inventory_date: Optional[date] = None
    days_since_inventory: Optional[int] = None

    class Config:
        from_attributes = True


class RealTimeTrackingResponse(BaseModel):
    """Real-time financial tracking metrics"""
    daily_sales: DailySalesMetrics
    cogs: COGSMetrics
    bank_balance: BankBalanceSummary
    cash_flow_forecast: CashFlowForecast
    ap_aging: APAgingSummary
    accounting_health: AccountingHealthMetrics
    as_of_datetime: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Historical Analysis Schemas
# ============================================================================

class MonthlyPerformancePoint(BaseModel):
    """Single month's performance data"""
    period_month: date
    revenue: Decimal
    cogs_pct: Decimal
    labor_pct: Optional[Decimal] = None
    net_income: Decimal
    net_income_margin: Decimal

    class Config:
        from_attributes = True


class HistoricalTrendResponse(BaseModel):
    """6-month historical trends"""
    months: List[MonthlyPerformancePoint]
    revenue_trend: str = Field(description="up, down, or flat")
    cogs_trend: str
    net_income_trend: str

    class Config:
        from_attributes = True


class BudgetVarianceItem(BaseModel):
    """Budget variance for a category"""
    category: str
    actual: Decimal
    budget: Decimal
    variance: Decimal
    variance_pct: Decimal

    class Config:
        from_attributes = True


class BudgetVarianceResponse(BaseModel):
    """Budget variance analysis"""
    period_month: date
    variances: List[BudgetVarianceItem]
    total_variance: Decimal
    total_variance_pct: Decimal

    class Config:
        from_attributes = True


# ============================================================================
# Multi-Location Schemas
# ============================================================================

class LocationPerformanceFlag(BaseModel):
    """Performance flag for a location"""
    flag_type: str = Field(description="sales_drop, cogs_high, ap_aging_high")
    severity: str = Field(description="critical, warning, info")
    message: str
    metric_value: Decimal
    threshold_value: Decimal

    class Config:
        from_attributes = True


class LocationPerformanceMetrics(BaseModel):
    """Performance metrics for a single location"""
    area_id: int
    area_name: str
    revenue: Decimal
    gross_profit_pct: Decimal
    net_income: Decimal
    net_income_margin: Decimal
    cogs_pct: Decimal
    labor_pct: Optional[Decimal] = None
    prime_cost_pct: Decimal
    rank_by_revenue: int
    rank_by_profit: int
    flags: List[LocationPerformanceFlag]

    class Config:
        from_attributes = True


class MultiLocationResponse(BaseModel):
    """Multi-location comparison"""
    consolidated: LocationPerformanceMetrics
    locations: List[LocationPerformanceMetrics]
    period_start: date
    period_end: date

    class Config:
        from_attributes = True


# ============================================================================
# Alert Schemas
# ============================================================================

class DashboardAlertResponse(BaseModel):
    """Dashboard alert"""
    id: int
    alert_type: str
    severity: str
    title: str
    message: str
    metric_value: Optional[Decimal] = None
    threshold_value: Optional[Decimal] = None
    action_url: Optional[str] = None
    area_id: Optional[int] = None
    area_name: Optional[str] = None
    is_active: bool
    is_acknowledged: bool
    acknowledged_by: Optional[int] = None
    acknowledged_at: Optional[datetime] = None
    is_resolved: bool
    created_at: datetime

    class Config:
        from_attributes = True


class AlertAcknowledgeRequest(BaseModel):
    """Request to acknowledge an alert"""
    user_id: int


class AlertResolveRequest(BaseModel):
    """Request to resolve an alert"""
    user_id: int
    resolution_notes: Optional[str] = None


class AlertSummaryResponse(BaseModel):
    """Summary of alerts by severity"""
    critical_count: int
    warning_count: int
    info_count: int
    total_active: int
    alerts: List[DashboardAlertResponse]

    class Config:
        from_attributes = True


# ============================================================================
# Dashboard Summary (All-in-One)
# ============================================================================

class DashboardSummaryResponse(BaseModel):
    """Complete dashboard summary - all widgets"""
    executive_summary: ExecutiveSummaryResponse
    real_time_tracking: RealTimeTrackingResponse
    alerts: AlertSummaryResponse
    as_of_datetime: datetime
    selected_area_id: Optional[int] = None
    selected_area_name: Optional[str] = None

    class Config:
        from_attributes = True


# ============================================================================
# Month-End Close Schemas
# ============================================================================

class MonthEndChecklistItem(BaseModel):
    """Single checklist item for month-end close"""
    item_name: str
    is_complete: bool
    completed_by: Optional[int] = None
    completed_at: Optional[datetime] = None
    required: bool = True

    class Config:
        from_attributes = True


class MonthEndCloseStatus(BaseModel):
    """Month-end close progress"""
    period_month: date
    is_closed: bool
    closed_by: Optional[int] = None
    closed_at: Optional[datetime] = None
    checklist: List[MonthEndChecklistItem]
    completion_pct: Decimal
    can_close: bool

    class Config:
        from_attributes = True
