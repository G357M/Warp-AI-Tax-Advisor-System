"""
Public API routes (no authentication required).
"""
import time
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

from backend.rag.pipeline import rag_pipeline


router = APIRouter(prefix="/public", tags=["Public"])


class PublicQueryRequest(BaseModel):
    """Public query request schema."""
    query: str = Field(..., min_length=1, max_length=2000, description="User query")
    language: Optional[str] = Field(default="ru", pattern="^(ka|ru|en)$", description="Query language")


class PublicSourceInfo(BaseModel):
    """Source information schema."""
    text: str
    relevance: float
    metadata: Dict[str, Any]


class PublicQueryResponse(BaseModel):
    """Public query response schema."""
    response: str
    sources: List[PublicSourceInfo]
    retrieved_count: int
    processing_time: float


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    components: Dict[str, bool]
    stats: Dict[str, Any]


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Public health check endpoint.
    
    Returns system status and component availability with connection checks.
    """
    from backend.core.config import settings
    from backend.core.database import SessionLocal
    from backend.core.cache import cache
    from backend.rag.embeddings import embeddings_generator
    from backend.rag.vector_store import vector_store
    from backend.rag.llm import llm_client
    import sqlalchemy
    
    # Check database connection
    database_healthy = False
    try:
        db = SessionLocal()
        db.execute(sqlalchemy.text("SELECT 1"))
        db.close()
        database_healthy = True
    except Exception as e:
        print(f"Database health check failed: {e}")
    
    # Check Redis connection
    redis_healthy = False
    try:
        await cache.ping()
        redis_healthy = True
    except Exception as e:
        print(f"Redis health check failed: {e}")
    
    # Overall health status
    all_healthy = (
        database_healthy and
        redis_healthy and
        embeddings_generator.model is not None and
        vector_store.client is not None and
        llm_client.client is not None
    )
    
    return {
        "status": "healthy" if all_healthy else "degraded",
        "version": settings.APP_VERSION,
        "components": {
            "database": database_healthy,
            "redis": redis_healthy,
            "embeddings": embeddings_generator.model is not None,
            "vector_store": vector_store.client is not None,
            "llm": llm_client.client is not None,
        },
        "stats": {
            "total_documents": vector_store.get_count() if vector_store.client else 0,
            "embedding_dimension": settings.EMBEDDING_DIMENSION,
            "llm_model": settings.LLM_MODEL,
        }
    }


@router.post("/query", response_model=PublicQueryResponse)
def process_public_query(query_data: PublicQueryRequest):
    """
    Process query without authentication (for testing/demo).
    
    **Note:** This is a public endpoint for testing purposes.
    In production, use the authenticated `/query` endpoint.
    
    - **query**: Your question about Georgian tax law
    - **language**: Language code (ka=Georgian, ru=Russian, en=English)
    
    Returns:
    - AI-generated response with relevant sources
    """
    start_time = time.time()
    
    try:
        # Process query through RAG pipeline
        result = rag_pipeline.process_query(
            query=query_data.query,
            conversation_history=None,
            language=query_data.language
        )
        
        # Format sources for public response
        formatted_sources = []
        for chunk in result.get("sources", []):
            # Use chunk data instead of requiring document_id
            formatted_sources.append(PublicSourceInfo(
                text=chunk.get("title", "")[:200],  # First 200 chars
                relevance=chunk.get("relevance", 0.0),
                metadata=chunk or {}
            ))
        
        processing_time = time.time() - start_time
        
        return PublicQueryResponse(
            response=result.get("response", ""),
            sources=formatted_sources,
            retrieved_count=result.get("retrieved_count", 0),
            processing_time=processing_time
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing query: {str(e)}"
        )


@router.get("/stats")
def get_public_stats():
    """
    Get public system statistics.
    
    Returns basic information about the system without authentication.
    """
    from backend.core.config import settings
    from backend.rag.vector_store import vector_store
    
    return {
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "total_documents": vector_store.get_count() if vector_store.client else 0,
        "supported_languages": ["ka", "ru", "en"],
        "features": {
            "rag": True,
            "multilingual": True,
            "semantic_search": True,
        }
    }
