"""
Restaurant Accounting System - Main Application
"""
from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import text
from pathlib import Path

from accounting.core.config import settings
from accounting.db.database import get_db
from accounting.api.accounts import router as accounts_router
from accounting.api.journal_entries import router as journal_entries_router
from accounting.api.fiscal_periods import router as fiscal_periods_router
# Import all models to ensure they are registered
import accounting.models  # noqa

# Initialize FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Restaurant Accounting System - Separate microservice for financial management"
)

# Setup templates and static files
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/accounting/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(accounts_router)
app.include_router(journal_entries_router)
app.include_router(fiscal_periods_router)

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

# Frontend Pages
@app.get("/accounts")
async def accounts_page(request: Request):
    """Chart of Accounts page"""
    return templates.TemplateResponse("chart_of_accounts.html", {"request": request})

@app.get("/journal-entries")
async def journal_entries_page(request: Request):
    """Journal Entries page"""
    return templates.TemplateResponse("journal_entries.html", {"request": request})

@app.get("/periods")
async def periods_page(request: Request):
    """Fiscal Periods page"""
    return templates.TemplateResponse("fiscal_periods.html", {"request": request})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
