"""
Restaurant Accounting System - Main Application
"""
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text

from accounting.core.config import settings
from accounting.db.database import get_db

# Initialize FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Restaurant Accounting System - Separate microservice for financial management"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
        "status": "healthy" if settings.ACCOUNTING_ENABLED else "disabled",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "database": db_status,
        "accounting_enabled": settings.ACCOUNTING_ENABLED,
        "auto_sync_enabled": settings.AUTO_SYNC_ENABLED
    }

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running" if settings.ACCOUNTING_ENABLED else "disabled",
        "docs": "/docs",
        "health": "/health"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
