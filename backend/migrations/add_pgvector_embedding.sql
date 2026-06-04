-- Migration: Add pgvector embedding column to document_chunks
-- Purpose: Support vector search with pgvector instead of ChromaDB

-- Enable the pgvector extension (requires a superuser/owner role)
CREATE EXTENSION IF NOT EXISTS vector;

-- Add embedding column (768-dimensional vector for multilingual-mpnet-base-v2)
ALTER TABLE document_chunks 
ADD COLUMN IF NOT EXISTS embedding vector(768);

-- Create HNSW index for fast cosine similarity search
CREATE INDEX IF NOT EXISTS document_chunks_embedding_idx 
ON document_chunks 
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Create partial index for chunks with embeddings
CREATE INDEX IF NOT EXISTS document_chunks_has_embedding_idx
ON document_chunks (id)
WHERE embedding IS NOT NULL;
