"""Embedding service using transformers (local, no external API)."""

import logging
from typing import List

import torch
from transformers import AutoModel, AutoTokenizer

from restaurant_cookbook.core.config import settings

logger = logging.getLogger(__name__)

_embedding_service = None


class EmbeddingService:
    def __init__(self):
        model_name = settings.EMBEDDING_MODEL
        logger.info(f"Loading embedding model: {model_name}")
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name)
        self.model.eval()
        logger.info("Embedding model loaded successfully")

    def _encode(self, texts: List[str]) -> List[List[float]]:
        """Encode texts to embeddings using mean pooling."""
        inputs = self.tokenizer(
            texts, return_tensors="pt", padding=True, truncation=True, max_length=256
        )
        with torch.no_grad():
            outputs = self.model(**inputs)
        # Mean pooling over token embeddings, respecting attention mask
        mask = inputs["attention_mask"].unsqueeze(-1).float()
        embeddings = (outputs.last_hidden_state * mask).sum(dim=1) / mask.sum(dim=1)
        return embeddings.tolist()

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of texts."""
        return self._encode(texts)

    def embed_query(self, text: str) -> List[float]:
        """Generate embedding for a single query."""
        return self._encode([text])[0]


def get_embedding_service() -> EmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
