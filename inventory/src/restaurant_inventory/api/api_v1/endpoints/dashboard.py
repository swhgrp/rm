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
from restaurant_inventory.models.transfer import Transfer
from restaurant_inventory.models.waste import WasteRecord
from restaurant_inventory.services.hub_client import get_hub_client

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

    # COGS (Previous 7 Complete Days) - Fetched from Hub
    total_cogs = 0.0
    daily_cogs_from_hub = {}
    recent_invoices_from_hub = []

    try:
        hub_client = get_hub_client()
        cogs_summary = await hub_client.get_cogs_summary(
            start_date=start_date.date(),
            end_date=(end_date - timedelta(days=1)).date(),  # end_date is exclusive
            location_id=location_id
        )
        total_cogs = cogs_summary.get("total_cogs", 0.0)
        daily_cogs_from_hub = cogs_summary.get("daily_cogs", {})
        recent_invoices_from_hub = cogs_summary.get("recent_invoices", [])
        logger.info(f"Fetched COGS from Hub: ${total_cogs:.2f}")
    except Exception as e:
        logger.warning(f"Error fetching COGS from Hub: {str(e)} - using 0.0")

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

    # COGS aggregated by date - from Hub data
    # Convert Hub daily_cogs (date strings) to date objects for lookup
    from datetime import datetime as dt
    cogs_dict = {}
    for date_str, amount in daily_cogs_from_hub.items():
        try:
            cogs_date = dt.fromisoformat(date_str).date()
            cogs_dict[cogs_date] = amount
        except (ValueError, TypeError):
            pass

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

    # Recent Invoices - from Hub data (already fetched with COGS summary)
    invoices_data = []
    for inv in recent_invoices_from_hub:
        invoices_data.append({
            'id': inv.get('id'),
            'invoice_number': inv.get('invoice_number'),
            'vendor_name': inv.get('vendor_name'),
            'location_name': inv.get('location_name'),
            'total': inv.get('total_amount', 0),
            'status': inv.get('status'),
            'invoice_date': inv.get('invoice_date'),
            'item_count': inv.get('item_count', 0),
            'mapped_item_count': inv.get('mapped_item_count', 0)
        })

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
