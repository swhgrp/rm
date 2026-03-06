"""
Restaurant Inventory Management System
Main FastAPI application with complete endpoints and web interface
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import text
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import logging

from restaurant_inventory.core.config import settings
from restaurant_inventory.db.database import get_db
from restaurant_inventory.models import Location, User, MasterItem
from restaurant_inventory.core.deps import get_current_user, require_admin
from restaurant_inventory.api.api_v1.endpoints import auth
from restaurant_inventory.api.api_v1.endpoints import locations
from restaurant_inventory.api.api_v1.endpoints import storage_areas
from restaurant_inventory.api.api_v1.endpoints import items
from restaurant_inventory.api.api_v1.endpoints import inventory
from restaurant_inventory.api.api_v1.endpoints import transfers
from restaurant_inventory.api.api_v1.endpoints import users
from restaurant_inventory.api.api_v1.endpoints import audit_log
from restaurant_inventory.api.api_v1.endpoints import count_templates
from restaurant_inventory.api.api_v1.endpoints import count_sessions
from restaurant_inventory.api.api_v1.endpoints import roles
from restaurant_inventory.api.api_v1.endpoints import categories
from restaurant_inventory.api.api_v1.endpoints import reports
from restaurant_inventory.api.api_v1.endpoints import vendors
from restaurant_inventory.api.api_v1.endpoints import waste
from restaurant_inventory.api.api_v1.endpoints import recipes
from restaurant_inventory.api.api_v1.endpoints import pos
from restaurant_inventory.api.api_v1.endpoints import units
from restaurant_inventory.api.api_v1.endpoints import dashboard
from restaurant_inventory.api.api_v1.endpoints import cache_management
from restaurant_inventory.api.api_v1.endpoints import hub_invoices
from restaurant_inventory.api.api_v1.endpoints import hub_vendor_items
from restaurant_inventory.api.api_v1.endpoints import order_sheet_templates
from restaurant_inventory.api.api_v1.endpoints import order_sheets
# REMOVED (Dec 25, 2025): invoices, vendor_items - Hub is source of truth
from restaurant_inventory.services.scheduler import start_scheduler, stop_scheduler

logger = logging.getLogger(__name__)

# Startup and shutdown events
def startup_event_handler():
    """Handle application startup"""
    logger.warning("=" * 60)
    logger.warning("🚀 APPLICATION STARTING UP")
    logger.warning("=" * 60)
    try:
        start_scheduler()
        logger.warning("✓ Background scheduler initialized successfully")
        logger.warning("✓ Auto-sync will run every 10 minutes")
        logger.warning("=" * 60)
    except Exception as e:
        logger.error(f"✗ Error starting scheduler: {str(e)}")
        import traceback
        traceback.print_exc()

def shutdown_event_handler():
    """Handle application shutdown"""
    logger.warning("=" * 60)
    logger.warning("🛑 APPLICATION SHUTTING DOWN")
    logger.warning("=" * 60)
    try:
        stop_scheduler()
        logger.warning("✓ Background scheduler stopped successfully")
    except Exception as e:
        logger.error(f"✗ Error stopping scheduler: {str(e)}")


# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Multi-location restaurant inventory management system",
    root_path="/inventory"
)

# Register startup and shutdown events
app.add_event_handler("startup", startup_event_handler)
app.add_event_handler("shutdown", shutdown_event_handler)

# Add rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Custom exception handler for authentication redirects
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions - redirect 401 to Portal login for HTML requests"""
    if exc.status_code == 401:  # HTTP_401_UNAUTHORIZED
        # Check if this is an HTML request (not API)
        # API requests go through /api/ path and should get JSON responses
        accept = request.headers.get("accept", "")
        path = str(request.url.path)
        is_api_request = "/api/" in path

        # Only redirect for HTML page requests, not API requests
        if not is_api_request and "text/html" in accept:
            # Redirect to Portal login with return URL to the current page
            from fastapi.responses import RedirectResponse
            from urllib.parse import quote
            redirect_path = f"/inventory{path}" if not path.startswith("/inventory") else path
            return RedirectResponse(url=f"/portal/login?redirect={quote(redirect_path)}", status_code=302)
    # For API requests or other errors, return JSON response
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files and templates
app.mount("/static", StaticFiles(directory="src/restaurant_inventory/static"), name="static")
templates = Jinja2Templates(directory="src/restaurant_inventory/templates")

