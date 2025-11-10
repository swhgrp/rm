"""
Dashboard Analytics API endpoints
"""

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
import logging

from restaurant_inventory.core.deps import get_db, get_current_user, get_user_location_ids
from restaurant_inventory.core.cache import cache, CacheKeys
from restaurant_inventory.models.user import User
from restaurant_inventory.models.pos_sale import POSSale, POSSaleItem
from restaurant_inventory.models.inventory import Inventory
from restaurant_inventory.models.invoice import Invoice
from restaurant_inventory.models.transfer import Transfer
from restaurant_inventory.models.waste import WasteRecord

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/analytics")
async def get_dashboard_analytics(
    response: Response,
    location_id: Optional[int] = Query(None, description="Filter by location ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get dashboard analytics including KPIs and trends (with Redis caching)"""

    # Prevent browser caching (but use server-side Redis cache)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    # Generate cache key based on location filter and user's location access
    import pytz
    local_tz = pytz.timezone('America/New_York')
    now_local = datetime.now(local_tz)
    cache_date = now_local.strftime('%Y-%m-%d')

    # Include user's location restrictions in cache key
    user_location_ids = get_user_location_ids(current_user)
    if user_location_ids is None:
        user_cache_suffix = "all"
    elif len(user_location_ids) == 0:
        user_cache_suffix = "none"
    else:
        user_cache_suffix = "_".join(map(str, sorted(user_location_ids)))

    cache_key = f"dashboard:analytics:{location_id or 'all'}:{cache_date}:user_{user_cache_suffix}"

    # Try to get from cache
    cached_data = cache.get(cache_key)
    if cached_data is not None:
        response.headers["X-Cache-Status"] = "HIT"
        logger.info(f"Dashboard analytics cache HIT: {cache_key}")
        return cached_data

    response.headers["X-Cache-Status"] = "MISS"
    logger.info(f"Dashboard analytics cache MISS: {cache_key}")

    # Date range: previous 7 complete days (NOT including today)
    # Use business timezone (America/New_York) to determine "today"
    import pytz
    local_tz = pytz.timezone('America/New_York')  # EDT/EST

    # Get current time in business timezone
    now_local = datetime.now(local_tz)
    today_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)

    # Convert to UTC for database queries
    today_midnight_utc = today_local.astimezone(timezone.utc)

    # Get previous 7 days: today midnight UTC (excluded) back to 7 days ago
    end_date = today_midnight_utc  # Start of today in UTC (excluded with <)
    start_date = end_date - timedelta(days=7)  # 7 days before today

    # Build base query filters with user location enforcement
    # Note: user_location_ids already defined above for cache key
    def apply_location_filter(query, model):
        # First, enforce user's location access
        if user_location_ids is not None:  # None means admin (access all)
            if len(user_location_ids) == 0:
                # User has no assigned locations, return empty result
                return query.filter(model.location_id == -1)  # No location has ID -1
            # User has specific locations assigned
            query = query.filter(model.location_id.in_(user_location_ids))

        # Then apply optional location_id filter from query parameter
        if location_id:
            # Verify user has access to this location
            if user_location_ids is not None and location_id not in user_location_ids:
                # User trying to access location they don't have access to
                from fastapi import HTTPException, status
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"You don't have access to location {location_id}"
                )
            query = query.filter(model.location_id == location_id)

        return query

    # Total Sales (Previous 7 Complete Days)
    # Use subtotal (net sales before tax/tip) for consistency with Clover "Gross Sales"
    # Exclude zero-dollar orders (voids, cancellations)
    sales_query = db.query(func.sum(POSSale.subtotal)).filter(
        POSSale.order_date >= start_date,
        POSSale.order_date < end_date,  # Exclude today
        POSSale.total > 0  # Exclude zero-dollar orders
    )
    sales_query = apply_location_filter(sales_query, POSSale)
    total_sales = float(sales_query.scalar() or 0.0)

    # Previous Week Sales (for week-over-week comparison)
    prev_week_end = start_date  # End of previous week = start of current week
    prev_week_start = prev_week_end - timedelta(days=7)  # 7 days before that

    prev_sales_query = db.query(func.sum(POSSale.subtotal)).filter(
        POSSale.order_date >= prev_week_start,
        POSSale.order_date < prev_week_end,
        POSSale.total > 0  # Exclude zero-dollar orders
    )
    prev_sales_query = apply_location_filter(prev_sales_query, POSSale)
    prev_week_sales = float(prev_sales_query.scalar() or 0.0)

    # Calculate week-over-week percentage change
    wow_change = None
    if prev_week_sales > 0:
        wow_change = ((total_sales - prev_week_sales) / prev_week_sales) * 100
    elif total_sales > 0:
        # Previous week had zero sales but current week has sales
        wow_change = 100.0  # 100% increase from zero

    # COGS (Previous 7 Complete Days) - Sum of approved invoices
    cogs_query = db.query(func.sum(Invoice.total)).filter(
        Invoice.invoice_date >= start_date,
        Invoice.invoice_date < end_date,  # Exclude today
        Invoice.status == 'APPROVED'
    )
    cogs_query = apply_location_filter(cogs_query, Invoice)
    total_cogs = float(cogs_query.scalar() or 0.0)

    # Gross Margin %
    gross_margin = ((total_sales - total_cogs) / total_sales * 100) if total_sales > 0 else 0.0

    # Current Inventory Value
    inv_query = db.query(
        func.sum(Inventory.current_quantity * Inventory.unit_cost)
    )
    inv_query = apply_location_filter(inv_query, Inventory)
    inventory_value = float(inv_query.scalar() or 0.0)

    # Daily Sales & COGS for trend chart (last 7 days)
    # Optimized: Use single aggregated query instead of loop (7x faster)
    from sqlalchemy import cast, Date

    # Sales aggregated by date (single query for all 7 days)
    sales_by_date_query = db.query(
        cast(POSSale.order_date, Date).label('date'),
        func.sum(POSSale.subtotal).label('sales')
    ).filter(
        POSSale.order_date >= start_date,
        POSSale.order_date < end_date,
        POSSale.total > 0  # Exclude zero-dollar orders
    ).group_by(cast(POSSale.order_date, Date))

    sales_by_date_query = apply_location_filter(sales_by_date_query, POSSale)
    sales_dict = {row.date: float(row.sales) for row in sales_by_date_query.all()}

    # COGS aggregated by date (single query for all 7 days)
    cogs_by_date_query = db.query(
        cast(Invoice.invoice_date, Date).label('date'),
        func.sum(Invoice.total).label('cogs')
    ).filter(
        Invoice.invoice_date >= start_date,
        Invoice.invoice_date < end_date,
        Invoice.status == 'APPROVED'
    ).group_by(cast(Invoice.invoice_date, Date))

    cogs_by_date_query = apply_location_filter(cogs_by_date_query, Invoice)
    cogs_dict = {row.date: float(row.cogs) for row in cogs_by_date_query.all()}

    # Build daily data array from dictionaries
    daily_data = []
    for i in range(7):
        day = start_date + timedelta(days=i)
        day_date = day.date()

        daily_data.append({
            'date': day.strftime('%Y-%m-%d'),
            'day_name': day.strftime('%a'),
            'sales': sales_dict.get(day_date, 0.0),
            'cogs': cogs_dict.get(day_date, 0.0)
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
        POSSale.order_date < end_date,  # Exclude today (consistent with sales query)
        POSSale.total > 0  # Exclude zero-dollar orders (voids, cancellations)
    )

    # Apply location filter using the same function as sales query
    top_items_query = apply_location_filter(top_items_query, POSSale)

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

    # Build response data
    result = {
        'kpis': {
            'total_sales': float(total_sales),
            'total_cogs': float(total_cogs),
            'gross_margin': float(gross_margin),
            'inventory_value': float(inventory_value),
            'wow_sales_change': wow_change,  # Week-over-week sales change percentage
            'prev_week_sales': float(prev_week_sales)  # Previous week sales amount
        },
        'daily_trend': daily_data,
        'top_items': top_items,
        'recent_invoices': invoices_data,
        'recent_transfers': transfers_data,
        'recent_waste': waste_data
    }

    # Cache the result for 5 minutes (300 seconds)
    cache.set(cache_key, result, ttl=300)
    logger.info(f"Dashboard analytics cached: {cache_key} (TTL: 300s)")

    return result
