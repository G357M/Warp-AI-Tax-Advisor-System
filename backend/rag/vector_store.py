"""
Vector database client for storing and retrieving document embeddings.
"""
from typing import List, Dict, Optional, Any
import chromadb
from chromadb.config import Settings as ChromaSettings

from backend.core.config import settings


class VectorStore:
    """Client for vector database operations."""

    def __init__(self):
        """Initialize ChromaDB client."""
        self.client = None
        self.collection = None
        self._initialize_client()

    def _initialize_client(self):
        """Initialize ChromaDB client and collection."""
        try:
            # Create ChromaDB client
            if settings.CHROMA_HOST and settings.CHROMA_PORT:
                # Remote ChromaDB
                self.client = chromadb.HttpClient(
                    host=settings.CHROMA_HOST,
                    port=settings.CHROMA_PORT,
                    settings=ChromaSettings(
                        chroma_client_auth_provider="chromadb.auth.token.TokenAuthClientProvider",
                        chroma_client_auth_credentials=settings.CHROMA_AUTH_TOKEN,
                    ) if settings.CHROMA_AUTH_TOKEN else None,
                )
            else:
                # Local ChromaDB with persistent storage
                import os
                persist_directory = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "chromadb")
                self.client = chromadb.PersistentClient(path=persist_directory)

            # Get or create collection
            self.collection = self.client.get_or_create_collection(
                name="infohub_documents",
                metadata={"description": "Tax documents from infohub.ge"},
            )
            print(f"✓ Vector store initialized: {self.collection.count()} documents")

        except Exception as e:
            print(f"⚠ Warning: Could not initialize vector store: {e}")
            print(f"⚠ Vector search will not work until ChromaDB is running")
            self.client = None
            self.collection = None

    def add_documents(
        self,
        ids: List[str],
        embeddings: List[List[float]],
        documents: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        """
        Add documents with embeddings to the vector store.

        Args:
            ids: List of document IDs
            embeddings: List of embedding vectors
            documents: List of document texts
            metadatas: Optional list of metadata dictionaries

        Returns:
            True if successful, False otherwise
        """
        try:
            self.collection.add(
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
        """
        Search for similar documents.

        Args:
            query_embedding: Query embedding vector
            n_results: Number of results to return
            where: Optional metadata filters

        Returns:
            Search results dictionary
        """
        try:
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                where=where,
            )
            return results
        except Exception as e:
            print(f"Error searching vector store: {e}")
            return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}

    def delete_documents(self, ids: List[str]) -> bool:
        """
        Delete documents from vector store.

        Args:
            ids: List of document IDs to delete

        Returns:
            True if successful, False otherwise
        """
        try:
            self.collection.delete(ids=ids)
            return True
        except Exception as e:
            print(f"Error deleting documents from vector store: {e}")
            return False

    def clear_collection(self) -> bool:
        """
        Clear all documents from collection.

        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.delete_collection(name="infohub_documents")
            self.collection = self.client.create_collection(
                name="infohub_documents",
                metadata={"description": "Tax documents from infohub.ge"},
            )
            return True
        except Exception as e:
            print(f"Error clearing collection: {e}")
            return False

    def get_count(self) -> int:
        """
        Get total number of documents in collection.

        Returns:
            Document count
        """
        try:
            return self.collection.count()
        except Exception as e:
            print(f"Error getting document count: {e}")
            return 0


# Global vector store instance
vector_store = VectorStore()
