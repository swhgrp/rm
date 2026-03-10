"""Embedding service using sentence-transformers (local, no external API)."""

import logging
from typing import List

from restaurant_cookbook.core.config import settings

logger = logging.getLogger(__name__)

_embedding_service = None


class EmbeddingService:
    def __init__(self):
        logger.info(f"Loading embedding model: {settings.EMBEDDING_MODEL}")
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(settings.EMBEDDING_MODEL)
        logger.info("Embedding model loaded successfully")

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of texts."""
        embeddings = self.model.encode(texts, show_progress_bar=False)
        return [emb.tolist() for emb in embeddings]

    def embed_query(self, text: str) -> List[float]:
        """Generate embedding for a single query."""
        embedding = self.model.encode([text], show_progress_bar=False)
        return embedding[0].tolist()


def get_embedding_service() -> EmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