# Include API routers
app.include_router(auth.router, prefix="/api/auth", tags=["authentication"])
app.include_router(locations.router, prefix="/api/locations", tags=["locations"])
app.include_router(storage_areas.router, prefix="/api/storage-areas", tags=["storage-areas"])
app.include_router(items.router, prefix="/api/items", tags=["master-items"])
app.include_router(inventory.router, prefix="/api/inventory", tags=["inventory"])
app.include_router(transfers.router, prefix="/api/transfers", tags=["transfers"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(roles.router, prefix="/api/roles", tags=["roles"])
app.include_router(audit_log.router, prefix="/api/audit-log", tags=["audit-log"])
app.include_router(count_templates.router, prefix="/api/count-templates", tags=["count-templates"])
app.include_router(count_sessions.router, prefix="/api/count-sessions", tags=["count-sessions"])
app.include_router(categories.router, prefix="/api/categories", tags=["categories"])
app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
app.include_router(vendors.router, prefix="/api/vendors", tags=["vendors"])
app.include_router(waste.router, prefix="/api/waste", tags=["waste"])
app.include_router(recipes.router, prefix="/api/recipes", tags=["recipes"])
app.include_router(pos.router, prefix="/api/pos", tags=["pos"])
app.include_router(units.router, prefix="/api/units", tags=["units"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(cache_management.router, prefix="/api/cache", tags=["cache"])
# Hub integration - source of truth for invoices and vendor items
app.include_router(hub_invoices.router, prefix="/api/hub-invoices", tags=["hub-invoices"])
app.include_router(hub_vendor_items.router, prefix="/api/hub-vendor-items", tags=["hub-vendor-items"])
# Order Sheets
app.include_router(order_sheet_templates.router, prefix="/api/order-sheet-templates", tags=["order-sheet-templates"])
app.include_router(order_sheets.router, prefix="/api/order-sheets", tags=["order-sheets"])
# REMOVED (Dec 25, 2025): /api/invoices, /api/vendor-items - Hub is source of truth


# Health check endpoint
@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Health check endpoint with database connectivity test"""
    try:
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"
    
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "database": db_status
    }

# Users endpoint (Admin only)
@app.get("/api/users", tags=["users"])
async def get_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Get all users from database (Admin only)"""
    try:
        users = db.query(User).all()
        return {
            "success": True,
            "count": len(users),
            "users": [
                {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "full_name": user.full_name,
                    "role": user.role.value if user.role else None,
                    "is_active": user.is_active,
                    "created_at": user.created_at.isoformat() if user.created_at else None
                }
                for user in users
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

# Simple locations endpoint for backward compatibility
@app.get("/api/locations", tags=["locations-simple"])
async def get_locations_simple(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all locations from database"""
    try:
        locations = db.query(Location).all()
        return {
            "success": True,
            "count": len(locations),
            "locations": [
                {
                    "id": loc.id,
                    "name": loc.name,
                    "address": loc.address,
                    "manager_name": loc.manager_name,
                    "is_active": loc.is_active
                }
                for loc in locations
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

# Redirect /api/items (no slash) to /api/items/ for consistency
# The full-featured endpoint is at /api/items/ (with trailing slash)
@app.get("/api/items", tags=["items-redirect"])
async def redirect_to_items():
    """Redirect to the proper items endpoint with trailing slash"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/api/items/", status_code=307)

# HTML Routes for Web Interface
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page redirect to dashboard"""
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page"""
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/setup-password", response_class=HTMLResponse)
async def setup_password_page(request: Request):
    """Password setup page for new user invitations"""
    return templates.TemplateResponse("setup_password.html", {"request": request})

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    """Dashboard page"""
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/locations", response_class=HTMLResponse)
async def locations_page(request: Request):
    """Locations management page"""
    return templates.TemplateResponse("locations.html", {"request": request})

@app.get("/items", response_class=HTMLResponse)
async def items_page(request: Request):
    """Items management page"""
    return templates.TemplateResponse("items.html", {"request": request})

@app.get("/transfers", response_class=HTMLResponse)
async def transfers_page(request: Request):
    """Transfers management page"""
    return templates.TemplateResponse("transfers.html", {"request": request})

@app.get("/invoices", response_class=HTMLResponse)
async def invoices_page(request: Request):
    """Invoices management page"""
    return templates.TemplateResponse("invoices.html", {"request": request})

@app.get("/hub-invoices", response_class=HTMLResponse)
async def hub_invoices_page(request: Request):
    """Hub Invoices page - view invoices from Integration Hub"""
    return templates.TemplateResponse("hub_invoices.html", {"request": request})

@app.get("/hub-invoices/{invoice_id}", response_class=HTMLResponse)
async def hub_invoice_detail_page(request: Request, invoice_id: int):
    """Hub Invoice detail page - view single invoice from Integration Hub"""
    return templates.TemplateResponse("hub_invoice_detail.html", {"request": request, "invoice_id": invoice_id})

@app.get("/storage-areas", response_class=HTMLResponse)
async def storage_areas_page(request: Request):
    """Storage areas management page"""
    return templates.TemplateResponse("storage_areas.html", {"request": request})

@app.get("/count", response_class=HTMLResponse)
async def count_session_page(request: Request):
    """Inventory count session page"""
    return templates.TemplateResponse("count_session_new.html", {"request": request})

@app.get("/count/history", response_class=HTMLResponse)
async def count_history_page(request: Request):
    """Inventory count history page"""
    return templates.TemplateResponse("count_history.html", {"request": request})

@app.get("/count/{session_id}/report", response_class=HTMLResponse)
async def count_session_report_page(
    request: Request,
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Printable report for a completed/approved count session"""
    from restaurant_inventory.models.count_session import CountSession, CountSessionItem, CountStatus
    from restaurant_inventory.models.master_item_location_cost import MasterItemLocationCost
    from restaurant_inventory.models.inventory import Inventory
    from restaurant_inventory.core.deps import get_user_location_ids
    from sqlalchemy.orm import joinedload
    from collections import OrderedDict
    from decimal import Decimal
    from datetime import datetime
    from zoneinfo import ZoneInfo

    session = db.query(CountSession).options(
        joinedload(CountSession.items).joinedload(CountSessionItem.master_item),
        joinedload(CountSession.items).joinedload(CountSessionItem.storage_area),
        joinedload(CountSession.items).joinedload(CountSessionItem.counted_by_user),
        joinedload(CountSession.location),
        joinedload(CountSession.started_by_user),
        joinedload(CountSession.completed_by_user),
        joinedload(CountSession.approved_by_user),
    ).filter(CountSession.id == session_id).first()

    if not session:
        raise HTTPException(status_code=404, detail="Count session not found")

    # Check location access
    location_ids = get_user_location_ids(current_user, db)
    if location_ids is not None and session.location_id not in location_ids:
        raise HTTPException(status_code=403, detail="No access to this location")

    if session.status not in (CountStatus.COMPLETED, CountStatus.APPROVED):
        raise HTTPException(status_code=400, detail="Report only available for completed or approved sessions")

    # Pre-load location costs for this location in one query
    cost_map = {}
    location_costs = db.query(MasterItemLocationCost).filter(
        MasterItemLocationCost.location_id == session.location_id
    ).all()
    for lc in location_costs:
        cost_map[lc.master_item_id] = float(lc.current_weighted_avg_cost) if lc.current_weighted_avg_cost else None

    # Pre-load Hub vendor item pricing as fallback for items without location costs
    hub_pricing = {}
    try:
        import os
        from sqlalchemy import create_engine, text as sa_text
        hub_db_url = os.getenv("HUB_DATABASE_URL")
        if hub_db_url:
            hub_engine = create_engine(hub_db_url)
            with hub_engine.connect() as conn:
                rows = conn.execute(sa_text("""
                    SELECT DISTINCT ON (inventory_master_item_id)
                        inventory_master_item_id,
                        CASE
                            WHEN case_cost IS NOT NULL AND pack_to_primary_factor IS NOT NULL AND pack_to_primary_factor > 0
                                THEN case_cost / pack_to_primary_factor
                            ELSE NULL
                        END as cost_per_unit
                    FROM hub_vendor_items
                    WHERE inventory_master_item_id IS NOT NULL
                      AND is_active = true
                      AND case_cost IS NOT NULL
                      AND pack_to_primary_factor IS NOT NULL AND pack_to_primary_factor > 0
                    ORDER BY inventory_master_item_id, is_preferred DESC, updated_at DESC
                """)).fetchall()
                for row in rows:
                    if row[1]:
                        hub_pricing[row[0]] = round(float(row[1]), 2)
            hub_engine.dispose()
    except Exception:
        pass  # Hub pricing is a best-effort fallback

    # Build item dicts with cost data
    all_items = []
    for item in session.items:
        # Cost lookup: location cost > hub vendor pricing > inventory unit_cost > deprecated master item cost
        unit_cost = cost_map.get(item.master_item_id)
        if unit_cost is None:
            unit_cost = hub_pricing.get(item.master_item_id)
        if unit_cost is None and item.inventory_id:
            inv = db.query(Inventory).filter(Inventory.id == item.inventory_id).first()
            if inv and inv.unit_cost:
                unit_cost = float(inv.unit_cost)
        if unit_cost is None and item.master_item and item.master_item.current_cost:
            unit_cost = float(item.master_item.current_cost)

        counted_qty = float(item.counted_quantity) if item.counted_quantity is not None else None
        extended_value = (counted_qty * unit_cost) if counted_qty is not None and unit_cost else None

        # Get unit display: prefer primary_uom_abbr, fall back to deprecated unit relation
        unit_display = None
        if item.master_item:
            unit_display = item.master_item.primary_uom_abbr or (
                item.master_item.unit.name if item.master_item.unit else None
            )

        all_items.append({
            'item_name': item.master_item.name if item.master_item else 'Unknown',
            'category': item.master_item.category if item.master_item else 'Other',
            'storage_area_name': item.storage_area.name if item.storage_area else 'Unassigned',
            'unit': unit_display,
            'counted_qty': counted_qty,
            'unit_cost': unit_cost,
            'extended_value': extended_value,
            'is_new': item.is_new_item,
        })

    # Group by storage area
    by_storage_area = {}
    for itm in sorted(all_items, key=lambda x: (x['storage_area_name'], x['category'] or '', x['item_name'])):
        area = itm['storage_area_name']
        if area not in by_storage_area:
            by_storage_area[area] = {'items': [], 'subtotal_value': 0.0, 'subtotal_counted': 0.0}
        by_storage_area[area]['items'].append(itm)
        if itm['extended_value'] is not None:
            by_storage_area[area]['subtotal_value'] += itm['extended_value']
        if itm['counted_qty'] is not None:
            by_storage_area[area]['subtotal_counted'] += itm['counted_qty']

    # Group by category
    by_category = {}
    for itm in sorted(all_items, key=lambda x: (x['category'] or 'Other', x['item_name'])):
        cat = itm['category'] or 'Other'
        if cat not in by_category:
            by_category[cat] = {'items': [], 'subtotal_value': 0.0, 'subtotal_counted': 0.0}
        by_category[cat]['items'].append(itm)
        if itm['extended_value'] is not None:
            by_category[cat]['subtotal_value'] += itm['extended_value']
        if itm['counted_qty'] is not None:
            by_category[cat]['subtotal_counted'] += itm['counted_qty']

    # Summary calculations
    total_items = len(all_items)
    counted_items = sum(1 for i in all_items if i['counted_qty'] is not None)
    total_counted_value = sum(i['extended_value'] for i in all_items if i['extended_value'] is not None)
    total_counted_qty = sum(i['counted_qty'] for i in all_items if i['counted_qty'] is not None)

    # Session data dict for template
    session_data = {
        'id': session.id,
        'name': session.name,
        'location_name': session.location.name if session.location else '',
        'inventory_type': session.inventory_type.value if session.inventory_type else 'PARTIAL',
        'status': session.status.value,
        'notes': session.notes,
        'started_at': session.started_at,
        'completed_at': session.completed_at,
        'approved_at': session.approved_at,
        'started_by_name': session.started_by_user.username if session.started_by_user else None,
        'completed_by_name': session.completed_by_user.username if session.completed_by_user else None,
        'approved_by_name': session.approved_by_user.username if session.approved_by_user else None,
    }

    _ET = ZoneInfo("America/New_York")

    return templates.TemplateResponse("count_session_report.html", {
        "request": request,
        "session": session_data,
        "summary": {
            "total_items": total_items,
            "counted_items": counted_items,
            "total_counted_value": total_counted_value,
            "total_counted_qty": total_counted_qty,
            "storage_areas": len(by_storage_area),
            "categories": len(by_category),
        },
        "by_storage_area": by_storage_area,
        "sorted_areas": sorted(by_storage_area.keys()),
        "by_category": by_category,
        "sorted_categories": sorted(by_category.keys()),
        "now": datetime.now(_ET),
    })

@app.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request):
    """Reports page"""
    return templates.TemplateResponse("reports.html", {"request": request})

@app.get("/analytics", response_class=HTMLResponse)
async def analytics_page(request: Request):
    """Analytics dashboard page"""
    return templates.TemplateResponse("analytics.html", {"request": request})

@app.get("/templates", response_class=HTMLResponse)
async def templates_page(request: Request):
    """Count templates management page"""
    return templates.TemplateResponse("templates_management.html", {"request": request})

@app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request):
    """User management page (Admin only)"""
    return templates.TemplateResponse("users.html", {"request": request})

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Settings page with Users, Locations, and Items (Admin only)"""
    return templates.TemplateResponse("settings.html", {"request": request})

@app.get("/pos-item-mapping", response_class=HTMLResponse)
async def pos_item_mapping_page(request: Request):
    """POS Item Mapping page"""
    return templates.TemplateResponse("pos_item_mapping.html", {"request": request})

@app.get("/inventory-movements", response_class=HTMLResponse)
async def inventory_movements_page(request: Request):
    """Inventory Movements/Transactions page"""
    return templates.TemplateResponse("inventory_movements.html", {"request": request})

@app.get("/categories", response_class=HTMLResponse)
async def categories_page(request: Request):
    """Categories management page"""
    return templates.TemplateResponse("categories.html", {"request": request})

@app.get("/master-items", response_class=HTMLResponse)
async def master_items_page(request: Request):
    """Master Items management page"""
    return templates.TemplateResponse("master_items.html", {"request": request})

@app.get("/item-detail", response_class=HTMLResponse)
async def item_detail_page(request: Request):
    """Item detail page - unified view of master item with all vendors and details"""
    return templates.TemplateResponse("item_detail.html", {"request": request})

@app.get("/vendor-items", response_class=HTMLResponse)
async def vendor_items_page(request: Request):
    """Vendor Items management page"""
    return templates.TemplateResponse("vendor_items.html", {"request": request})

@app.get("/vendors", response_class=HTMLResponse)
async def vendors_page(request: Request):
    """Vendors management page"""
    return templates.TemplateResponse("vendors.html", {"request": request})

@app.get("/order-sheets", response_class=HTMLResponse)
async def order_sheets_page(request: Request):
    """Order Sheets page"""
    return templates.TemplateResponse("order_sheets.html", {"request": request})

@app.get("/order-sheets/templates", response_class=HTMLResponse)
async def order_sheet_templates_page(request: Request):
    """Order Sheet Templates management page"""
    return templates.TemplateResponse("order_sheet_templates.html", {"request": request})

@app.get("/order-sheets/{sheet_id}/fill", response_class=HTMLResponse)
async def order_sheet_fill_page(request: Request, sheet_id: int):
    """Fill out an order sheet"""
    return templates.TemplateResponse("order_sheet_fill.html", {"request": request, "sheet_id": sheet_id})

@app.get("/order-sheets/{sheet_id}/print", response_class=HTMLResponse)
async def order_sheet_print_page(
    request: Request,
    sheet_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Printable view of an order sheet (non-API route for proper auth redirect)"""
    from restaurant_inventory.models.order_sheet import OrderSheet, OrderSheetItem, OrderSheetStatus
    from restaurant_inventory.models.order_sheet_template import OrderSheetTemplate
    from restaurant_inventory.models.location import Location
    from restaurant_inventory.core.deps import get_user_location_ids
    from sqlalchemy.orm import joinedload

    sheet = db.query(OrderSheet).options(
        joinedload(OrderSheet.items),
        joinedload(OrderSheet.template),
        joinedload(OrderSheet.location),
        joinedload(OrderSheet.created_by_user)
    ).filter(OrderSheet.id == sheet_id).first()

    if not sheet:
        raise HTTPException(status_code=404, detail="Order sheet not found")

    location_ids = get_user_location_ids(current_user, db)
    if location_ids is not None and sheet.location_id not in location_ids:
        raise HTTPException(status_code=403, detail="No access to this location")

    # Build response data
    from restaurant_inventory.api.api_v1.endpoints.order_sheets import _build_sheet_response
    response = _build_sheet_response(sheet)

    # Group items by category
    categories = {}
    for item in response.items:
        cat = item.item_category or 'Other'
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(item)

    return templates.TemplateResponse("order_sheet_print.html", {
        "request": request,
        "sheet": response,
        "categories": categories,
        "sorted_categories": sorted(categories.keys())
    })

@app.get("/units-of-measure", response_class=HTMLResponse)
async def units_of_measure_page(request: Request):
    """Units of Measure - DEPRECATED: Redirect to Hub (source of truth for UoMs)"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/hub/vendor-items", status_code=302)

@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request):
    """User profile page"""
    return templates.TemplateResponse("profile.html", {"request": request})

@app.get("/waste", response_class=HTMLResponse)
async def waste_page(request: Request):
    """Waste log page"""
    import time
    return templates.TemplateResponse("waste.html", {"request": request, "cache_bust": int(time.time())})

@app.get("/recipes", response_class=HTMLResponse)
async def recipes_page(request: Request):
    """Recipes page"""
    return templates.TemplateResponse("recipes.html", {"request": request})

@app.get("/pos-config", response_class=HTMLResponse)
async def pos_config_page(request: Request):
    """POS Configuration page"""
    return templates.TemplateResponse("pos_config.html", {"request": request})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
