"""API endpoints for Banking Dashboard"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import date, timedelta

from accounting.db.database import get_db
from accounting.models.user import User
from accounting.api.auth import get_current_user
from accounting.services.dashboard_service import DashboardService
from accounting.services.health_metrics_service import HealthMetricsService
from accounting.services.alert_service import AlertService
from accounting.models.banking_dashboard import AlertSeverity, AlertType
from accounting.schemas.banking_dashboard import (
    DashboardSummaryResponse,
    CashFlowTrendResponse,
    ReconciliationTrendResponse,
    BankingAlert,
    BankingAlertCreate,
    AlertAcknowledge,
    AlertResolve,
    ReconciliationHealthMetric,
    DailyCashPosition,
    LocationCashFlowSummary
)

router = APIRouter()


# ============================================================================
# Dashboard Summary Endpoints
# ============================================================================

@router.get("/summary", response_model=DashboardSummaryResponse)
async def get_dashboard_summary(
    area_id: Optional[int] = Query(None, description="Filter by location ID"),
    start_date: Optional[date] = Query(None, description="Start date for metrics"),
    end_date: Optional[date] = Query(None, description="End date for metrics"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get complete dashboard summary with KPIs, location breakdown, and alerts.

    - **area_id**: Optional filter by specific location
    - **start_date**: Start date for calculations (default: 30 days ago)
    - **end_date**: End date for calculations (default: today)
    """
    service = DashboardService(db)
    return service.get_dashboard_summary(area_id, start_date, end_date)


