"""Schemas for Banking Dashboard API endpoints"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from decimal import Decimal
from datetime import date, datetime
from accounting.models.banking_dashboard import CashFlowCategory, AlertSeverity, AlertType


# ============================================================================
# Cash Position Schemas
# ============================================================================

class DailyCashPositionBase(BaseModel):
    """Base schema for daily cash position"""
    position_date: date
    area_id: int
    bank_account_id: int
    opening_balance: Decimal
    closing_balance: Decimal
    total_inflows: Decimal = Decimal("0")
    total_outflows: Decimal = Decimal("0")
    net_change: Decimal = Decimal("0")
    transaction_count: int = 0
    reconciled_count: int = 0
    unreconciled_count: int = 0
    gl_balance: Optional[Decimal] = None
    variance: Optional[Decimal] = None


class DailyCashPositionCreate(DailyCashPositionBase):
    """Schema for creating a daily cash position"""
    pass


class DailyCashPosition(DailyCashPositionBase):
    """Schema for daily cash position response"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


# ============================================================================
# Cash Flow Schemas
# ============================================================================

class CashFlowTransactionBase(BaseModel):
    """Base schema for cash flow transaction"""
    bank_transaction_id: int
    area_id: int
    category: CashFlowCategory
    subcategory: Optional[str] = None
    amount: Decimal
    transaction_date: date
    description: Optional[str] = None
    is_auto_classified: bool = False
    classification_confidence: Optional[Decimal] = None


class CashFlowTransactionCreate(CashFlowTransactionBase):
    """Schema for creating a cash flow transaction"""
    pass


class CashFlowTransaction(CashFlowTransactionBase):
    """Schema for cash flow transaction response"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class CashFlowSummary(BaseModel):
    """Summary of cash flows by category"""
    operating_inflows: Decimal = Decimal("0")
    operating_outflows: Decimal = Decimal("0")
    net_operating: Decimal = Decimal("0")

    investing_inflows: Decimal = Decimal("0")
    investing_outflows: Decimal = Decimal("0")
    net_investing: Decimal = Decimal("0")

    financing_inflows: Decimal = Decimal("0")
    financing_outflows: Decimal = Decimal("0")
    net_financing: Decimal = Decimal("0")

    net_change: Decimal = Decimal("0")


# ============================================================================
# Alert Schemas
# ============================================================================

class BankingAlertBase(BaseModel):
    """Base schema for banking alert"""
    alert_type: AlertType
    severity: AlertSeverity
    area_id: Optional[int] = None
    bank_account_id: Optional[int] = None
    bank_transaction_id: Optional[int] = None
    title: str
    message: str
    amount: Optional[Decimal] = None


class BankingAlertCreate(BankingAlertBase):
    """Schema for creating a banking alert"""
    pass


class BankingAlert(BankingAlertBase):
    """Schema for banking alert response"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    is_acknowledged: bool
    acknowledged_by: Optional[int] = None
    acknowledged_at: Optional[datetime] = None
    is_resolved: bool
    resolved_by: Optional[int] = None
    resolved_at: Optional[datetime] = None
    resolution_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class AlertAcknowledge(BaseModel):
    """Schema for acknowledging an alert"""
    user_id: int


class AlertResolve(BaseModel):
    """Schema for resolving an alert"""
    user_id: int
    resolution_notes: Optional[str] = None


# ============================================================================
# Reconciliation Health Schemas
# ============================================================================

class ReconciliationHealthMetricBase(BaseModel):
    """Base schema for reconciliation health metric"""
    metric_date: date
    area_id: Optional[int] = None
    total_transactions: int = 0
    reconciled_transactions: int = 0
    unreconciled_transactions: int = 0
    reconciliation_rate: Optional[Decimal] = None
    avg_days_to_reconcile: Optional[Decimal] = None
    transactions_over_30_days: int = 0
    transactions_over_60_days: int = 0
    transactions_over_90_days: int = 0
    auto_matched_count: int = 0
    manual_matched_count: int = 0
    auto_match_rate: Optional[Decimal] = None
    gl_variance_count: int = 0
    total_gl_variance: Optional[Decimal] = None
    avg_gl_variance: Optional[Decimal] = None
    critical_alerts: int = 0
    warning_alerts: int = 0


