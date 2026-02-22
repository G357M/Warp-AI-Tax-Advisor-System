"""
RAG (Retrieval-Augmented Generation) pipeline.
"""
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from core.config import settings
from core.database import SessionLocal
from models import Document, DocumentChunk
from rag.embeddings import embeddings_generator
from rag.vector_store import vector_store
from rag.llm import llm_client


class RAGPipeline:
    """Complete RAG pipeline for query processing."""

    def __init__(self):
        """Initialize RAG pipeline."""
        self.embeddings = embeddings_generator
        self.vector_store = vector_store
        self.llm = llm_client

    def process_query(
        self,
        query: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        language: str = "ka",
    ) -> Dict[str, Any]:
        """
        Process user query through RAG pipeline.

        Args:
            query: User query text
            conversation_history: Previous conversation messages
            language: Query language (ka, ru, en)

        Returns:
            Dictionary with response and sources
        """
        try:
            # Step 1: Generate query embedding
            query_embedding = self.embeddings.encode_query(query)
            print(f"[RAG] Query: {query[:50]}..., Language: {language}")

            # Step 2: Search vector store
            search_results = self.vector_store.search(
                query_embedding=query_embedding,
                n_results=settings.RAG_TOP_K,
                where={"language": language} if language else None,
            )
            print(f"[RAG] Search results: {len(search_results.get('ids', [[]])[0])} chunks found")

            # Step 3: Retrieve full documents from database
            retrieved_chunks = self._retrieve_chunks(search_results)
            print(f"[RAG] Retrieved chunks: {len(retrieved_chunks)}")

            # Step 4: Assemble context
            context = self._assemble_context(retrieved_chunks)

            # Step 5: Generate response using LLM
            response = self.llm.generate_response(
                query=query,
                context=context,
                conversation_history=conversation_history,
            )

            # Step 6: Prepare sources
            sources = self._prepare_sources(retrieved_chunks)
            print(f"[RAG] Prepared sources: {len(sources)}")
            if len(sources) == 0 and len(retrieved_chunks) > 0:
                print(f"[RAG] WARNING: Retrieved {len(retrieved_chunks)} chunks but 0 sources!")
                print(f"[RAG] First chunk metadata: {retrieved_chunks[0].get('metadata', {})}")

            return {
                "response": response,
                "sources": sources,
                "retrieved_count": len(retrieved_chunks),
            }

        except Exception as e:
            print(f"Error in RAG pipeline: {e}")
            return {
                "response": f"Извините, произошла ошибка при обработке запроса: {str(e)}",
                "sources": [],
                "retrieved_count": 0,
            }

    def _retrieve_chunks(self, search_results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Retrieve full chunk information from database.

        Args:
            search_results: Results from vector store search

        Returns:
            List of chunk dictionaries with metadata
        """
        chunks = []
        
        if not search_results.get("ids") or not search_results["ids"][0]:
            return chunks

        chunk_ids = search_results["ids"][0]
        documents = search_results["documents"][0]
        metadatas = search_results.get("metadatas", [[]])[0]
        distances = search_results.get("distances", [[]])[0]

        for i, chunk_id in enumerate(chunk_ids):
            chunks.append({
                "id": chunk_id,
                "content": documents[i] if i < len(documents) else "",
                "metadata": metadatas[i] if i < len(metadatas) else {},
                "similarity": 1 - distances[i] if i < len(distances) else 0.0,
            })

        return chunks

    def _assemble_context(self, chunks: List[Dict[str, Any]]) -> str:
        """
        Assemble context from retrieved chunks.

        Args:
            chunks: List of retrieved chunks

        Returns:
            Assembled context string
        """
        if not chunks:
            return "Нет доступной информации в базе данных."

        context_parts = []
        for i, chunk in enumerate(chunks[:settings.RAG_RERANK_TOP_K], 1):
            metadata = chunk.get("metadata", {})
            doc_title = metadata.get("title", "Неизвестный документ")
            doc_type = metadata.get("document_type", "")
            
            context_parts.append(
                f"[Документ {i}: {doc_title} ({doc_type})]\n{chunk['content']}\n"
            )

        return "\n---\n".join(context_parts)

    def _prepare_sources(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Prepare source information for response.

        Args:
            chunks: List of retrieved chunks

        Returns:
            List of source dictionaries
        """
        sources = []
        seen_docs = set()

        for chunk in chunks:
            metadata = chunk.get("metadata", {})
            doc_id = metadata.get("document_id")
            
            if not doc_id or doc_id in seen_docs:
                continue

            seen_docs.add(doc_id)
            sources.append({
                "document_id": doc_id,
                "title": metadata.get("title", "Неизвестный документ"),
                "document_type": metadata.get("document_type", ""),
                "url": metadata.get("source_url", ""),
                "relevance": chunk.get("similarity", 0.0),
            })

        return sources[:5]  # Top 5 unique sources


# Global RAG pipeline instance
rag_pipeline = RAGPipeline()
