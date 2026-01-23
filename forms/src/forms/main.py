"""Main FastAPI application for Forms Service"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from forms.config import settings
from forms.database import init_db

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Base directory for templates and static files
BASE_DIR = Path(__file__).resolve().parent.parent.parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    logger.info("Starting Forms Service...")
    # Initialize database tables if needed
    await init_db()
    # Start background scheduler
    from forms.services.scheduler import start_scheduler, stop_scheduler
    start_scheduler()
    logger.info("Forms Service started successfully")
    yield
    logger.info("Shutting down Forms Service...")
    stop_scheduler()


app = FastAPI(
    title="Forms Service",
    description="Digital forms management for SW Hospitality Group",
    version="1.0.0",
    lifespan=lifespan,
    root_path="/forms",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
static_path = BASE_DIR / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

# Templates
templates_path = BASE_DIR / "templates"
templates = Jinja2Templates(directory=str(templates_path)) if templates_path.exists() else None


# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


# Include routers
from forms.routers import templates as templates_router
from forms.routers import submissions, signatures, workflows, attachments, dashboard, reports, pages, settings

# API routers
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])
app.include_router(templates_router.router, prefix="/api/templates", tags=["Templates"])
app.include_router(submissions.router, prefix="/api/submissions", tags=["Submissions"])
app.include_router(signatures.router, prefix="/api/signatures", tags=["Signatures"])
app.include_router(workflows.router, prefix="/api/workflows", tags=["Workflows"])
app.include_router(attachments.router, prefix="/api/attachments", tags=["Attachments"])
app.include_router(reports.router, prefix="/api/reports", tags=["Reports"])
app.include_router(settings.router, tags=["Settings"])

# HTML page routes (must be last to not conflict with API routes)
app.include_router(pages.router, tags=["Pages"])


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "forms"}
