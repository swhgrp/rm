"""
Nextcloud Integration Service - Main Application

A microservice for integrating Nextcloud file and calendar functionality
into the SW Restaurant Management System.
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

from nextcloud.core.config import settings
from nextcloud.api.v1.endpoints import auth, files, calendar

# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Nextcloud integration for files and calendar management",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    openapi_url="/api/v1/openapi.json"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="src/nextcloud/static"), name="static")

# Templates
templates = Jinja2Templates(directory="src/nextcloud/templates")

# Include API routers - SSO auth without /v1 for compatibility
app.include_router(
    auth.router,
    prefix="/api/auth",
    tags=["Authentication"]
)

# V1 API routers
app.include_router(
    files.router,
    prefix="/api/v1/files",
    tags=["Files"]
)

app.include_router(
    calendar.router,
    prefix="/api/v1/calendar",
    tags=["Calendar"]
)


# Frontend routes
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Nextcloud service landing page"""
    return templates.TemplateResponse(
        "index.html",
        {"request": request}
    )


@app.get("/files", response_class=HTMLResponse)
async def files_page(request: Request):
    """Files browser page"""
    return templates.TemplateResponse(
        "files.html",
        {"request": request}
    )


@app.get("/calendar", response_class=HTMLResponse)
async def calendar_page(request: Request):
    """Calendar view page"""
    return templates.TemplateResponse(
        "calendar.html",
        {"request": request}
    )


@app.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request):
    """Nextcloud credentials setup page"""
    return templates.TemplateResponse(
        "setup.html",
        {"request": request}
    )


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "nextcloud",
        "version": settings.APP_VERSION
    }


# Startup event
@app.on_event("startup")
async def startup_event():
    """Application startup"""
    print(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} starting...")
    print(f"📁 Nextcloud URL: {settings.NEXTCLOUD_URL}")
    print(f"🔒 Debug mode: {settings.DEBUG}")


# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown"""
    print(f"👋 {settings.APP_NAME} shutting down...")
