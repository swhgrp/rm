"""PDF processing service — extracts text, chunks it, and triggers embedding."""

import os
import logging
import threading
from datetime import datetime
from typing import List, Tuple
from zoneinfo import ZoneInfo

import pdfplumber

from restaurant_cookbook.core.config import settings
from restaurant_cookbook.db.database import SessionLocal
from restaurant_cookbook.models.book import Book
from restaurant_cookbook.models.chunk import Chunk

logger = logging.getLogger(__name__)
_ET = ZoneInfo("America/New_York")


def _extract_text_pdfplumber(file_path: str) -> List[Tuple[int, str]]:
    """Extract text page-by-page using pdfplumber. Returns [(page_num, text), ...]."""
    pages = []
    with pdfplumber.open(file_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text()
            if text and text.strip():
                pages.append((i, text.strip()))
    return pages


def _extract_text_ocr(file_path: str) -> List[Tuple[int, str]]:
    """OCR fallback using pytesseract for scanned/image-based PDFs."""
    try:
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError:
        logger.warning("pytesseract or pdf2image not available for OCR fallback")
        return []

    pages = []
    images = convert_from_path(file_path, dpi=300)
    for i, img in enumerate(images, start=1):
        text = pytesseract.image_to_string(img)
        if text and text.strip():
            pages.append((i, text.strip()))
    return pages


def _chunk_text(
    pages: List[Tuple[int, str]], chunk_size: int, chunk_overlap: int
) -> List[dict]:
    """Split page text into overlapping chunks."""
    chunks = []
    chunk_index = 0

    for page_num, page_text in pages:
        words = page_text.split()
        start = 0
        while start < len(words):
            end = start + chunk_size
            chunk_words = words[start:end]
            content = " ".join(chunk_words)

            if len(content.strip()) > 20:  # Skip tiny fragments
                chunks.append(
                    {
                        "content": content,
                        "page_number": page_num,
                        "chunk_index": chunk_index,
                    }
                )
                chunk_index += 1

            start += chunk_size - chunk_overlap
            if start >= len(words):
                break

    return chunks


def process_book_background(book_id: int):
    """Run PDF processing in a background thread."""
    thread = threading.Thread(target=_process_book, args=(book_id,), daemon=True)
    thread.start()


def _process_book(book_id: int):
    """Full processing pipeline: extract → chunk → embed → store."""
    db = SessionLocal()
    try:
        book = db.query(Book).filter(Book.id == book_id).first()
        if not book:
            logger.error(f"Book {book_id} not found")
            return

        # Update status to processing
        book.status = "processing"
        db.commit()

        # Step 1: Extract text
        logger.info(f"Extracting text from: {book.filename}")
        pages = _extract_text_pdfplumber(book.file_path)

        # Fallback to OCR if no text extracted
        if not pages:
            logger.info(f"No text extracted, trying OCR for: {book.filename}")
            pages = _extract_text_ocr(book.file_path)

        if not pages:
            book.status = "error"
            book.error_message = "No text could be extracted from this PDF"
            db.commit()
            return

        book.page_count = max(p[0] for p in pages)

        # Step 2: Chunk the text
        logger.info(f"Chunking text from {len(pages)} pages")
        chunk_dicts = _chunk_text(pages, settings.CHUNK_SIZE, settings.CHUNK_OVERLAP)

        if not chunk_dicts:
            book.status = "error"
            book.error_message = "Text extracted but no viable chunks created"
            db.commit()
            return

        # Step 3: Store chunks in DB
        db_chunks = []
        for cd in chunk_dicts:
            chunk = Chunk(
                book_id=book.id,
                content=cd["content"],
                page_number=cd["page_number"],
                chunk_index=cd["chunk_index"],
            )
            db.add(chunk)
            db_chunks.append(chunk)

        db.flush()  # Get chunk IDs

        # Step 4: Generate embeddings and store in ChromaDB
        try:
            from restaurant_cookbook.services.embeddings import get_embedding_service
            from restaurant_cookbook.services.chroma_client import get_chroma_service

            embed_svc = get_embedding_service()
            chroma_svc = get_chroma_service()

            texts = [c.content for c in db_chunks]
            embeddings = embed_svc.embed_texts(texts)

            ids = []
            metadatas = []
            for chunk in db_chunks:
                doc_id = f"book_{book.id}_chunk_{chunk.chunk_index}"
                chunk.embedding_id = doc_id
                ids.append(doc_id)
                metadatas.append(
                    {
                        "book_id": book.id,
                        "book_title": book.title,
                        "page_number": chunk.page_number or 0,
                        "chunk_index": chunk.chunk_index,
                    }
                )

            chroma_svc.add_documents(
                ids=ids,
                documents=texts,
                embeddings=embeddings,
                metadatas=metadatas,
            )

            logger.info(f"Stored {len(ids)} embeddings in ChromaDB for book {book.id}")

        except Exception as e:
            logger.error(f"Embedding/ChromaDB error for book {book.id}: {e}")
            book.status = "error"
            book.error_message = f"Text extracted but embedding failed: {str(e)}"
            db.commit()
            return

        # Step 5: Update book status
        book.chunk_count = len(db_chunks)
        book.status = "ready"
        book.processed_at = datetime.now(_ET)
        db.commit()

        logger.info(
            f"Book '{book.title}' processed: {book.page_count} pages, {book.chunk_count} chunks"
        )

    except Exception as e:
        logger.error(f"Error processing book {book_id}: {e}")
        try:
            book = db.query(Book).filter(Book.id == book_id).first()
            if book:
                book.status = "error"
                book.error_message = str(e)[:500]
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
