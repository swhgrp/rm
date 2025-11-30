"""
General Accounting Dashboard API endpoints
"""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from datetime import date
from typing import Optional

from accounting.db.database import get_db
from accounting.models.user import User
from accounting.api.auth import require_auth
from accounting.services.general_dashboard_service import GeneralDashboardService
from accounting.schemas.general_dashboard import (
    ExecutiveSummaryResponse,
    RealTimeTrackingResponse,
    HistoricalTrendResponse,
    AlertSummaryResponse,
    DashboardSummaryResponse,
    AlertAcknowledgeRequest,
    AlertResolveRequest
)
from accounting.models.general_dashboard import DashboardAlert


router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


@router.get("/summary", response_model=ExecutiveSummaryResponse)
def get_dashboard_summary(
    as_of_date: Optional[date] = Query(None, description="As of date (defaults to today)"),
    area_id: Optional[int] = Query(None, description="Filter by location (null = all locations)"),
    period: Optional[str] = Query(None, description="Period: yesterday, wtd, mtd, ytd"),
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """
    Get executive dashboard summary with key financial metrics.

    Returns:
    - Net income (MTD, YTD)
    - Revenue metrics
    - Profit margins
    - Top 5 expense categories
    - Revenue by location
    """
    service = GeneralDashboardService(db)
    return service.get_executive_summary(as_of_date, area_id, period)


@router.get("/real-time", response_model=RealTimeTrackingResponse)
def get_real_time_tracking(
    as_of_date: Optional[date] = Query(None, description="As of date (defaults to today)"),
    area_id: Optional[int] = Query(None, description="Filter by location"),
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """
    Get real-time financial tracking metrics.

    Returns:
    - Daily sales metrics
    - COGS percentages
    - Bank balances
    - Cash flow forecast
    - AP aging summary
    - Accounting health indicators
    """
    service = GeneralDashboardService(db)
    return service.get_real_time_tracking(as_of_date, area_id)


@router.get("/trends", response_model=HistoricalTrendResponse)
def get_historical_trends(
    months: int = Query(6, ge=1, le=24, description="Number of months to analyze"),
    area_id: Optional[int] = Query(None, description="Filter by location"),
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """
    Get historical performance trends over multiple months.

    Returns:
    - Revenue trends
    - COGS% trends
    - Labor% trends (from closed periods)
    - Net income trends
    """
    service = GeneralDashboardService(db)
    return service.get_historical_trends(months, area_id)


@router.get("/alerts", response_model=AlertSummaryResponse)
def get_alerts(
    area_id: Optional[int] = Query(None, description="Filter by location"),
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """
    Get active dashboard alerts.

    Returns:
    - Alert counts by severity
    - List of active alerts with details
    - Action URLs to resolve issues
    """
    service = GeneralDashboardService(db)
    return service.get_alert_summary(area_id)


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(
    alert_id: int,
    request: AlertAcknowledgeRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Acknowledge a dashboard alert"""
    alert = db.query(DashboardAlert).filter(DashboardAlert.id == alert_id).first()

    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.acknowledge(request.user_id)
    db.commit()

    return {"success": True, "message": "Alert acknowledged"}


@router.post("/alerts/{alert_id}/resolve")
def resolve_alert(
    alert_id: int,
    request: AlertResolveRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Resolve a dashboard alert"""
    alert = db.query(DashboardAlert).filter(DashboardAlert.id == alert_id).first()

    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.resolve(request.user_id, request.resolution_notes)
    db.commit()

    return {"success": True, "message": "Alert resolved"}
