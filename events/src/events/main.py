"""Main FastAPI application"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from events.core.config import settings
from events.api import public, events, tasks, documents, auth
import logging
import os

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
    root_path="/events",  # Behind reverse proxy at /events/ path
)

# Middleware to handle proxy headers (X-Forwarded-Proto, X-Forwarded-Host)
class ProxyHeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Trust X-Forwarded-Proto from nginx proxy
        forwarded_proto = request.headers.get("X-Forwarded-Proto")
        if forwarded_proto:
            request.scope["scheme"] = forwarded_proto
        response = await call_next(request)
        return response

app.add_middleware(ProxyHeaderMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.DEBUG else [settings.APP_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
# app.mount("/static", StaticFiles(directory="src/events/static"), name="static")

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
async def calendar_page(request: Request):
    """Serve the event calendar page"""
    return templates.TemplateResponse("admin/calendar.html", {"request": request})

# Tasks page
@app.get("/tasks", response_class=HTMLResponse)
async def tasks_page(request: Request):
    """Serve the task management page"""
    return templates.TemplateResponse("admin/tasks.html", {"request": request})

# Events list page
@app.get("/events", response_class=HTMLResponse)
async def events_list_page(request: Request):
    """Serve the events list/dashboard page"""
    return templates.TemplateResponse("admin/events_list.html", {"request": request})

# Event detail page
@app.get("/event", response_class=HTMLResponse)
async def event_detail_page(request: Request):
    """Serve the event detail/edit page"""
    return templates.TemplateResponse("admin/event_detail.html", {"request": request})

# Include API routers
app.include_router(auth.router, tags=["Authentication"])
app.include_router(public.router, prefix="/public", tags=["Public"])
app.include_router(events.router, prefix="/api/events", tags=["Events"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["Tasks"])
app.include_router(documents.router, prefix="/api/documents", tags=["Documents"])

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Dashboard - main landing page (session auth checked by JS)"""
    return templates.TemplateResponse("admin/dashboard.html", {"request": request})

@app.on_event("startup")
async def startup_event():
    """Log startup"""
    logger.info("=" * 60)
    logger.info(f"Starting {settings.APP_NAME}")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Debug Mode: {settings.DEBUG}")
    logger.info("=" * 60)
