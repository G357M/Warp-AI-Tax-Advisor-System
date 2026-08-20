"""
Vector store implementation using pgvector (PostgreSQL extension).
Compatible with Python 3.14+.
"""
import logging
import os
from typing import List, Dict, Optional, Any
from uuid import UUID
import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.database import SessionLocal, engine
from models.document import DocumentChunk


logger = logging.getLogger(__name__)


def _use_v2() -> bool:
    """Mirrors rag.embeddings._use_v2 — duplicated (not imported) so importing
    this module never forces a SentenceTransformer load just to pick a column name.
    """
    return (os.getenv("INFOHUB_EMBEDDING_V2") or "").strip() == "1"


class PgVectorStore:
    """Vector store using PostgreSQL with pgvector extension."""

    def __init__(self):
        self.use_v2 = _use_v2()
        self.dimension = 1024 if self.use_v2 else 768
        self.embedding_column = "embedding_v2" if self.use_v2 else "embedding"
        # embedding_column is f-string-interpolated into raw SQL below; keep it
        # restricted to this fixed pair, never derived from external input.
        assert self.embedding_column in ("embedding", "embedding_v2")
        self.session: Optional[Session] = None
        self._initialize()

    def _initialize(self):
        """Initialize connection and verify pgvector is installed."""
        try:
            with engine.connect() as conn:
                result = conn.execute(text("SELECT extname FROM pg_extension WHERE extname = 'vector'"))
                if not result.fetchone():
                    raise RuntimeError("pgvector extension is not installed")
                logger.info(f"✓ pgvector initialized (column: {self.embedding_column}, dimension: {self.dimension})")
        except Exception as e:
            logger.error(f"Failed to initialize pgvector: {e}")
            raise

    def add_documents(
        self,
        ids: List[str],
        embeddings: List[List[float]],
        documents: List[str],
        metadatas: List[Dict[str, Any]]
    ) -> None:
        """Add embeddings by updating existing document_chunks rows."""
        if not (len(ids) == len(embeddings) == len(documents) == len(metadatas)):
            raise ValueError("All input lists must have the same length")

        db = SessionLocal()
        updated_count = 0
        try:
            for chunk_id_str, embedding, _text, _metadata in zip(ids, embeddings, documents, metadatas):
                try:
                    chunk_uuid_str = chunk_id_str.split('_chunk_')[-1]
                    chunk_id = UUID(chunk_uuid_str)
                except Exception:
                    logger.warning(f"Could not parse chunk UUID from {chunk_id_str}, skipping")
                    continue

                chunk = db.query(DocumentChunk).filter_by(id=chunk_id).first()
                if not chunk:
                    logger.warning(f"Chunk {chunk_id} not found in database")
                    continue

                embedding_array = np.array(embedding, dtype=np.float32)
                setattr(chunk, self.embedding_column, embedding_array.tolist())
                updated_count += 1

            db.commit()
            logger.info(f"Added {updated_count} vectors to pgvector")
        except Exception as e:
            logger.error(f"Error adding documents to pgvector: {e}")
            db.rollback()
            raise
        finally:
            db.close()

    def search(
        self,
        query_embedding: List[float],
        limit: int = 10,
        where: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Search for similar vectors using cosine similarity."""
        db = SessionLocal()
        try:
            col = self.embedding_column
            query_vec = np.array(query_embedding, dtype=np.float32)
            query_vec_str = "[" + ",".join(str(float(x)) for x in query_vec.tolist()) + "]"
            sql = f"""
                SELECT
                    c.id,
                    c.document_id,
                    c.chunk_index,
                    c.content,
                    c.metadata,
                    d.title AS document_title,
                    d.document_type AS document_type,
                    d.category AS document_category,
                    d.language AS document_language,
                    d.source_url AS source_url,
                    d.document_number AS document_number,
                    d.date_published AS date_published,
                    d.date_effective AS date_effective,
                    d.status AS document_status,
                    d.authority AS authority,
                    1 - (c.{col} <=> CAST(:query_embedding AS vector)) as similarity,
                    c.{col} <=> CAST(:query_embedding AS vector) as distance
                FROM document_chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE c.{col} IS NOT NULL
            """
            clauses = []
            params = {"query_embedding": query_vec_str, "limit": limit}
            if where:
                language = where.get("language")
                if language:
                    clauses.append("d.language = :language")
                    params["language"] = language

                language_in = where.get("language_in") or where.get("languages")
                if language_in:
                    names = []
                    for i, value in enumerate(language_in):
                        key = f"language_in_{i}"
                        params[key] = value
                        names.append(f":{key}")
                    clauses.append(f"d.language IN ({', '.join(names)})")

                document_types = where.get("document_types") or where.get("document_type_in")
                if document_types:
                    names = []
                    for i, value in enumerate(document_types):
                        key = f"document_type_{i}"
                        params[key] = value
                        names.append(f":{key}")
                    clauses.append(f"d.document_type IN ({', '.join(names)})")

                exclude_document_types = where.get("exclude_document_types") or where.get("document_type_not_in")
                if exclude_document_types:
                    names = []
                    for i, value in enumerate(exclude_document_types):
                        key = f"exclude_document_type_{i}"
                        params[key] = value
                        names.append(f":{key}")
                    clauses.append(f"d.document_type NOT IN ({', '.join(names)})")

                categories = where.get("categories") or where.get("category_in")
                if categories:
                    names = []
                    for i, value in enumerate(categories):
                        key = f"category_{i}"
                        params[key] = value
                        names.append(f":{key}")
                    clauses.append(f"d.category IN ({', '.join(names)})")

                exclude_categories = where.get("exclude_categories") or where.get("category_not_in")
                if exclude_categories:
                    names = []
                    for i, value in enumerate(exclude_categories):
                        key = f"exclude_category_{i}"
                        params[key] = value
                        names.append(f":{key}")
                    clauses.append(f"(d.category IS NULL OR d.category NOT IN ({', '.join(names)}))")

            if clauses:
                sql += " AND " + " AND ".join(clauses)
            sql += f" ORDER BY c.{col} <=> CAST(:query_embedding AS vector) LIMIT :limit"
            result = db.execute(text(sql), params)

            results = []
            for row in result:
                results.append({
                    'id': f"doc_{row.document_id}_chunk_{row.id}",
                    'document': row.content,
                    'metadata': {
                        **(row.metadata or {}),
                        'chunk_id': str(row.id),
                        'document_id': str(row.document_id),
                        'chunk_index': row.chunk_index,
                        'title': row.document_title or 'Неизвестный документ',
                        'document_type': row.document_type or '',
                        'category': row.document_category or '',
                        'language': row.document_language or '',
                        'source_url': row.source_url or '',
                        'document_number': row.document_number or '',
                        'date_published': row.date_published.isoformat() if row.date_published else None,
                        'date_effective': row.date_effective.isoformat() if row.date_effective else None,
                        'document_status': row.document_status or '',
                        'authority': row.authority or '',
                    },
                    'distance': float(row.distance),
                    'similarity': float(row.similarity)
                })

            logger.info(f"Found {len(results)} similar documents")
            return results
        except Exception as e:
            logger.error(f"Error searching pgvector: {e}")
            return []
        finally:
            db.close()

    def get_count(self) -> int:
        db = SessionLocal()
        try:
            result = db.execute(text(f"SELECT COUNT(*) FROM document_chunks WHERE {self.embedding_column} IS NOT NULL"))
            count = result.scalar()
            return count or 0
        finally:
            db.close()

    def delete_collection(self) -> None:
        db = SessionLocal()
        try:
            db.execute(text(f"UPDATE document_chunks SET {self.embedding_column} = NULL"))
            db.commit()
            logger.info(f"Cleared all {self.embedding_column} vectors from pgvector")
        except Exception as e:
            logger.error(f"Error clearing embeddings: {e}")
            db.rollback()
        finally:
            db.close()

    def create_index(self) -> None:
        db = SessionLocal()
        try:
            db.execute(text(f"""
                CREATE INDEX IF NOT EXISTS document_chunks_{self.embedding_column}_idx
                ON document_chunks
                USING hnsw ({self.embedding_column} vector_cosine_ops)
                WITH (m = 16, ef_construction = 64);
            """))
            db.commit()
            logger.info(f"Created HNSW index for pgvector ({self.embedding_column})")
        except Exception as e:
            logger.error(f"Error creating index: {e}")
            db.rollback()
        finally:
            db.close()


vector_store = PgVectorStore()
