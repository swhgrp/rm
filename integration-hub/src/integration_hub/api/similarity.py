"""
Similarity Search API Endpoints

Provides AI-powered semantic search for finding similar vendor items
using OpenAI embeddings and pgvector similarity search.
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel, Field

from integration_hub.db.database import get_db
from integration_hub.services.embedding_service import EmbeddingService

router = APIRouter(prefix="/api/v1/similarity", tags=["similarity"])


class SimilaritySearchRequest(BaseModel):
    """Request body for text-based similarity search"""
    text: str = Field(..., min_length=2, max_length=5000, description="Text to search for")
    limit: int = Field(10, ge=1, le=50, description="Maximum results to return")
    min_similarity: float = Field(0.55, ge=0.0, le=1.0, description="Minimum similarity score")
    vendor_id: Optional[int] = Field(None, description="Filter by vendor ID")
    location_id: Optional[int] = Field(None, description="Filter by location ID")


class GenerateEmbeddingsRequest(BaseModel):
    """Request body for batch embedding generation"""
    limit: int = Field(100, ge=1, le=500, description="Max items to process")


@router.get("/stats")
async def get_embedding_stats(db: Session = Depends(get_db)):
    """
    Get statistics about embedding coverage.

    Returns counts of items with/without embeddings and service availability.
    """
    service = EmbeddingService(db)
    return service.get_embedding_stats()


@router.post("/search")
async def search_similar_items(
    request: SimilaritySearchRequest,
    db: Session = Depends(get_db)
):
    """
    Search for vendor items similar to the provided text.

    Uses AI embeddings to find semantically similar products across vendors.
    Results are ranked by cosine similarity score.
    """
    service = EmbeddingService(db)

    if not service.is_available():
        raise HTTPException(
            status_code=503,
            detail="Embedding service unavailable (check OpenAI API key and pgvector)"
        )

    results = service.find_similar_items(
        text=request.text,
        limit=request.limit,
        min_similarity=request.min_similarity,
        vendor_id=request.vendor_id,
        location_id=request.location_id
    )

    return {
        "query": request.text[:100] + "..." if len(request.text) > 100 else request.text,
        "count": len(results),
        "results": results
    }


@router.get("/search")
async def search_similar_items_get(
    text: str = Query(..., min_length=2, max_length=5000, description="Text to search for"),
    limit: int = Query(10, ge=1, le=50, description="Maximum results"),
    min_similarity: float = Query(0.55, ge=0.0, le=1.0, description="Minimum similarity"),
    vendor_id: Optional[int] = Query(None, description="Filter by vendor"),
    location_id: Optional[int] = Query(None, description="Filter by location"),
    db: Session = Depends(get_db)
):
    """
    Search for vendor items similar to the provided text (GET version).

    Same as POST /search but uses query parameters for simpler testing.
    """
    service = EmbeddingService(db)

    if not service.is_available():
        raise HTTPException(
            status_code=503,
            detail="Embedding service unavailable (check OpenAI API key and pgvector)"
        )

    results = service.find_similar_items(
        text=text,
        limit=limit,
        min_similarity=min_similarity,
        vendor_id=vendor_id,
        location_id=location_id
    )

    return {
        "query": text[:100] + "..." if len(text) > 100 else text,
        "count": len(results),
        "results": results
    }


@router.get("/item/{vendor_item_id}")
async def find_similar_to_item(
    vendor_item_id: int,
    limit: int = Query(10, ge=1, le=50, description="Maximum results"),
    min_similarity: float = Query(0.55, ge=0.0, le=1.0, description="Minimum similarity"),
    same_vendor: bool = Query(False, description="Only search within same vendor"),
    same_location: bool = Query(False, description="Only search within same location"),
    db: Session = Depends(get_db)
):
    """
    Find vendor items similar to an existing vendor item.

    Useful for:
    - Finding duplicate/similar items across vendors
    - Suggesting matches for unmapped items
    - Cross-location price comparisons for similar products
    """
    service = EmbeddingService(db)

    if not service.is_available():
        raise HTTPException(
            status_code=503,
            detail="Embedding service unavailable"
        )

    results = service.find_similar_to_item(
        vendor_item_id=vendor_item_id,
        limit=limit,
        min_similarity=min_similarity,
        same_vendor=same_vendor,
        same_location=same_location
    )

    return {
        "source_item_id": vendor_item_id,
        "count": len(results),
        "results": results
    }


@router.post("/generate")
async def generate_embeddings(
    request: GenerateEmbeddingsRequest,
    db: Session = Depends(get_db)
):
    """
    Generate embeddings for vendor items that don't have them yet.

    This is a batch operation that processes items without embeddings.
    Call multiple times to process all items.
    """
    service = EmbeddingService(db)

    if not service.is_available():
        raise HTTPException(
            status_code=503,
            detail="Embedding service unavailable"
        )

    success, failure = service.update_embeddings_batch(limit=request.limit)

    # Get updated stats
    stats = service.get_embedding_stats()

    return {
        "processed": success + failure,
        "success": success,
        "failure": failure,
        "stats": stats
    }


@router.post("/item/{vendor_item_id}/generate")
async def generate_item_embedding(
    vendor_item_id: int,
    db: Session = Depends(get_db)
):
    """
    Generate/regenerate embedding for a specific vendor item.

    Use this to update the embedding after item details change.
    """
    from integration_hub.models.hub_vendor_item import HubVendorItem

    service = EmbeddingService(db)

    if not service.is_available():
        raise HTTPException(
            status_code=503,
            detail="Embedding service unavailable"
        )

    item = db.query(HubVendorItem).filter(HubVendorItem.id == vendor_item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Vendor item not found")

    success = service.update_vendor_item_embedding(item)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to generate embedding")

    return {
        "id": vendor_item_id,
        "text": item.embedding_text[:200] + "..." if len(item.embedding_text) > 200 else item.embedding_text,
        "success": True
    }