class ReconciliationHealthMetricCreate(ReconciliationHealthMetricBase):
    """Schema for creating a reconciliation health metric"""
    pass


class ReconciliationHealthMetric(ReconciliationHealthMetricBase):
    """Schema for reconciliation health metric response"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


# ============================================================================
# Location Cash Flow Summary Schemas
# ============================================================================

class LocationCashFlowSummaryBase(BaseModel):
    """Base schema for location cash flow summary"""
    area_id: int
    summary_month: date
    opening_balance: Decimal
    closing_balance: Decimal
    operating_inflows: Decimal = Decimal("0")
    operating_outflows: Decimal = Decimal("0")
    net_operating_cash_flow: Decimal = Decimal("0")
    investing_inflows: Decimal = Decimal("0")
    investing_outflows: Decimal = Decimal("0")
    net_investing_cash_flow: Decimal = Decimal("0")
    financing_inflows: Decimal = Decimal("0")
    financing_outflows: Decimal = Decimal("0")
    net_financing_cash_flow: Decimal = Decimal("0")
    net_cash_change: Decimal = Decimal("0")
    daily_burn_rate: Optional[Decimal] = None
    runway_days: Optional[int] = None


class LocationCashFlowSummaryCreate(LocationCashFlowSummaryBase):
    """Schema for creating a location cash flow summary"""
    pass


class LocationCashFlowSummary(LocationCashFlowSummaryBase):
    """Schema for location cash flow summary response"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


# ============================================================================
# Dashboard Summary Schemas
# ============================================================================

class DashboardKPI(BaseModel):
    """Key performance indicator for dashboard"""
    label: str
    value: Decimal
    change: Optional[Decimal] = None  # Change vs previous period
    change_percent: Optional[Decimal] = None
    trend: Optional[str] = None  # "up", "down", "neutral"


class LocationSummary(BaseModel):
    """Summary for a single location"""
    area_id: int
    area_name: str
    total_balance: Decimal
    reconciled_transactions: int
    unreconciled_transactions: int
    reconciliation_rate: Decimal
    active_alerts: int
    gl_variance: Optional[Decimal] = None


class DashboardSummaryResponse(BaseModel):
    """Complete dashboard summary response"""
    # Top-level KPIs
    total_cash_balance: DashboardKPI
    gl_variance: DashboardKPI
    reconciliation_rate: DashboardKPI
    unreconciled_transactions: DashboardKPI

    # Location breakdown
    locations: List[LocationSummary]

    # Cash flow summary (last 30 days)
    cash_flow: CashFlowSummary

    # Active alerts summary
    critical_alerts: int
    warning_alerts: int
    info_alerts: int

    # Reconciliation health
    avg_days_to_reconcile: Optional[Decimal] = None
    transactions_over_30_days: int
    auto_match_rate: Optional[Decimal] = None


class CashFlowTrendPoint(BaseModel):
    """Single point in cash flow trend"""
    date: date
    opening_balance: Decimal
    closing_balance: Decimal
    net_change: Decimal
    inflows: Decimal
    outflows: Decimal


class CashFlowTrendResponse(BaseModel):
    """Cash flow trend over time"""
    area_id: Optional[int] = None
    area_name: Optional[str] = None
    start_date: date
    end_date: date
    data_points: List[CashFlowTrendPoint]


class ReconciliationTrendPoint(BaseModel):
    """Single point in reconciliation trend"""
    date: date
    total_transactions: int
    reconciled_transactions: int
    reconciliation_rate: Decimal
    avg_days_to_reconcile: Optional[Decimal] = None


class ReconciliationTrendResponse(BaseModel):
    """Reconciliation health trend over time"""
    area_id: Optional[int] = None
    area_name: Optional[str] = None
    start_date: date
    end_date: date
    data_points: List[ReconciliationTrendPoint]