@router.get("/cash-flow-trend", response_model=CashFlowTrendResponse)
async def get_cash_flow_trend(
    area_id: Optional[int] = Query(None, description="Filter by location ID"),
    start_date: Optional[date] = Query(None, description="Start date"),
    end_date: Optional[date] = Query(None, description="End date"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get cash flow trend over time.

    Returns daily cash positions showing opening/closing balances and cash flows.
    """
    service = DashboardService(db)
    return service.get_cash_flow_trend(area_id, start_date, end_date)


@router.get("/reconciliation-trend", response_model=ReconciliationTrendResponse)
async def get_reconciliation_trend(
    area_id: Optional[int] = Query(None, description="Filter by location ID"),
    start_date: Optional[date] = Query(None, description="Start date"),
    end_date: Optional[date] = Query(None, description="End date"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get reconciliation health trend over time.

    Returns daily reconciliation metrics showing rates and aging.
    """
    service = DashboardService(db)
    return service.get_reconciliation_trend(area_id, start_date, end_date)


# ============================================================================
# Alert Management Endpoints
# ============================================================================

@router.get("/alerts", response_model=List[BankingAlert])
async def get_alerts(
    area_id: Optional[int] = Query(None, description="Filter by location ID"),
    severity: Optional[AlertSeverity] = Query(None, description="Filter by severity"),
    alert_type: Optional[AlertType] = Query(None, description="Filter by alert type"),
    active_only: bool = Query(True, description="Show only active alerts"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get banking alerts with optional filters.

    - **area_id**: Filter by specific location
    - **severity**: Filter by severity (critical, warning, info)
    - **alert_type**: Filter by alert type
    - **active_only**: Show only active (unresolved) alerts
    """
    service = AlertService(db)

    if active_only:
        return service.get_active_alerts(area_id, severity, alert_type)
    else:
        # Get all alerts (active and resolved)
        query = db.query(BankingAlert)

        if area_id:
            query = query.filter(BankingAlert.area_id == area_id)
        if severity:
            query = query.filter(BankingAlert.severity == severity)
        if alert_type:
            query = query.filter(BankingAlert.alert_type == alert_type)

        return query.order_by(BankingAlert.created_at.desc()).all()


@router.post("/alerts/generate", response_model=List[BankingAlert])
async def generate_alerts(
    area_id: Optional[int] = Query(None, description="Generate for specific location"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Manually trigger alert generation.

    Runs all alert checks and creates new alerts where conditions are met.
    """
    service = AlertService(db)
    return service.generate_all_alerts(area_id)


@router.post("/alerts/{alert_id}/acknowledge", response_model=BankingAlert)
async def acknowledge_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Acknowledge an alert.

    Marks the alert as acknowledged by the current user.
    """
    service = AlertService(db)
    return service.acknowledge_alert(alert_id, current_user.id)


@router.post("/alerts/{alert_id}/resolve", response_model=BankingAlert)
async def resolve_alert(
    alert_id: int,
    data: AlertResolve,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Resolve an alert.

    Marks the alert as resolved and deactivates it.
    """
    service = AlertService(db)
    return service.resolve_alert(alert_id, data.user_id, data.resolution_notes)


@router.post("/alerts/auto-resolve")
async def auto_resolve_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Auto-resolve alerts that are no longer relevant.

    Returns count of alerts that were auto-resolved.
    """
    service = AlertService(db)
    count = service.auto_resolve_alerts()
    return {"resolved_count": count}


# ============================================================================
# Health Metrics Endpoints
# ============================================================================

@router.post("/metrics/calculate")
async def calculate_health_metrics(
    target_date: Optional[date] = Query(None, description="Calculate for specific date (default: today)"),
    area_id: Optional[int] = Query(None, description="Calculate for specific location"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Calculate and store reconciliation health metrics.

    Manually trigger metric calculation for a specific date.
    """
    if not target_date:
        target_date = date.today()

    service = HealthMetricsService(db)
    metric = service.calculate_daily_metrics(target_date, area_id)

    return {"status": "success", "metric_id": metric.id, "date": target_date}


@router.post("/metrics/calculate-range")
async def calculate_metrics_range(
    start_date: date = Query(..., description="Start date"),
    end_date: date = Query(..., description="End date"),
    area_id: Optional[int] = Query(None, description="Calculate for specific location"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Calculate health metrics for a date range.

    Useful for backfilling historical metrics.
    """
    service = HealthMetricsService(db)
    metrics = service.calculate_metrics_for_date_range(start_date, end_date, area_id)

    return {"status": "success", "metrics_calculated": len(metrics), "start_date": start_date, "end_date": end_date}


@router.get("/metrics", response_model=List[ReconciliationHealthMetric])
async def get_health_metrics(
    start_date: Optional[date] = Query(None, description="Start date"),
    end_date: Optional[date] = Query(None, description="End date"),
    area_id: Optional[int] = Query(None, description="Filter by location ID"),
    limit: int = Query(30, description="Maximum number of records"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get historical reconciliation health metrics.

    Returns metrics for the specified date range and location.
    """
    from accounting.models.banking_dashboard import ReconciliationHealthMetric as RHM

    query = db.query(RHM)

    if area_id:
        query = query.filter(RHM.area_id == area_id)

    if start_date:
        query = query.filter(RHM.metric_date >= start_date)

    if end_date:
        query = query.filter(RHM.metric_date <= end_date)

    query = query.order_by(RHM.metric_date.desc()).limit(limit)

    return query.all()


# ============================================================================
# Cash Position Endpoints
# ============================================================================

@router.get("/cash-positions", response_model=List[DailyCashPosition])
async def get_cash_positions(
    start_date: Optional[date] = Query(None, description="Start date"),
    end_date: Optional[date] = Query(None, description="End date"),
    area_id: Optional[int] = Query(None, description="Filter by location ID"),
    bank_account_id: Optional[int] = Query(None, description="Filter by bank account ID"),
    limit: int = Query(30, description="Maximum number of records"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get daily cash position snapshots.

    Returns historical daily cash positions for trending and analysis.
    """
    from accounting.models.banking_dashboard import DailyCashPosition as DCP

    query = db.query(DCP)

    if area_id:
        query = query.filter(DCP.area_id == area_id)

    if bank_account_id:
        query = query.filter(DCP.bank_account_id == bank_account_id)

    if start_date:
        query = query.filter(DCP.position_date >= start_date)

    if end_date:
        query = query.filter(DCP.position_date <= end_date)

    query = query.order_by(DCP.position_date.desc()).limit(limit)

    return query.all()


# ============================================================================
# Cash Flow Summary Endpoints
# ============================================================================

@router.get("/cash-flow-summaries", response_model=List[LocationCashFlowSummary])
async def get_cash_flow_summaries(
    start_month: Optional[date] = Query(None, description="Start month (first day)"),
    end_month: Optional[date] = Query(None, description="End month (first day)"),
    area_id: Optional[int] = Query(None, description="Filter by location ID"),
    limit: int = Query(12, description="Maximum number of records"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get monthly cash flow summaries.

    Returns aggregated monthly cash flow data by location.
    """
    from accounting.models.banking_dashboard import LocationCashFlowSummary as LCFS

    query = db.query(LCFS)

    if area_id:
        query = query.filter(LCFS.area_id == area_id)

    if start_month:
        query = query.filter(LCFS.summary_month >= start_month)

    if end_month:
        query = query.filter(LCFS.summary_month <= end_month)

    query = query.order_by(LCFS.summary_month.desc()).limit(limit)

    return query.all()
