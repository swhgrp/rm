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
from restaurant_inventory.api.api_v1.endpoints import invoices
from restaurant_inventory.api.api_v1.endpoints import waste
from restaurant_inventory.api.api_v1.endpoints import recipes
from restaurant_inventory.api.api_v1.endpoints import pos
from restaurant_inventory.api.api_v1.endpoints import units
from restaurant_inventory.api.api_v1.endpoints import dashboard
from restaurant_inventory.api.api_v1.endpoints import vendor_items
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
    description="Multi-location restaurant inventory management system"
)

# Register startup and shutdown events
app.add_event_handler("startup", startup_event_handler)
app.add_event_handler("shutdown", shutdown_event_handler)

# Add rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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
app.include_router(invoices.router, prefix="/api/invoices", tags=["invoices"])
app.include_router(waste.router, prefix="/api/waste", tags=["waste"])
app.include_router(recipes.router, prefix="/api/recipes", tags=["recipes"])
app.include_router(pos.router, prefix="/api/pos", tags=["pos"])
app.include_router(units.router, prefix="/api/units", tags=["units"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(vendor_items.router, prefix="/api/vendor-items", tags=["vendor-items"])


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

# Simple items endpoint for backward compatibility
@app.get("/api/items", tags=["items-simple"])
async def get_master_items_simple(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all master items from database"""
    try:
        items = db.query(MasterItem).all()
        return {
            "success": True,
            "count": len(items),
            "items": [
                {
                    "id": item.id,
                    "name": item.name,
                    "description": item.description,
                    "category": item.category,
                    "unit_of_measure": item.unit_of_measure,
                    "current_cost": float(item.current_cost) if item.current_cost else None,
                    "average_cost": float(item.average_cost) if item.average_cost else None,
                    "sku": item.sku,
                    "vendor": item.vendor,
                    "par_level": float(item.par_level) if item.par_level else None,
                    "is_active": item.is_active,
                    "created_at": item.created_at.isoformat() if item.created_at else None
                }
                for item in items
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

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

@app.get("/storage-areas", response_class=HTMLResponse)
async def storage_areas_page(request: Request):
    """Storage areas management page"""
    return templates.TemplateResponse("inventory.html", {"request": request})

@app.get("/inventory/count", response_class=HTMLResponse)
async def count_session_page(request: Request):
    """Inventory count session page"""
    return templates.TemplateResponse("count_session_new.html", {"request": request})

@app.get("/inventory/count/history", response_class=HTMLResponse)
async def count_history_page(request: Request):
    """Inventory count history page"""
    return templates.TemplateResponse("count_history.html", {"request": request})

@app.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request):
    """Reports page"""
    return templates.TemplateResponse("reports.html", {"request": request})

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

@app.get("/master-items", response_class=HTMLResponse)
async def master_items_page(request: Request):
    """Master Items management page"""
    return templates.TemplateResponse("master_items.html", {"request": request})

@app.get("/vendor-items", response_class=HTMLResponse)
async def vendor_items_page(request: Request):
    """Vendor Items management page"""
    return templates.TemplateResponse("vendor_items.html", {"request": request})

@app.get("/vendors", response_class=HTMLResponse)
async def vendors_page(request: Request):
    """Vendors management page"""
    return templates.TemplateResponse("vendors.html", {"request": request})

@app.get("/units-of-measure", response_class=HTMLResponse)
async def units_of_measure_page(request: Request):
    """Units of Measure management page"""
    return templates.TemplateResponse("units_of_measure.html", {"request": request})

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
