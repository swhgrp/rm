"""Main FastAPI application for Maintenance & Equipment Tracking Service"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from maintenance.config import settings
from maintenance.database import init_db
from maintenance.routers import equipment, categories, schedules, work_orders, vendors, dashboard

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    logger.info("Starting Maintenance Service...")
    # Initialize database tables if needed
    await init_db()
    logger.info("Maintenance Service started successfully")
    yield
    logger.info("Shutting down Maintenance Service...")


app = FastAPI(
    title="Maintenance & Equipment Tracking Service",
    description="Service for tracking equipment, maintenance schedules, and work orders",
    version="1.0.0",
    lifespan=lifespan,
    root_path="/maintenance",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


# Include routers
app.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
app.include_router(equipment.router, prefix="/equipment", tags=["Equipment"])
app.include_router(categories.router, prefix="/categories", tags=["Categories"])
app.include_router(schedules.router, prefix="/schedules", tags=["Maintenance Schedules"])
app.include_router(work_orders.router, prefix="/work-orders", tags=["Work Orders"])
app.include_router(vendors.router, prefix="/vendors", tags=["Vendors"])


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "maintenance"}


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Maintenance & Equipment Tracking Service",
        "version": "1.0.0",
        "docs": "/maintenance/docs"
    }
