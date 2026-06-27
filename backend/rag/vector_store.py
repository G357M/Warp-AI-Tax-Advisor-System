"""
Compatibility vector store facade.

The production stack has migrated to pgvector, but parts of the app still
expect the older Chroma-style interface from `rag.vector_store`.
This module keeps that import path stable while delegating all real work to
`rag.vector_store_pgvector`.
"""
from typing import List, Dict, Optional, Any

from rag.vector_store_pgvector import PgVectorStore, vector_store as pgvector_store


class VectorStore:
    """Backward-compatible wrapper around the pgvector store."""

    def __init__(self):
        self._store: PgVectorStore = pgvector_store
        self.client = self._store
        self.collection = None

    def add_documents(
        self,
        ids: List[str],
        embeddings: List[List[float]],
        documents: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        try:
            self._store.add_documents(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas or [{}] * len(ids),
            )
            return True
        except Exception as e:
            print(f"Error adding documents to vector store: {e}")
            return False

    def search(
        self,
        query_embedding: List[float],
        n_results: int = 10,
        where: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        try:
            results = self._store.search(
                query_embedding=query_embedding,
                limit=n_results,
                where=where,
            )
            return {
                "ids": [[item.get("id") for item in results]],
                "documents": [[item.get("document", "") for item in results]],
                "metadatas": [[item.get("metadata", {}) for item in results]],
                "distances": [[item.get("distance", 1.0) for item in results]],
            }
        except Exception as e:
            print(f"Error searching vector store: {e}")
            return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}

    def delete_documents(self, ids: List[str]) -> bool:
        print("delete_documents is not implemented for the pgvector compatibility layer")
        return False

    def clear_collection(self) -> bool:
        try:
            self._store.delete_collection()
            return True
        except Exception as e:
            print(f"Error clearing collection: {e}")
            return False

    def get_count(self) -> int:
        try:
            return self._store.get_count()
        except Exception as e:
            print(f"Error getting document count: {e}")
            return 0


vector_store = VectorStore()
