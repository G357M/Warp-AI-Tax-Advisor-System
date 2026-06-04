"""
Vector store implementation using pgvector (PostgreSQL extension).
Compatible with Python 3.14+.

Drop-in replacement for the previous ChromaDB-based store: it preserves the
same public interface (``client`` availability flag, ``add_documents``,
``search`` returning the ChromaDB-shaped nested dict, ``get_count``,
``create_index``) so existing callers work unchanged.
"""
import logging
import uuid
from typing import List, Dict, Optional, Any

from sqlalchemy import text

from core.config import settings
from core.database import SessionLocal, engine
from models.document import DocumentChunk


logger = logging.getLogger(__name__)


class PgVectorStore:
    """Vector store using PostgreSQL with pgvector extension."""

    def __init__(self):
        self.dimension = settings.EMBEDDING_DIMENSION
        # ``client`` mirrors the old ChromaDB store: truthy when the store is
        # usable, ``None`` when unavailable. Callers gate on it.
        self.client = None
        self._initialize()

    def _initialize(self):
        """Verify pgvector is installed; degrade gracefully if not."""
        try:
            with engine.connect() as conn:
                result = conn.execute(
                    text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
                )
                if not result.fetchone():
                    raise RuntimeError("pgvector extension is not installed")

            self.client = engine
            logger.info(f"✓ pgvector initialized (dimension: {self.dimension})")
        except Exception as e:
            self.client = None
            logger.warning(f"⚠ Could not initialize pgvector: {e}")
            logger.warning("⚠ Vector search will not work until pgvector is available")

    def add_documents(
        self,
        ids: List[str],
        embeddings: List[List[float]],
        documents: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        """
        Store embeddings on the corresponding document chunks.

        Args:
            ids: Chunk identifiers, format ``doc_{document_id}_chunk_{chunk_id}``
                where ``chunk_id`` is the chunk's UUID.
            embeddings: Embedding vectors aligned with ``ids``.
            documents: Chunk texts (unused — content already lives on the row).
            metadatas: Optional metadata (unused — sourced from the document at
                search time via a JOIN).

        Returns:
            True if all embeddings were written, False on error.
        """
        if not (len(ids) == len(embeddings) == len(documents)):
            raise ValueError("ids, embeddings and documents must have the same length")

        db = SessionLocal()
        try:
            for chunk_id_str, embedding in zip(ids, embeddings):
                # Format is "doc_{document_uuid}_chunk_{chunk_uuid}"; UUIDs use
                # hyphens, so the last underscore-delimited token is the chunk UUID.
                try:
                    chunk_id = uuid.UUID(chunk_id_str.split("_")[-1])
                except (ValueError, IndexError):
                    logger.error(f"Could not parse chunk UUID from '{chunk_id_str}', skipping")
                    continue

                chunk = db.query(DocumentChunk).filter_by(id=chunk_id).first()
                if chunk:
                    chunk.embedding = embedding
                else:
                    logger.warning(f"Chunk {chunk_id} not found in database, skipping")

            db.commit()
            logger.info(f"Added {len(ids)} vectors to pgvector")
            return True
        except Exception as e:
            logger.error(f"Error adding documents to pgvector: {e}")
            db.rollback()
            return False
        finally:
            db.close()

    def search(
        self,
        query_embedding: List[float],
        n_results: int = 10,
        where: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Search for similar chunks using cosine distance.

        Returns the ChromaDB-shaped nested dict expected by the RAG pipeline:
        ``{"ids": [[...]], "documents": [[...]], "metadatas": [[...]],
        "distances": [[...]]}``.
        """
        empty: Dict[str, Any] = {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
        db = SessionLocal()
        try:
            language = where.get("language") if where else None
            language_clause = "AND d.language = :language" if language else ""

            # ``metadata_json`` maps to the DB column "metadata"; title /
            # document_type / source_url live on the documents table, so JOIN.
            query = text(f"""
                SELECT
                    c.id AS chunk_id,
                    c.document_id AS document_id,
                    c.chunk_index AS chunk_index,
                    c.content AS content,
                    c.metadata AS chunk_metadata,
                    d.title AS title,
                    d.document_type AS document_type,
                    d.source_url AS source_url,
                    d.language AS language,
                    c.embedding <=> :query_embedding::vector AS distance
                FROM document_chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE c.embedding IS NOT NULL
                {language_clause}
                ORDER BY c.embedding <=> :query_embedding::vector
                LIMIT :limit
            """)

            params: Dict[str, Any] = {
                "query_embedding": str(query_embedding),
                "limit": n_results,
            }
            if language:
                params["language"] = language

            rows = db.execute(query, params).fetchall()

            ids, docs, metadatas, distances = [], [], [], []
            for row in rows:
                ids.append(f"doc_{row.document_id}_chunk_{row.chunk_id}")
                docs.append(row.content)
                metadatas.append({
                    "chunk_id": str(row.chunk_id),
                    "document_id": str(row.document_id),
                    "chunk_index": row.chunk_index,
                    "title": row.title,
                    "document_type": row.document_type,
                    "source_url": row.source_url,
                    "language": row.language,
                    **(row.chunk_metadata or {}),
                })
                distances.append(float(row.distance))

            logger.info(f"Found {len(ids)} similar documents")
            return {
                "ids": [ids],
                "documents": [docs],
                "metadatas": [metadatas],
                "distances": [distances],
            }
        except Exception as e:
            logger.error(f"Error searching pgvector: {e}")
            return empty
        finally:
            db.close()

    def get_count(self) -> int:
        """Return the number of chunks that have an embedding."""
        db = SessionLocal()
        try:
            result = db.execute(
                text("SELECT COUNT(*) FROM document_chunks WHERE embedding IS NOT NULL")
            )
            return result.scalar() or 0
        except Exception as e:
            logger.error(f"Error getting document count: {e}")
            return 0
        finally:
            db.close()

    def create_index(self) -> None:
        """Create the HNSW index for fast cosine-distance search."""
        db = SessionLocal()
        try:
            db.execute(text("""
                CREATE INDEX IF NOT EXISTS document_chunks_embedding_idx
                ON document_chunks
                USING hnsw (embedding vector_cosine_ops)
                WITH (m = 16, ef_construction = 64);
            """))
            db.commit()
            logger.info("Created HNSW index for pgvector")
        except Exception as e:
            logger.error(f"Error creating index: {e}")
            db.rollback()
        finally:
            db.close()


# Global instance
vector_store = PgVectorStore()
