"""
Public API routes (no authentication required).
"""
import logging
import time
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

from rag.pipeline import rag_pipeline
from rag_v2.shadow_runtime import maybe_run_shadow
from rag_v2.live_runtime import maybe_run_live_rollout


router = APIRouter(prefix="/public", tags=["Public"])
logger = logging.getLogger(__name__)


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
    from core.config import settings
    from core.database import SessionLocal
    from core.cache import cache
    from rag.embeddings import embeddings_generator
    from rag.vector_store import vector_store
    from rag.llm import llm_client
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
        result = maybe_run_live_rollout(
            query=query_data.query,
            language=query_data.language,
            conversation_history=None,
        )
        if result is None:
            result = rag_pipeline.process_query(
                query=query_data.query,
                conversation_history=None,
                language=query_data.language
            )
        
        maybe_run_shadow(
            query=query_data.query,
            language=query_data.language or "ru",
            route="/api/v1/public/query",
            legacy_result=result,
            extra={"surface": "public"},
        )

        # Format sources for public response
        formatted_sources = []
        for source in result.get("sources", []):
            formatted_sources.append(PublicSourceInfo(
                text=source.get("title", "")[:200],
                relevance=source.get("relevance", 0.0),
                metadata={
                    "title": source.get("title", ""),
                    "document_type": source.get("document_type", ""),
                    "source_url": source.get("url", ""),
                }
            ))

        processing_time = time.time() - start_time

        return PublicQueryResponse(
            response=result.get("response", ""),
            sources=formatted_sources,
            retrieved_count=len(formatted_sources),
            processing_time=processing_time
        )

    except Exception:
        logger.exception("Public query processing failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to process the query right now. Please try again later."
        )


@router.get("/stats")
def get_public_stats():
    """
    Get public system statistics.
    
    Returns basic information about the system without authentication.
    """
    from core.config import settings
    from rag.vector_store import vector_store
    
    return {
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "total_documents": vector_store.get_count() if vector_store.client else 0,
        "supported_languages": ["ka", "ru", "en"],
        "features": {
            "rag": True,
            "multilingual": True,
            "semantic_search": True,
        }
    }
