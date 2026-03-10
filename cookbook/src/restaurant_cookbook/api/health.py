"""Health check endpoint for monitoring integration."""

import time
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text, func

from restaurant_cookbook.core.deps import get_db
from restaurant_cookbook.core.config import settings
from restaurant_cookbook.models.book import Book

router = APIRouter()

_start_time = time.time()


@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    """Health check — no auth required. Matches monitoring portal format."""
    # Database check
    try:
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"

    # ChromaDB check
    try:
        from restaurant_cookbook.services.chroma_client import get_chroma_service
        chroma_svc = get_chroma_service()
        chroma_healthy = chroma_svc.is_healthy()
        chroma_status = "connected" if chroma_healthy else "error"
        chroma_count = chroma_svc.count()
    except Exception:
        chroma_status = "not initialized"
        chroma_count = 0

    # Book count
    try:
        book_count = db.query(func.count(Book.id)).scalar()
    except Exception:
        book_count = 0

    uptime = int(time.time() - _start_time)

    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "service": "Cookbook",
        "version": settings.APP_VERSION,
        "uptime": uptime,
        "database": db_status,
        "chroma": chroma_status,
        "chroma_documents": chroma_count,
        "book_count": book_count,
    }
