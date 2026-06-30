"""
Text chunking utilities for document processing.
"""
from typing import List, Dict, Any
import re

from core.config import settings


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

    # Article headings in the corpus look like "#### მუხლი 166. …" (markdown h4) or
    # a bare "მუხლი 166" at line start. Inline references use the ordinal form
    # ("166-ე მუხლის", number BEFORE მუხლი), which this does NOT match.
    _ARTICLE_HEADING_RE = re.compile(r"(?m)^\s*#{0,6}\s*მუხლი\s+(\d+[¹²³\d]*)")

    def chunk_by_article(self, text: str, metadata: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """Chunk legislation so each chunk is one whole article ("მუხლი N").

        A complete article embeds coherently with a topical query (unlike the
        current fragmented chunks), and carries article_ref for precise citation.
        Falls back to paragraph chunking for documents without article headings.
        """
        if not text or not text.strip():
            return []

        matches = list(self._ARTICLE_HEADING_RE.finditer(text))
        if not matches:
            return self.chunk_text(text, metadata)

        base_meta = dict(metadata or {})
        chunks: List[Dict[str, Any]] = []

        # Preamble before the first article (definitions/title) — keep, don't lose text.
        preamble = text[: matches[0].start()].strip()
        if preamble:
            for ch in self.chunk_text(preamble, {**base_meta, "section_label": "preamble"}):
                ch["chunk_index"] = len(chunks)
                chunks.append(ch)

        max_chars = max(self.chunk_size * 4, 4000)  # tokens→chars; keep an article whole if it fits
        for i, m in enumerate(matches):
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            article_text = text[start:end].strip()
            if not article_text:
                continue
            article_ref = m.group(1)
            first_line = article_text.splitlines()[0].lstrip("# ").strip()
            section_label = first_line[:120]
            art_meta = {**base_meta, "article_ref": article_ref, "section_label": section_label}

            if len(article_text) <= max_chars:
                chunk = self._create_chunk(article_text, len(chunks), art_meta)
                chunks.append(chunk)
            else:
                # Long article: split at paragraph boundaries, keep the heading on the
                # first part and tag every part with the same article_ref.
                parts = self._split_long_article(article_text, max_chars)
                for p_idx, part in enumerate(parts):
                    part_meta = {**art_meta, "article_part": p_idx}
                    if p_idx > 0:
                        part = f"{section_label} (продолжение)\n{part}"
                    chunks.append(self._create_chunk(part, len(chunks), part_meta))

        return chunks

    def _split_long_article(self, article_text: str, max_chars: int) -> List[str]:
        """Greedily pack an over-long article's paragraphs into <=max_chars parts."""
        paragraphs = self._split_paragraphs(article_text)
        parts: List[str] = []
        current = ""
        for para in paragraphs:
            if current and len(current) + len(para) + 2 > max_chars:
                parts.append(current.strip())
                current = para
            else:
                current = f"{current}\n\n{para}" if current else para
        if current.strip():
            parts.append(current.strip())
        return parts or [article_text]

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
