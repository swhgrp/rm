"""
Dashboard Analytics API endpoints
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from restaurant_inventory.core.deps import get_db, get_current_user
from restaurant_inventory.models.user import User
from restaurant_inventory.models.pos_sale import POSSale, POSSaleItem
from restaurant_inventory.models.inventory import Inventory
from restaurant_inventory.models.invoice import Invoice
from restaurant_inventory.models.transfer import Transfer
from restaurant_inventory.models.waste import WasteRecord

router = APIRouter()


@router.get("/analytics")
async def get_dashboard_analytics(
    location_id: Optional[int] = Query(None, description="Filter by location ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get dashboard analytics including KPIs and trends"""

    # Date range: last 7 days
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)

    # Build base query filters
    def apply_location_filter(query, model):
        if location_id:
            return query.filter(model.location_id == location_id)
        return query

    # Total Sales (Last 7 Days)
    sales_query = db.query(func.sum(POSSale.total)).filter(
        POSSale.order_date >= start_date,
        POSSale.order_date <= end_date
    )
    sales_query = apply_location_filter(sales_query, POSSale)
    total_sales = sales_query.scalar() or 0.0

    # COGS (Last 7 Days) - Sum of approved invoices
    cogs_query = db.query(func.sum(Invoice.total)).filter(
        Invoice.invoice_date >= start_date,
        Invoice.invoice_date <= end_date,
        Invoice.status == 'APPROVED'
    )
    cogs_query = apply_location_filter(cogs_query, Invoice)
    total_cogs = cogs_query.scalar() or 0.0

    # Gross Margin %
    gross_margin = ((total_sales - total_cogs) / total_sales * 100) if total_sales > 0 else 0.0

    # Current Inventory Value
    inv_query = db.query(
        func.sum(Inventory.current_quantity * Inventory.unit_cost)
    )
    inv_query = apply_location_filter(inv_query, Inventory)
    inventory_value = inv_query.scalar() or 0.0

    # Daily Sales & COGS for trend chart (last 7 days)
    daily_data = []
    for i in range(7):
        day = start_date + timedelta(days=i)
        day_end = day + timedelta(days=1)

        day_sales_query = db.query(func.sum(POSSale.total)).filter(
            POSSale.order_date >= day,
            POSSale.order_date < day_end
        )
        day_sales_query = apply_location_filter(day_sales_query, POSSale)
        day_sales = day_sales_query.scalar() or 0.0

        day_cogs_query = db.query(func.sum(Invoice.total)).filter(
            Invoice.invoice_date >= day,
            Invoice.invoice_date < day_end,
            Invoice.status == 'APPROVED'
        )
        day_cogs_query = apply_location_filter(day_cogs_query, Invoice)
        day_cogs = day_cogs_query.scalar() or 0.0

        daily_data.append({
            'date': day.strftime('%Y-%m-%d'),
            'day_name': day.strftime('%a'),
            'sales': float(day_sales),
            'cogs': float(day_cogs)
        })

    # Top Selling Items (by revenue, last 7 days)
    top_items_query = db.query(
        POSSaleItem.item_name,
        func.sum(POSSaleItem.quantity).label('total_quantity'),
        func.sum(POSSaleItem.total_price).label('total_revenue')
    ).join(
        POSSale, POSSaleItem.sale_id == POSSale.id
    ).filter(
        POSSale.order_date >= start_date,
        POSSale.order_date <= end_date
    )

    if location_id:
        top_items_query = top_items_query.filter(POSSale.location_id == location_id)

    top_items_query = top_items_query.group_by(
        POSSaleItem.item_name
    ).order_by(
        func.sum(POSSaleItem.total_price).desc()
    ).limit(10)

    top_items = [
        {
            'item_name': item[0],
            'quantity_sold': float(item[1]),
            'revenue': float(item[2])
        }
        for item in top_items_query.all()
    ]

    # Recent Invoices (last 5)
    recent_invoices_query = db.query(Invoice).options(
        joinedload(Invoice.location)
    )
    recent_invoices_query = apply_location_filter(recent_invoices_query, Invoice)
    recent_invoices = recent_invoices_query.order_by(
        Invoice.uploaded_at.desc()
    ).limit(5).all()

    invoices_data = [
        {
            'id': inv.id,
            'invoice_number': inv.invoice_number,
            'location_name': inv.location.name if inv.location else 'Unknown',
            'total': float(inv.total) if inv.total else 0.0,
            'status': inv.status.value,
            'uploaded_at': inv.uploaded_at.isoformat() if inv.uploaded_at else None
        }
        for inv in recent_invoices
    ]

    # Recent Transfers (last 5)
    recent_transfers_query = db.query(Transfer).options(
        joinedload(Transfer.from_location),
        joinedload(Transfer.to_location)
    )

    if location_id:
        # Show transfers from or to this location
        recent_transfers_query = recent_transfers_query.filter(
            (Transfer.from_location_id == location_id) | (Transfer.to_location_id == location_id)
        )

    recent_transfers = recent_transfers_query.order_by(
        Transfer.created_at.desc()
    ).limit(5).all()

    transfers_data = [
        {
            'id': transfer.id,
            'from_location_name': transfer.from_location.name if transfer.from_location else 'Unknown',
            'to_location_name': transfer.to_location.name if transfer.to_location else 'Unknown',
            'status': transfer.status.value,
            'created_at': transfer.created_at.isoformat() if transfer.created_at else None
        }
        for transfer in recent_transfers
    ]

    # Recent Waste (last 5)
    recent_waste_query = db.query(WasteRecord).options(
        joinedload(WasteRecord.location),
        joinedload(WasteRecord.master_item)
    )
    recent_waste_query = apply_location_filter(recent_waste_query, WasteRecord)
    recent_waste = recent_waste_query.order_by(
        WasteRecord.recorded_at.desc()
    ).limit(5).all()

    waste_data = [
        {
            'id': waste.id,
            'master_item_id': waste.master_item_id,
            'item_name': waste.master_item.name if waste.master_item else 'Unknown',
            'location_name': waste.location.name if waste.location else 'Unknown',
            'quantity_wasted': float(waste.quantity_wasted),
            'total_cost': float(waste.total_cost) if waste.total_cost else 0.0,
            'reason_code': waste.reason_code,
            'recorded_at': waste.recorded_at.isoformat() if waste.recorded_at else None
        }
        for waste in recent_waste
    ]

    return {
        'kpis': {
            'total_sales': float(total_sales),
            'total_cogs': float(total_cogs),
            'gross_margin': float(gross_margin),
            'inventory_value': float(inventory_value)
        },
        'daily_trend': daily_data,
        'top_items': top_items,
        'recent_invoices': invoices_data,
        'recent_transfers': transfers_data,
        'recent_waste': waste_data
    }
