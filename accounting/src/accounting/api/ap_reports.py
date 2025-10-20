"""
API endpoints for Accounts Payable Reports
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import Optional
from datetime import date, timedelta
from decimal import Decimal
from collections import defaultdict

from accounting.db.database import get_db
from accounting.models.user import User
from accounting.models.vendor_bill import VendorBill, BillStatus
from accounting.schemas.vendor_bill import APAgingReportResponse, AgingBucket, VendorAgingDetail
from accounting.api.auth import require_auth

router = APIRouter(prefix="/api/ap-reports", tags=["ap_reports"])


@router.get("/aging", response_model=APAgingReportResponse)
def get_ap_aging_report(
    as_of_date: date = Query(default_factory=date.today, description="Date to calculate aging as of"),
    area_id: Optional[int] = Query(None, description="Filter by location/area (null = all locations)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """
    Generate Accounts Payable Aging Report

    Shows outstanding payables grouped by vendor and aged into buckets:
    - Current (0-30 days)
    - 31-60 days
    - 61-90 days
    - Over 90 days

    Only includes unpaid or partially paid bills
    """

    # Build query for outstanding bills
    query = db.query(VendorBill).filter(
        VendorBill.status.in_([
            BillStatus.APPROVED,
            BillStatus.PARTIALLY_PAID,
            BillStatus.PENDING_APPROVAL  # Include pending for full picture
        ]),
        VendorBill.paid_amount < VendorBill.total_amount  # Has outstanding balance
    )

    # Apply area filter if specified
    area_name = None
    if area_id is not None:
        query = query.filter(VendorBill.area_id == area_id)
        from accounting.models.area import Area
        area = db.query(Area).filter(Area.id == area_id).first()
        if area:
            area_name = area.name

    bills = query.all()

    # Group by vendor and age bills
    vendor_aging = defaultdict(lambda: {
        'vendor_name': '',
        'vendor_id': None,
        'current': Decimal('0.00'),
        'days_31_60': Decimal('0.00'),
        'days_61_90': Decimal('0.00'),
        'over_90_days': Decimal('0.00'),
        'total': Decimal('0.00'),
    })

    for bill in bills:
        balance = bill.total_amount - bill.paid_amount

        # Calculate days overdue from due date
        days_old = (as_of_date - bill.due_date).days

        # Determine aging bucket
        vendor_key = (bill.vendor_name, bill.vendor_id)
        if vendor_key not in vendor_aging:
            vendor_aging[vendor_key]['vendor_name'] = bill.vendor_name
            vendor_aging[vendor_key]['vendor_id'] = bill.vendor_id

        if days_old <= 30:
            vendor_aging[vendor_key]['current'] += balance
        elif days_old <= 60:
            vendor_aging[vendor_key]['days_31_60'] += balance
        elif days_old <= 90:
            vendor_aging[vendor_key]['days_61_90'] += balance
        else:
            vendor_aging[vendor_key]['over_90_days'] += balance

        vendor_aging[vendor_key]['total'] += balance

    # Convert to list and sort by vendor name
    vendors_list = [
        VendorAgingDetail(
            vendor_name=data['vendor_name'],
            vendor_id=data['vendor_id'],
            current=data['current'],
            days_31_60=data['days_31_60'],
            days_61_90=data['days_61_90'],
            over_90_days=data['over_90_days'],
            total=data['total'],
        )
        for data in vendor_aging.values()
    ]
    vendors_list.sort(key=lambda x: x.vendor_name)

    # Calculate totals
    totals = AgingBucket(
        current=sum(v.current for v in vendors_list),
        days_31_60=sum(v.days_31_60 for v in vendors_list),
        days_61_90=sum(v.days_61_90 for v in vendors_list),
        over_90_days=sum(v.over_90_days for v in vendors_list),
        total=sum(v.total for v in vendors_list),
    )

    return APAgingReportResponse(
        as_of_date=as_of_date,
        area_id=area_id,
        area_name=area_name,
        vendors=vendors_list,
        totals=totals,
    )
