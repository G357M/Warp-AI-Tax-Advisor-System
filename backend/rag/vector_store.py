"""
Backward-compatibility shim.

The vector store migrated from ChromaDB to pgvector (see
``vector_store_pgvector.py``). This module re-exports the pgvector-backed
store so existing ``from rag.vector_store import vector_store`` callers keep
working without changes.
"""
from rag.vector_store_pgvector import vector_store, PgVectorStore as VectorStore

__all__ = ["vector_store", "VectorStore"]
