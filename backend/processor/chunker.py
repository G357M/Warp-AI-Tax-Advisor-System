"""
Text chunking utilities for document processing.
"""
from typing import List, Dict, Any
import re

from backend.core.config import settings


class TextChunker:
    """Chunk text into smaller segments for embedding."""

    def __init__(
        self,
        chunk_size: int = None,
        chunk_overlap: int = None,
    ):
        """
        Initialize text chunker.

        Args:
            chunk_size: Size of each chunk in tokens (default from settings)
            chunk_overlap: Overlap between chunks in tokens (default from settings)
        """
        self.chunk_size = chunk_size or settings.RAG_CHUNK_SIZE
        self.chunk_overlap = chunk_overlap or settings.RAG_CHUNK_OVERLAP

    def chunk_text(self, text: str, metadata: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        Chunk text into smaller segments.

        Args:
            text: Text to chunk
            metadata: Optional metadata to attach to each chunk

        Returns:
            List of chunk dictionaries
        """
        if not text or not text.strip():
            return []

        # Split by paragraphs first
        paragraphs = self._split_paragraphs(text)

        chunks = []
        current_chunk = ""
        current_tokens = 0

        for para in paragraphs:
            para_tokens = self._estimate_tokens(para)

            # If paragraph itself is too large, split it
            if para_tokens > self.chunk_size:
                # Save current chunk if not empty
                if current_chunk:
                    chunks.append(self._create_chunk(current_chunk, len(chunks), metadata))
                    current_chunk = ""
                    current_tokens = 0

                # Split large paragraph into sentences
                sentences = self._split_sentences(para)
                for sent in sentences:
                    sent_tokens = self._estimate_tokens(sent)
                    
                    if current_tokens + sent_tokens > self.chunk_size and current_chunk:
                        chunks.append(self._create_chunk(current_chunk, len(chunks), metadata))
                        # Keep overlap
                        current_chunk = current_chunk[-self.chunk_overlap:] + " " + sent
                        current_tokens = self._estimate_tokens(current_chunk)
                    else:
                        current_chunk += " " + sent if current_chunk else sent
                        current_tokens += sent_tokens
            else:
                # Add paragraph to current chunk
                if current_tokens + para_tokens > self.chunk_size and current_chunk:
                    chunks.append(self._create_chunk(current_chunk, len(chunks), metadata))
                    # Keep overlap
                    current_chunk = current_chunk[-self.chunk_overlap:] + " " + para
                    current_tokens = self._estimate_tokens(current_chunk)
                else:
                    current_chunk += "\n\n" + para if current_chunk else para
                    current_tokens += para_tokens

        # Add remaining chunk
        if current_chunk.strip():
            chunks.append(self._create_chunk(current_chunk, len(chunks), metadata))

        return chunks

    def _split_paragraphs(self, text: str) -> List[str]:
        """Split text into paragraphs."""
        # Split by double newlines or multiple newlines
        paragraphs = re.split(r'\n\s*\n', text)
        return [p.strip() for p in paragraphs if p.strip()]

    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences."""
        # Simple sentence splitter (can be improved)
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]

    def _estimate_tokens(self, text: str) -> int:
        """
        Estimate token count (rough approximation).

        Args:
            text: Text to estimate

        Returns:
            Estimated token count
        """
        # Rough estimation: 1 token ≈ 4 characters for multilingual text
        return len(text) // 4

    def _create_chunk(self, content: str, index: int, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Create chunk dictionary.

        Args:
            content: Chunk content
            index: Chunk index
            metadata: Optional metadata

        Returns:
            Chunk dictionary
        """
        return {
            "content": content.strip(),
            "chunk_index": index,
            "tokens_count": self._estimate_tokens(content),
            "metadata": metadata or {},
        }


# Global text chunker instance
text_chunker = TextChunker()
