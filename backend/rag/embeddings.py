"""
Embeddings generation using multilingual sentence transformers.
"""
from typing import List, Union
from sentence_transformers import SentenceTransformer

from core.config import settings


class EmbeddingsGenerator:
    """Generate embeddings for text using sentence transformers."""

    def __init__(self):
        """Initialize embedding model."""
        self.model = None
        self._load_model()

    def _load_model(self):
        """Load sentence transformer model."""
        try:
            print(f"Loading embedding model: {settings.EMBEDDING_MODEL}")
            self.model = SentenceTransformer(settings.EMBEDDING_MODEL)
            print(f"✓ Embedding model loaded (dimension: {settings.EMBEDDING_DIMENSION})")
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
            return [[0.0] * settings.EMBEDDING_DIMENSION] * len(texts)

    def encode_query(self, query: str) -> List[float]:
        """
        Generate embedding for a single query.

        Args:
            query: Query text

        Returns:
            Embedding vector
        """
        embeddings = self.encode(query)
        return embeddings[0] if embeddings else [0.0] * settings.EMBEDDING_DIMENSION


# Global embeddings generator instance
embeddings_generator = EmbeddingsGenerator()
