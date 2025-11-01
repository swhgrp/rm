"""Main FastAPI application"""
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
import logging
import os
import sys

# Add shared directory to path for Sentry config
# sys.path.insert(0, '/opt/restaurant-system/shared/python')
# from sentry_config import init_sentry
# Initialize Sentry error tracking
# init_sentry("events")

from events.core.config import settings
from events.core.deps import require_auth
from events.api import public, events, tasks, documents, auth, settings as settings_api, packages

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get the templates directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

app = FastAPI(
    title=settings.APP_NAME,
    description="Event Planning System with Calendar, Tasks, Documents, and Email Notifications",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    # NO root_path - Nginx strips /events/ before forwarding
    redirect_slashes=False,  # Disable automatic trailing slash redirects
)

# Middleware to handle proxy headers
class ProxyHeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Trust X-Forwarded-Proto from nginx proxy
        forwarded_proto = request.headers.get("X-Forwarded-Proto")
        if forwarded_proto:
            request.scope["scheme"] = forwarded_proto

        response = await call_next(request)
        return response

app.add_middleware(ProxyHeaderMiddleware)

# Custom exception handler for authentication redirects
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions - redirect 401 to Portal login for HTML requests"""
    if exc.status_code == 401:  # HTTP_401_UNAUTHORIZED
        # Check if this is an HTML request (not API)
        accept = request.headers.get("accept", "")
        if "text/html" in accept or str(request.url.path).startswith(("/", "/calendar", "/tasks", "/settings", "/list", "/event")):
            # Redirect to Portal login
            from fastapi.responses import RedirectResponse
            return RedirectResponse(url="/portal/login?redirect=/events/", status_code=302)

    # For API requests or other errors, return JSON response
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.DEBUG else [settings.APP_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "events"}

# Public intake form page (standalone, no base template)
@app.get("/public/intake", response_class=HTMLResponse)
async def public_intake_form():
    """Serve the public event intake form"""
    form_path = os.path.join(BASE_DIR, "templates", "public", "intake_form.html")
    with open(form_path, "r") as f:
        return f.read()

# Calendar page
@app.get("/calendar", response_class=HTMLResponse)
async def calendar_page(request: Request, current_user=Depends(require_auth)):
    """Serve the event calendar page"""
    return templates.TemplateResponse("admin/calendar.html", {
        "request": request,
        "user": current_user
    })

# Tasks page
@app.get("/tasks", response_class=HTMLResponse)
async def tasks_page(request: Request, current_user=Depends(require_auth)):
    """Serve the task management page"""
    return templates.TemplateResponse("admin/tasks.html", {
        "request": request,
        "user": current_user
    })

# Settings page
@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, current_user=Depends(require_auth)):
    """Serve the settings page"""
    return templates.TemplateResponse("admin/settings.html", {
        "request": request,
        "user": current_user
    })

# Packages page
@app.get("/packages", response_class=HTMLResponse)
async def packages_page(request: Request, current_user=Depends(require_auth)):
    """Serve the event packages management page"""
    return templates.TemplateResponse("admin/packages.html", {
        "request": request,
        "user": current_user
    })

# Events list page
@app.get("/list", response_class=HTMLResponse)
async def events_list_page(request: Request, current_user=Depends(require_auth)):
    """Serve the events list/dashboard page"""
    return templates.TemplateResponse("admin/events_list.html", {
        "request": request,
        "user": current_user
    })

# Event detail page
@app.get("/event", response_class=HTMLResponse)
async def event_detail_page(request: Request, current_user=Depends(require_auth)):
    """Serve the event detail/edit page"""
    return templates.TemplateResponse("admin/event_detail.html", {
        "request": request,
        "user": current_user
    })

# Include API routers
app.include_router(auth.router, tags=["Authentication"])
app.include_router(public.router, prefix="/public", tags=["Public"])
app.include_router(events.router, prefix="/api/events", tags=["Events"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["Tasks"])
app.include_router(documents.router, prefix="/api/documents", tags=["Documents"])
app.include_router(packages.router, prefix="/api/packages", tags=["Packages"])
app.include_router(settings_api.router, prefix="/api/settings", tags=["Settings"])

# Mount static files AFTER routers (matching HR pattern)
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    logger.info(f"Static files mounted at /static from {STATIC_DIR}")

# Catch-all routes for pages
@app.get("/", response_class=HTMLResponse)
async def root(request: Request, current_user=Depends(require_auth)):
    """Dashboard - main landing page (auth required)"""
    return templates.TemplateResponse("admin/dashboard.html", {
        "request": request,
        "user": current_user
    })

@app.on_event("startup")
async def startup_event():
    """Log startup"""
    logger.info("=" * 60)
    logger.info(f"Starting {settings.APP_NAME}")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Debug Mode: {settings.DEBUG}")
    logger.info("=" * 60)
