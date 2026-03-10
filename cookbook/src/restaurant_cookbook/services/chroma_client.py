"""ChromaDB client for vector storage and similarity search."""

import logging
from typing import List, Optional

import chromadb

from restaurant_cookbook.core.config import settings

logger = logging.getLogger(__name__)

_chroma_service = None

COLLECTION_NAME = "cookbook_chunks"


class ChromaService:
    def __init__(self):
        logger.info(f"Initializing ChromaDB at: {settings.CHROMA_PERSIST_PATH}")
        self.client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_PATH)
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            f"ChromaDB ready — collection '{COLLECTION_NAME}' has {self.collection.count()} documents"
        )

    def add_documents(
        self,
        ids: List[str],
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: List[dict],
    ):
        """Add documents with pre-computed embeddings."""
        self.collection.add(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )

    def query(
        self,
        query_embedding: List[float],
        n_results: int = 5,
        book_ids: Optional[List[int]] = None,
    ) -> dict:
        """Query for similar documents. Optionally filter by book IDs."""
        where_filter = None
        if book_ids:
            if len(book_ids) == 1:
                where_filter = {"book_id": book_ids[0]}
            else:
                where_filter = {"book_id": {"$in": book_ids}}

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where_filter,
            include=["documents", "metadatas", "distances"],
        )
        return results

    def delete_book(self, book_id: int):
        """Delete all documents for a given book."""
        self.collection.delete(where={"book_id": book_id})
        logger.info(f"Deleted ChromaDB documents for book {book_id}")

    def count(self) -> int:
        return self.collection.count()

    def is_healthy(self) -> bool:
        try:
            self.collection.count()
            return True
        except Exception:
            return False


def get_chroma_service() -> ChromaService:
    global _chroma_service
    if _chroma_service is None:
        _chroma_service = ChromaService()
    return _chroma_service
