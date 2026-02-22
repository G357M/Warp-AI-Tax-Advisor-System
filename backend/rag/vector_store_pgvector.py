"""
Vector store implementation using pgvector (PostgreSQL extension).
Compatible with Python 3.14+.
"""
import logging
from typing import List, Dict, Optional, Any
import numpy as np
from sqlalchemy import text, select
from sqlalchemy.orm import Session

from core.database import SessionLocal, engine
from models.document import DocumentChunk


logger = logging.getLogger(__name__)


class PgVectorStore:
    """Vector store using PostgreSQL with pgvector extension."""
    
    def __init__(self):
        self.dimension = 768  # sentence-transformers/paraphrase-multilingual-mpnet-base-v2
        self.session: Optional[Session] = None
        self._initialize()
    
    def _initialize(self):
        """Initialize connection and verify pgvector is installed."""
        try:
            with engine.connect() as conn:
                # Check if vector extension exists
                result = conn.execute(
                    text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
                )
                if not result.fetchone():
                    raise RuntimeError("pgvector extension is not installed")
                
                logger.info(f"✓ pgvector initialized (dimension: {self.dimension})")
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
        """
        Add documents with embeddings to vector store.
        
        Args:
            ids: List of unique IDs (format: "doc_{doc_id}_chunk_{chunk_id}")
            embeddings: List of embedding vectors
            documents: List of document texts
            metadatas: List of metadata dicts
        """
        if not (len(ids) == len(embeddings) == len(documents) == len(metadatas)):
            raise ValueError("All input lists must have the same length")
        
        db = SessionLocal()
        try:
            for chunk_id_str, embedding, text, metadata in zip(ids, embeddings, documents, metadatas):
                # Extract chunk_id from format "doc_{doc_id}_chunk_{chunk_id}"
                try:
                    chunk_id = int(chunk_id_str.split('_')[-1])
                except:
                    logger.warning(f"Could not parse chunk_id from {chunk_id_str}, skipping")
                    continue
                
                # Update chunk with embedding
                chunk = db.query(DocumentChunk).filter_by(id=chunk_id).first()
                if chunk:
                    # Convert embedding to PostgreSQL vector format
                    embedding_array = np.array(embedding, dtype=np.float32)
                    chunk.embedding = embedding_array.tolist()  # Store as list, SQLAlchemy will convert
                    db.merge(chunk)
                else:
                    logger.warning(f"Chunk {chunk_id} not found in database")
            
            db.commit()
            logger.info(f"Added {len(ids)} vectors to pgvector")
        
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
        """
        Search for similar vectors using cosine similarity.
        
        Args:
            query_embedding: Query vector
            limit: Maximum number of results
            where: Optional metadata filters (not implemented yet)
        
        Returns:
            List of results with 'id', 'document', 'metadata', 'distance'
        """
        db = SessionLocal()
        try:
            # Convert query to numpy array
            query_vec = np.array(query_embedding, dtype=np.float32)
            
            # Build SQL query with pgvector cosine distance
            # Using <=> operator for cosine distance (1 - cosine similarity)
            query = text("""
                SELECT 
                    id,
                    document_id,
                    chunk_index,
                    content,
                    metadata_json,
                    1 - (embedding <=> :query_embedding::vector) as similarity,
                    embedding <=> :query_embedding::vector as distance
                FROM document_chunks
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> :query_embedding::vector
                LIMIT :limit
            """)
            
            result = db.execute(
                query,
                {
                    "query_embedding": query_vec.tolist(),
                    "limit": limit
                }
            )
            
            results = []
            for row in result:
                results.append({
                    'id': f"doc_{row.document_id}_chunk_{row.id}",
                    'document': row.content,
                    'metadata': {
                        'chunk_id': str(row.id),
                        'document_id': str(row.document_id),
                        'chunk_index': row.chunk_index,
                        **(row.metadata_json or {})
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
        """Get total number of vectors in store."""
        db = SessionLocal()
        try:
            result = db.execute(
                text("SELECT COUNT(*) FROM document_chunks WHERE embedding IS NOT NULL")
            )
            count = result.scalar()
            return count or 0
        finally:
            db.close()
    
    def delete_collection(self) -> None:
        """Delete all vectors (clear embeddings)."""
        db = SessionLocal()
        try:
            db.execute(
                text("UPDATE document_chunks SET embedding = NULL")
            )
            db.commit()
            logger.info("Cleared all embeddings from pgvector")
        except Exception as e:
            logger.error(f"Error clearing embeddings: {e}")
            db.rollback()
        finally:
            db.close()
    
    def create_index(self) -> None:
        """Create HNSW index for fast vector search."""
        db = SessionLocal()
        try:
            # Create HNSW index for cosine distance
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
