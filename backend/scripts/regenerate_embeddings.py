"""
Regenerate embeddings for all existing documents and store in pgvector.
"""
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.database import SessionLocal
from models.document import DocumentChunk
from rag.embeddings import embeddings_generator
from rag.vector_store_pgvector import vector_store
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def regenerate_embeddings():
    """Regenerate embeddings for all document chunks."""
    db = SessionLocal()
    
    try:
        # Get all chunks without embeddings
        chunks = db.query(DocumentChunk).filter(DocumentChunk.embedding == None).all()
        total = len(chunks)
        
        logger.info(f"Found {total} chunks without embeddings")
        
        if total == 0:
            logger.info("All chunks already have embeddings!")
            return
        
        # Process in batches
        batch_size = 50
        for i in range(0, total, batch_size):
            batch = chunks[i:i + batch_size]
            
            # Extract texts
            texts = [chunk.content for chunk in batch]
            
            # Generate embeddings
            logger.info(f"Processing batch {i//batch_size + 1}/{(total + batch_size - 1)//batch_size}")
            embeddings = embeddings_generator.encode(texts)
            
            # Prepare data for vector store
            ids = [f"doc_{chunk.document_id}_chunk_{chunk.id}" for chunk in batch]
            metadatas = [
                {
                    'document_id': str(chunk.document_id),
                    'chunk_id': str(chunk.id),
                    'chunk_index': chunk.chunk_index,
                }
                for chunk in batch
            ]
            
            # Add to pgvector
            vector_store.add_documents(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas
            )
            
            logger.info(f"Processed {min(i + batch_size, total)}/{total} chunks")
        
        # Create index for fast search
        logger.info("Creating HNSW index...")
        vector_store.create_index()
        
        # Verify
        count = vector_store.get_count()
        logger.info(f"✓ Complete! Total vectors in pgvector: {count}")
    
    except Exception as e:
        logger.error(f"Error regenerating embeddings: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    logger.info("=" * 80)
    logger.info("Regenerating embeddings with pgvector")
    logger.info("=" * 80)
    
    regenerate_embeddings()
