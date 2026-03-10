"""Book management API endpoints."""

import os
import shutil
import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import Optional

from restaurant_cookbook.core.deps import get_db, get_current_user
from restaurant_cookbook.core.config import settings
from restaurant_cookbook.models.book import Book
from restaurant_cookbook.models.user import User
from restaurant_cookbook.services.pdf_processor import process_book_background

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/upload")
def upload_book(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    author: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload a PDF cookbook for processing."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    # Check file size
    file.file.seek(0, 2)
    size_mb = file.file.tell() / (1024 * 1024)
    file.file.seek(0)

    if size_mb > settings.MAX_UPLOAD_SIZE_MB:
        raise HTTPException(
            status_code=400,
            detail=f"File too large ({size_mb:.1f}MB). Maximum is {settings.MAX_UPLOAD_SIZE_MB}MB",
        )

    # Save file
    os.makedirs(settings.UPLOAD_PATH, exist_ok=True)
    safe_name = file.filename.replace(" ", "_")
    file_path = os.path.join(settings.UPLOAD_PATH, safe_name)

    # Handle duplicate filenames
    base, ext = os.path.splitext(file_path)
    counter = 1
    while os.path.exists(file_path):
        file_path = f"{base}_{counter}{ext}"
        counter += 1

    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Create book record
    book = Book(
        title=title or os.path.splitext(file.filename)[0],
        author=author or "",
        filename=file.filename,
        file_path=file_path,
        status="pending",
        uploaded_by=current_user.id,
    )
    db.add(book)
    db.commit()
    db.refresh(book)

    # Start background processing
    process_book_background(book.id)

    return {
        "id": book.id,
        "title": book.title,
        "status": book.status,
        "message": "Upload successful. Processing started.",
    }


@router.get("")
def list_books(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all uploaded books."""
    books = db.query(Book).order_by(Book.uploaded_at.desc()).all()
    return [
        {
            "id": b.id,
            "title": b.title,
            "author": b.author,
            "filename": b.filename,
            "page_count": b.page_count,
            "chunk_count": b.chunk_count,
            "status": b.status,
            "error_message": b.error_message,
            "uploaded_at": b.uploaded_at.isoformat() if b.uploaded_at else None,
            "processed_at": b.processed_at.isoformat() if b.processed_at else None,
        }
        for b in books
    ]


@router.get("/{book_id}/status")
def book_status(
    book_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get processing status for a book."""
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return {
        "id": book.id,
        "status": book.status,
        "chunk_count": book.chunk_count,
        "page_count": book.page_count,
        "error_message": book.error_message,
    }


@router.delete("/{book_id}")
def delete_book(
    book_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a book, its chunks, vectors, and PDF file."""
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    # Delete from ChromaDB
    try:
        from restaurant_cookbook.services.chroma_client import get_chroma_service
        chroma_svc = get_chroma_service()
        chroma_svc.delete_book(book_id)
    except Exception as e:
        logger.warning(f"Error deleting ChromaDB vectors for book {book_id}: {e}")

    # Delete PDF file
    if book.file_path and os.path.exists(book.file_path):
        os.remove(book.file_path)

    # Delete book (cascades to chunks)
    db.delete(book)
    db.commit()

    return {"message": f"Book '{book.title}' deleted successfully"}
