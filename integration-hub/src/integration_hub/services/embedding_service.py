"""
Embedding Service for AI-Powered Item Matching

Uses OpenAI's text-embedding-3-small model to generate vector embeddings
for vendor items. These embeddings enable semantic similarity search for:
- Finding similar items across different vendors
- Matching invoice items to existing vendor items
- Suggesting master item matches based on product descriptions

Architecture:
- Embeddings are stored in hub_vendor_items.embedding (pgvector Vector(1536))
- Uses cosine similarity for matching (HNSW index for fast lookup)
- Batch processing for efficiency when generating embeddings for many items
"""

import logging
import os
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text as sql_text

from openai import OpenAI

from integration_hub.models.hub_vendor_item import HubVendorItem, PGVECTOR_AVAILABLE

logger = logging.getLogger(__name__)

# OpenAI embedding model - 1536 dimensions, good quality/cost ratio
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536

# Batch size for embedding generation (OpenAI limit is 2048)
BATCH_SIZE = 100

# Similarity thresholds
HIGH_CONFIDENCE_THRESHOLD = 0.85  # Very similar items
MEDIUM_CONFIDENCE_THRESHOLD = 0.70  # Likely matches
LOW_CONFIDENCE_THRESHOLD = 0.55  # Possible matches


class EmbeddingService:
    """Service for generating and searching embeddings for vendor items"""

    def __init__(self, db: Session):
        self.db = db
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OPENAI_API_KEY not set - embedding features disabled")
            self.client = None
        else:
            self.client = OpenAI(api_key=api_key)

    def is_available(self) -> bool:
        """Check if embedding service is available"""
        return self.client is not None and PGVECTOR_AVAILABLE

    def generate_embedding(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding vector for a single text string.

        Args:
            text: The text to embed (product name, description, etc.)

        Returns:
            List of floats (1536 dimensions) or None on error
        """
        if not self.client:
            logger.warning("OpenAI client not initialized")
            return None

        if not text or not text.strip():
            logger.warning("Empty text provided for embedding")
            return None

        try:
            # Truncate very long text (OpenAI has token limits)
            text = text[:8000]  # Roughly 2000 tokens

            response = self.client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=text,
                dimensions=EMBEDDING_DIMENSIONS
            )
            return response.data[0].embedding

        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            return None

    def generate_embeddings_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        """
        Generate embeddings for multiple texts in a single API call.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors (same order as input)
        """
        if not self.client:
            return [None] * len(texts)

        if not texts:
            return []

        try:
            # Filter and truncate
            processed_texts = [t[:8000] if t else "" for t in texts]

            response = self.client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=processed_texts,
                dimensions=EMBEDDING_DIMENSIONS
            )

            # Return in order
            embeddings = [None] * len(texts)
            for item in response.data:
                embeddings[item.index] = item.embedding

            return embeddings

        except Exception as e:
            logger.error(f"Failed to generate batch embeddings: {e}")
            return [None] * len(texts)

    def update_vendor_item_embedding(self, vendor_item: HubVendorItem) -> bool:
        """
        Generate and store embedding for a single vendor item.

        Args:
            vendor_item: The HubVendorItem to update

        Returns:
            True if successful, False otherwise
        """
        if not PGVECTOR_AVAILABLE:
            logger.warning("pgvector not available - cannot store embeddings")
            return False

        text = vendor_item.embedding_text
        if not text:
            logger.warning(f"No text for embedding on vendor item {vendor_item.id}")
            return False

        embedding = self.generate_embedding(text)
        if embedding is None:
            return False

        try:
            # Use raw SQL for vector update (SQLAlchemy needs special handling)
            self.db.execute(
                sql_text("""
                    UPDATE hub_vendor_items
                    SET embedding = :embedding,
                        embedding_generated_at = :now
                    WHERE id = :id
                """),
                {
                    "embedding": str(embedding),
                    "now": datetime.now(timezone.utc),
                    "id": vendor_item.id
                }
            )
            self.db.commit()
            logger.info(f"Updated embedding for vendor item {vendor_item.id}")
            return True

        except Exception as e:
            logger.error(f"Failed to store embedding for vendor item {vendor_item.id}: {e}")
            self.db.rollback()
            return False

    def update_embeddings_batch(self, limit: int = 100) -> Tuple[int, int]:
        """
        Generate embeddings for vendor items that don't have them yet.

        Args:
            limit: Maximum number of items to process

        Returns:
            Tuple of (success_count, failure_count)
        """
        if not PGVECTOR_AVAILABLE:
            logger.warning("pgvector not available - cannot generate embeddings")
            return (0, 0)

        # Find items without embeddings
        items = self.db.query(HubVendorItem).filter(
            HubVendorItem.embedding.is_(None),
            HubVendorItem.vendor_product_name.isnot(None)
        ).limit(limit).all()

        if not items:
            logger.info("No vendor items need embedding updates")
            return (0, 0)

        logger.info(f"Generating embeddings for {len(items)} vendor items")

        # Collect texts
        texts = [item.embedding_text for item in items]

        # Generate in batches
        success_count = 0
        failure_count = 0

        for batch_start in range(0, len(items), BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, len(items))
            batch_items = items[batch_start:batch_end]
            batch_texts = texts[batch_start:batch_end]

            embeddings = self.generate_embeddings_batch(batch_texts)

            for item, embedding in zip(batch_items, embeddings):
                if embedding is None:
                    failure_count += 1
                    continue

                try:
                    self.db.execute(
                        sql_text("""
                            UPDATE hub_vendor_items
                            SET embedding = :embedding,
                                embedding_generated_at = :now
                            WHERE id = :id
                        """),
                        {
                            "embedding": str(embedding),
                            "now": datetime.now(timezone.utc),
                            "id": item.id
                        }
                    )
                    success_count += 1
                except Exception as e:
                    logger.error(f"Failed to store embedding for item {item.id}: {e}")
                    failure_count += 1

            self.db.commit()

        logger.info(f"Embedding batch complete: {success_count} success, {failure_count} failures")
        return (success_count, failure_count)

    def find_similar_items(
        self,
        text: str,
        limit: int = 10,
        min_similarity: float = LOW_CONFIDENCE_THRESHOLD,
        vendor_id: Optional[int] = None,
        location_id: Optional[int] = None,
        exclude_item_id: Optional[int] = None
    ) -> List[dict]:
        """
        Find vendor items similar to the given text using embedding similarity.

        Args:
            text: Text to search for (product name, description, etc.)
            limit: Maximum number of results
            min_similarity: Minimum cosine similarity (0-1)
            vendor_id: Optional filter by vendor
            location_id: Optional filter by location
            exclude_item_id: Optional item ID to exclude from results

        Returns:
            List of dicts with item details and similarity scores
        """
        if not PGVECTOR_AVAILABLE:
            logger.warning("pgvector not available - cannot search embeddings")
            return []

        # Generate embedding for search text
        query_embedding = self.generate_embedding(text)
        if query_embedding is None:
            return []

        try:
            # Build query with filters
            where_clauses = ["embedding IS NOT NULL"]
            params = {
                "embedding": str(query_embedding),
                "limit": limit,
                "min_similarity": 1 - min_similarity  # Convert to distance
            }

            if vendor_id:
                where_clauses.append("vendor_id = :vendor_id")
                params["vendor_id"] = vendor_id

            if location_id:
                where_clauses.append("location_id = :location_id")
                params["location_id"] = location_id

            if exclude_item_id:
                where_clauses.append("id != :exclude_id")
                params["exclude_id"] = exclude_item_id

            where_sql = " AND ".join(where_clauses)

            # Query using cosine distance (1 - similarity)
            # Lower distance = more similar
            # Note: Use CAST instead of :: to avoid SQLAlchemy parameter parsing issues
            result = self.db.execute(
                sql_text(f"""
                    SELECT
                        id,
                        vendor_id,
                        location_id,
                        vendor_product_name,
                        vendor_description,
                        vendor_sku,
                        category,
                        pack_size,
                        inventory_master_item_id,
                        inventory_master_item_name,
                        status,
                        1 - (embedding <=> CAST(:embedding AS vector)) as similarity
                    FROM hub_vendor_items
                    WHERE {where_sql}
                      AND (embedding <=> CAST(:embedding AS vector)) < :min_similarity
                    ORDER BY embedding <=> CAST(:embedding AS vector)
                    LIMIT :limit
                """),
                params
            )

            items = []
            for row in result:
                confidence = "high" if row.similarity >= HIGH_CONFIDENCE_THRESHOLD else \
                            "medium" if row.similarity >= MEDIUM_CONFIDENCE_THRESHOLD else "low"
                items.append({
                    "id": row.id,
                    "vendor_id": row.vendor_id,
                    "location_id": row.location_id,
                    "vendor_product_name": row.vendor_product_name,
                    "vendor_description": row.vendor_description,
                    "vendor_sku": row.vendor_sku,
                    "category": row.category,
                    "pack_size": row.pack_size,
                    "inventory_master_item_id": row.inventory_master_item_id,
                    "inventory_master_item_name": row.inventory_master_item_name,
                    "status": row.status,
                    "similarity": round(row.similarity, 4),
                    "confidence": confidence
                })

            return items

        except Exception as e:
            logger.error(f"Failed to search embeddings: {e}")
            return []

    def find_similar_to_item(
        self,
        vendor_item_id: int,
        limit: int = 10,
        min_similarity: float = LOW_CONFIDENCE_THRESHOLD,
        same_vendor: bool = False,
        same_location: bool = False
    ) -> List[dict]:
        """
        Find vendor items similar to an existing vendor item.

        Args:
            vendor_item_id: ID of the vendor item to find matches for
            limit: Maximum number of results
            min_similarity: Minimum cosine similarity (0-1)
            same_vendor: If True, only return items from the same vendor
            same_location: If True, only return items from the same location

        Returns:
            List of dicts with item details and similarity scores
        """
        # Get the source item
        item = self.db.query(HubVendorItem).filter(HubVendorItem.id == vendor_item_id).first()
        if not item:
            logger.warning(f"Vendor item {vendor_item_id} not found")
            return []

        # Use the item's text for search
        text = item.embedding_text
        if not text:
            return []

        vendor_filter = item.vendor_id if same_vendor else None
        location_filter = item.location_id if same_location else None

        return self.find_similar_items(
            text=text,
            limit=limit,
            min_similarity=min_similarity,
            vendor_id=vendor_filter,
            location_id=location_filter,
            exclude_item_id=vendor_item_id
        )

    def get_embedding_stats(self) -> dict:
        """
        Get statistics about embedding coverage.

        Returns:
            Dict with counts and percentages
        """
        try:
            total = self.db.query(HubVendorItem).count()
            with_embedding = self.db.execute(
                sql_text("SELECT COUNT(*) FROM hub_vendor_items WHERE embedding IS NOT NULL")
            ).scalar()
            without_embedding = total - with_embedding

            return {
                "total_items": total,
                "with_embedding": with_embedding,
                "without_embedding": without_embedding,
                "coverage_percent": round((with_embedding / total * 100), 1) if total > 0 else 0,
                "pgvector_available": PGVECTOR_AVAILABLE,
                "openai_configured": self.client is not None
            }

        except Exception as e:
            logger.error(f"Failed to get embedding stats: {e}")
            return {
                "total_items": 0,
                "with_embedding": 0,
                "without_embedding": 0,
                "coverage_percent": 0,
                "pgvector_available": PGVECTOR_AVAILABLE,
                "openai_configured": self.client is not None,
                "error": str(e)
            }
