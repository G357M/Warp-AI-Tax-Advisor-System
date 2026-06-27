from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


DEFAULT_CHUNK_SIZE = 1024
DEFAULT_CHUNK_OVERLAP = 128


@dataclass
class ChunkRecord:
    chunk_id: str
    document_id: str
    chunk_index: int
    content: str
    tokens_count: int
    start_position: int
    end_position: int
    metadata: Dict[str, Any]


@dataclass
class IndexStats:
    documents_seen: int = 0
    documents_indexed: int = 0
    documents_skipped: int = 0
    chunks_written: int = 0
    embeddings_written: int = 0


class CorpusIndexer:
    def __init__(self, corpus_root: Path):
        self.corpus_root = corpus_root
        self.index_root = corpus_root / "index"
        self.index_root.mkdir(parents=True, exist_ok=True)

    def iter_documents(self, selected_relpaths: Optional[set[str]] = None) -> Iterable[tuple[Path, Dict[str, Any], str]]:
        for json_path in sorted((self.corpus_root / "normalized").glob("**/document.json")):
            rel = json_path.relative_to(self.corpus_root).as_posix()
            if selected_relpaths is not None and rel not in selected_relpaths:
                continue
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            md_path = json_path.with_name("document.md")
            markdown = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
            body = self.strip_frontmatter(markdown).strip()
            yield json_path, payload, body

    def build_chunks(
        self,
        document: Dict[str, Any],
        body_markdown: str,
        *,
        chunk_size: Optional[int] = None,
        overlap: Optional[int] = None,
    ) -> List[ChunkRecord]:
        chunk_size = chunk_size or self.default_chunk_size()
        overlap = overlap or self.default_chunk_overlap()
        doc_id = document["id"]
        elements = ((document.get("content") or {}).get("elements") or [])
        pieces_with_meta = self.chunk_elements(body_markdown, elements, chunk_size=chunk_size, overlap=overlap)
        if not pieces_with_meta:
            pieces_with_meta = [
                {
                    "content": piece,
                    "metadata": {
                        "chunk_strategy": "plain_text",
                        "element_types": [],
                    },
                }
                for piece in self.chunk_text(body_markdown, chunk_size=chunk_size, overlap=overlap)
            ]
        chunks: List[ChunkRecord] = []
        cursor = 0
        for idx, item in enumerate(pieces_with_meta):
            piece = item["content"]
            start = body_markdown.find(piece, cursor)
            if start < 0:
                start = cursor
            end = start + len(piece)
            cursor = max(end - overlap, end)
            chunk_hash = hashlib.sha1(f"{doc_id}:{idx}:{piece}".encode("utf-8")).hexdigest()[:16]
            chunk_id = f"{doc_id}:{idx}:{chunk_hash}"
            chunks.append(
                ChunkRecord(
                    chunk_id=chunk_id,
                    document_id=doc_id,
                    chunk_index=idx,
                    content=piece,
                    tokens_count=self.estimate_tokens(piece),
                    start_position=start,
                    end_position=end,
                    metadata={
                        "source_url": document.get("source_url"),
                        "title": document.get("title"),
                        "document_type": document.get("document_type"),
                        "authority": document.get("authority"),
                        "category": document.get("category"),
                        "status": document.get("status"),
                        "date_published": document.get("date_published"),
                        "complexity_level": (((document.get("content") or {}).get("complexity") or {}).get("level")),
                        **(item.get("metadata") or {}),
                    },
                )
            )
        return chunks

    def chunk_elements(
        self,
        body_markdown: str,
        elements: List[Dict[str, Any]],
        *,
        chunk_size: int,
        overlap: int,
    ) -> List[Dict[str, Any]]:
        if not elements:
            return []

        normalized_elements: List[Dict[str, Any]] = []
        for element in elements:
            text = str(element.get("markdown") or element.get("text") or "").strip()
            if not text:
                continue
            normalized_elements.append({
                "type": element.get("type") or "unknown",
                "text": text,
            })
        if not normalized_elements:
            return []

        chunks: List[Dict[str, Any]] = []
        current_parts: List[str] = []
        current_types: List[str] = []
        current_len = 0

        def flush() -> None:
            nonlocal current_parts, current_types, current_len
            if not current_parts:
                return
            content = "\n\n".join(part for part in current_parts if part).strip()
            if content:
                chunks.append({
                    "content": content,
                    "metadata": {
                        "chunk_strategy": "structured_elements",
                        "element_types": sorted(set(current_types)),
                    },
                })
            current_parts = []
            current_types = []
            current_len = 0

        for element in normalized_elements:
            piece = element["text"]
            etype = str(element["type"])

            if len(piece) > chunk_size:
                flush()
                subpieces = self.chunk_text(piece, chunk_size=chunk_size, overlap=overlap)
                for subpiece in subpieces:
                    chunks.append({
                        "content": subpiece,
                        "metadata": {
                            "chunk_strategy": "structured_elements_split",
                            "element_types": [etype],
                        },
                    })
                continue

            projected = current_len + len(piece) + (2 if current_parts else 0)
            if current_parts and projected > chunk_size:
                flush()

            current_parts.append(piece)
            current_types.append(etype)
            current_len = sum(len(part) for part in current_parts) + max(0, len(current_parts) - 1) * 2

        flush()
        return chunks

    def write_chunk_manifest(self, chunks: List[ChunkRecord]) -> Path:
        path = self.index_root / "chunks.jsonl"
        existing: Dict[str, Dict[str, Any]] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                existing[row["chunk_id"]] = row
        for chunk in chunks:
            existing[chunk.chunk_id] = {
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "chunk_index": chunk.chunk_index,
                "tokens_count": chunk.tokens_count,
                "start_position": chunk.start_position,
                "end_position": chunk.end_position,
                "content": chunk.content,
                "metadata": chunk.metadata,
            }
        ordered = [existing[key] for key in sorted(existing.keys())]
        path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in ordered) + "\n", encoding="utf-8")
        return path

    def index_corpus(
        self,
        *,
        limit: Optional[int] = None,
        chunk_size: Optional[int] = None,
        overlap: Optional[int] = None,
        write_db: bool = False,
        embed: bool = False,
        force: bool = False,
        selected_json: Optional[Path] = None,
    ) -> IndexStats:
        stats = IndexStats()
        db: Optional["Session"] = self.create_session() if write_db else None
        batch_rows: List[tuple[DocumentChunk, ChunkRecord]] = []
        selected_relpaths = self.load_selected_relpaths(selected_json)

        try:
            for idx, (_json_path, payload, body) in enumerate(self.iter_documents(selected_relpaths=selected_relpaths), start=1):
                if limit and idx > limit:
                    break
                stats.documents_seen += 1
                if not body.strip():
                    stats.documents_skipped += 1
                    continue

                file_hash = payload.get("hashes", {}).get("content_md5") or hashlib.md5(body.encode("utf-8")).hexdigest()
                chunks = self.build_chunks(payload, body, chunk_size=chunk_size, overlap=overlap)
                self.write_chunk_manifest(chunks)
                stats.chunks_written += len(chunks)

                if not write_db:
                    stats.documents_indexed += 1
                    continue

                assert db is not None
                Document, DocumentChunk = self.document_models()
                existing = db.query(Document).filter_by(source_url=payload["source_url"]).order_by(Document.created_at.asc()).first()
                if existing and existing.file_hash == file_hash and not force:
                    stats.documents_skipped += 1
                    continue

                document_row = existing or Document(source_url=payload["source_url"])
                document_row.title = payload["title"]
                document_row.document_type = self.fit_string(payload["document_type"], 50)
                document_row.document_number = self.fit_string(payload.get("document_number"), 100)
                document_row.date_published = self.parse_date(payload.get("date_published"))
                document_row.date_effective = self.parse_date(payload.get("date_effective"))
                document_row.language = self.fit_string(payload.get("language") or "unknown", 2) or "ka"
                document_row.category = self.fit_string(payload.get("category"), 50)
                document_row.authority = self.fit_authority(payload.get("authority"))
                document_row.status = self.fit_string(payload.get("status") or "unknown", 20) or "unknown"
                document_row.full_text = body
                document_row.file_hash = file_hash
                document_row.metadata_json = payload
                db.add(document_row)
                db.flush()

                if existing:
                    db.query(DocumentChunk).filter_by(document_id=document_row.id).delete(synchronize_session=False)
                    db.flush()

                for chunk in chunks:
                    row = DocumentChunk(
                        document_id=document_row.id,
                        chunk_index=chunk.chunk_index,
                        content=chunk.content,
                        tokens_count=chunk.tokens_count,
                        start_position=chunk.start_position,
                        end_position=chunk.end_position,
                        metadata_json=chunk.metadata,
                    )
                    db.add(row)
                    db.flush()
                    batch_rows.append((row, chunk))

                stats.documents_indexed += 1
                if len(batch_rows) >= 32:
                    if embed:
                        stats.embeddings_written += self.embed_pending_rows(batch_rows)
                    batch_rows.clear()
                    db.commit()

            if db is not None:
                if batch_rows:
                    if embed:
                        stats.embeddings_written += self.embed_pending_rows(batch_rows)
                    batch_rows.clear()
                db.commit()
                if embed:
                    self.create_vector_index(db)

            return stats
        except Exception:
            if db is not None:
                db.rollback()
            raise
        finally:
            if db is not None:
                db.close()

    def embed_pending_rows(self, rows: List[tuple[DocumentChunk, ChunkRecord]]) -> int:
        if not rows:
            return 0
        texts = [chunk.content for (_row, chunk) in rows]
        embeddings_generator = self.embeddings_generator()
        embeddings = embeddings_generator.encode(texts)
        for (row, _chunk), embedding in zip(rows, embeddings):
            row.embedding = embedding
        return len(rows)

    @staticmethod
    def create_vector_index(db: "Session") -> None:
        from sqlalchemy import text  # type: ignore

        db.execute(text("""
            CREATE INDEX IF NOT EXISTS document_chunks_embedding_idx
            ON document_chunks
            USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64);
        """))

    @staticmethod
    def parse_date(value: Optional[str]) -> Optional[date]:
        if not value:
            return None
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None

    @staticmethod
    def strip_frontmatter(markdown: str) -> str:
        if markdown.startswith("---\n"):
            parts = markdown.split("\n---\n", 1)
            if len(parts) == 2:
                return parts[1]
        return markdown

    @staticmethod
    def estimate_tokens(text: str) -> int:
        words = re.findall(r"\S+", text)
        return max(1, int(len(words) * 1.3))

    @staticmethod
    def fit_string(value: Optional[str], max_len: int) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        return text if len(text) <= max_len else text[:max_len]

    @classmethod
    def fit_authority(cls, value: Optional[str]) -> Optional[str]:
        text = cls.fit_string(value, 500)
        if not text:
            return None
        replacements = [
            (" მინისტრი", " სამინისტრო"),
            (" მინისტრის", " სამინისტროს"),
        ]
        for old, new in replacements:
            if text.endswith(old):
                text = text[: -len(old)] + new
                break
        if len(text) > 50 and text.startswith("საქართველოს "):
            text = text[len("საქართველოს "):]
        return cls.fit_string(text, 50)

    def load_selected_relpaths(self, selected_json: Optional[Path]) -> Optional[set[str]]:
        if not selected_json:
            return None
        rows = json.loads(selected_json.read_text(encoding="utf-8"))
        relpaths: set[str] = set()
        for row in rows:
            if isinstance(row, str):
                relpaths.add(row)
                continue
            if isinstance(row, dict):
                value = row.get("normalized_json") or row.get("path")
                if value:
                    relpaths.add(str(value))
        return relpaths if relpaths else None

    @staticmethod
    def default_chunk_size() -> int:
        try:
            from core.config import settings  # type: ignore

            return settings.RAG_CHUNK_SIZE
        except Exception:
            return DEFAULT_CHUNK_SIZE

    @staticmethod
    def default_chunk_overlap() -> int:
        try:
            from core.config import settings  # type: ignore

            return settings.RAG_CHUNK_OVERLAP
        except Exception:
            return DEFAULT_CHUNK_OVERLAP

    @staticmethod
    def create_session() -> "Session":
        from core.database import SessionLocal  # type: ignore

        return SessionLocal()

    @staticmethod
    def document_models():
        from models.document import Document, DocumentChunk  # type: ignore

        return Document, DocumentChunk

    @staticmethod
    def embeddings_generator():
        from rag.embeddings import embeddings_generator  # type: ignore

        return embeddings_generator

    @staticmethod
    def chunk_text(text: str, *, chunk_size: int, overlap: int) -> List[str]:
        text = text.strip()
        if not text:
            return []
        if len(text) <= chunk_size:
            return [text]

        chunks: List[str] = []
        start = 0
        while start < len(text):
            end = min(len(text), start + chunk_size)
            if end < len(text):
                for i in range(end, max(start + overlap, start), -1):
                    if text[i - 1] in ".!?\n":
                        end = i
                        break
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end >= len(text):
                break
            start = max(0, end - overlap)
        return chunks
