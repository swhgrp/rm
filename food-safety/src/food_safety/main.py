"""Main FastAPI application for Safety & Compliance Service"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from food_safety.config import settings
from food_safety.database import init_db
from food_safety.routers import (
    auth, dashboard, users, locations, temperatures,
    checklists, incidents, inspections, haccp, reports
)

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    logger.info("Starting Safety & Compliance Service...")
    # Initialize database tables if needed
    await init_db()
    logger.info("Safety & Compliance Service started successfully")
    yield
    logger.info("Shutting down Safety & Compliance Service...")


app = FastAPI(
    title="Safety & Compliance Service",
    description="Service for managing safety compliance, temperature monitoring, checklists, inspections, and incident reporting",
    version="1.0.0",
    lifespan=lifespan,
    root_path="/food-safety",
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
app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
app.include_router(users.router, prefix="/users", tags=["Users & Permissions"])
app.include_router(locations.router, prefix="/locations", tags=["Locations & Equipment"])
app.include_router(temperatures.router, prefix="/temperatures", tags=["Temperature Logging"])
app.include_router(checklists.router, prefix="/checklists", tags=["Checklists"])
app.include_router(incidents.router, prefix="/incidents", tags=["Incidents"])
app.include_router(inspections.router, prefix="/inspections", tags=["Inspections"])
app.include_router(haccp.router, prefix="/haccp", tags=["HACCP"])
app.include_router(reports.router, prefix="/reports", tags=["Reports"])


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "safety-compliance"}


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Safety & Compliance Service",
        "version": "1.0.0",
        "docs": "/food-safety/docs"
    }
