"""
Embeddings generation using multilingual sentence transformers.
"""
import os
from typing import List, Union
from sentence_transformers import SentenceTransformer

from core.config import settings


def _use_v2() -> bool:
    """BGE-M3 (1024-d) replaces paraphrase-mpnet (768-d) when enabled.

    bge-m3 actually discriminates Georgian law and matches ru/en queries against the
    Georgian corpus directly (no translation needed), so it reads from the embedding_v2
    column. Toggle with INFOHUB_EMBEDDING_V2=1 once that column is fully populated.
    """
    return (os.getenv("INFOHUB_EMBEDDING_V2") or "").strip() == "1"


class EmbeddingsGenerator:
    """Generate embeddings for text using sentence transformers."""

    def __init__(self):
        """Initialize embedding model."""
        self.use_v2 = _use_v2()
        self.model_name = "BAAI/bge-m3" if self.use_v2 else settings.EMBEDDING_MODEL
        self.dimension = 1024 if self.use_v2 else settings.EMBEDDING_DIMENSION
        self._normalize = self.use_v2
        self.model = None
        self._load_model()

    def _load_model(self):
        """Load sentence transformer model."""
        try:
            print(f"Loading embedding model: {self.model_name}")
            self.model = SentenceTransformer(self.model_name)
            print(f"✓ Embedding model loaded (dimension: {self.dimension})")
        except Exception as e:
            print(f"⚠ Warning: Could not load embedding model: {e}")
            print(f"⚠ Embeddings will not work until model is downloaded")
            self.model = None

    def encode(self, texts: Union[str, List[str]], batch_size: int = 32) -> List[List[float]]:
        """
        Generate embeddings for text(s).

        Args:
            texts: Single text or list of texts
            batch_size: Batch size for processing

        Returns:
            List of embedding vectors
        """
        if isinstance(texts, str):
            texts = [texts]

        try:
            embeddings = self.model.encode(
                texts,
                batch_size=batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
            return embeddings.tolist()
        except Exception as e:
            print(f"Error generating embeddings: {e}")
            return [[0.0] * self.dimension] * len(texts)

    def encode_query(self, query: str) -> List[float]:
        """
        Generate embedding for a single query.

        Args:
            query: Query text

        Returns:
            Embedding vector
        """
        embeddings = self.encode(query)
        return embeddings[0] if embeddings else [0.0] * self.dimension


# Global embeddings generator instance
embeddings_generator = EmbeddingsGenerator()
