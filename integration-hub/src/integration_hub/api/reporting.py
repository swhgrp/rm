"""
Reporting API Endpoints

Provides analytics and reporting endpoints.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date, timedelta

from integration_hub.db.database import get_db
from integration_hub.services.reporting import ReportingService

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


@router.get("/dashboard")
async def get_dashboard(
    days: int = Query(30, ge=1, le=365, description="Days to look back for trends"),
    db: Session = Depends(get_db)
):
    """
    Get dashboard summary with key metrics.

    Returns summary of invoices, spend, mapping rates, and sync status.
    """
    service = ReportingService(db)
    return service.get_dashboard_summary(days)


@router.get("/vendor-spend")
async def get_vendor_spend(
    start_date: Optional[date] = Query(None, description="Start date for period"),
    end_date: Optional[date] = Query(None, description="End date for period"),
    limit: int = Query(20, ge=1, le=100, description="Number of vendors to return"),
    db: Session = Depends(get_db)
):
    """
    Get vendor spend breakdown.

    Shows top vendors by spend with invoice counts and averages.
    """
    service = ReportingService(db)
    return service.get_vendor_spend_report(start_date, end_date, limit)


@router.get("/daily-trend")
async def get_daily_trend(
    days: int = Query(30, ge=7, le=365, description="Number of days to include"),
    db: Session = Depends(get_db)
):
    """
    Get daily invoice trend data.

    Returns daily counts and amounts for charting.
    """
    service = ReportingService(db)
    return service.get_daily_invoice_trend(days)


@router.get("/mapping")
async def get_mapping_report(
    db: Session = Depends(get_db)
):
    """
    Get detailed mapping statistics.

    Shows mapping rates by method, vendor, and identifies unmapped items.
    """
    service = ReportingService(db)
    return service.get_mapping_report()


@router.get("/price-changes")
async def get_price_changes(
    days: int = Query(30, ge=1, le=365, description="Days to look back"),
    min_change_pct: float = Query(5.0, ge=0, le=100, description="Minimum % change to consider significant"),
    db: Session = Depends(get_db)
):
    """
    Get price change analysis.

    Shows price increases/decreases and identifies volatile items.
    """
    service = ReportingService(db)
    return service.get_price_change_report(days, min_change_pct)


@router.get("/sync-status")
async def get_sync_status(
    db: Session = Depends(get_db)
):
    """
    Get detailed sync status breakdown.

    Shows how many invoices have been sent to each system and errors.
    """
    service = ReportingService(db)
    return service.get_sync_status_report()


@router.get("/summary")
async def get_full_summary(
    days: int = Query(30, ge=1, le=365, description="Days for trend data"),
    db: Session = Depends(get_db)
):
    """
    Get a comprehensive summary combining all reports.

    Useful for generating a full dashboard in a single call.
    """
    service = ReportingService(db)

    return {
        'dashboard': service.get_dashboard_summary(days),
        'vendor_spend': service.get_vendor_spend_report(limit=10),
        'mapping': service.get_mapping_report(),
        'sync_status': service.get_sync_status_report()
    }
