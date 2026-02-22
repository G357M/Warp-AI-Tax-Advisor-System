"""
Query processing API routes.
"""
import time
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.database import get_db
from core.security import get_current_user
from core.cache import cache_get, cache_set
from models import User, Conversation, Message
from api.schemas import QueryRequest, QueryResponse, SourceInfo
from rag.pipeline import rag_pipeline


router = APIRouter(prefix="/query", tags=["Query"])


@router.post("", response_model=QueryResponse)
def process_query(
    query_data: QueryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Process user query using RAG pipeline.
    
    This endpoint:
    1. Checks cache for similar queries
    2. Retrieves relevant documents from vector store
    3. Generates response using LLM
    4. Saves conversation to database
    5. Returns response with sources
    """
    start_time = time.time()
    
    # Check cache
    cache_key = f"query:{hash(query_data.query)}:{query_data.language}"
    cached_response = cache_get(cache_key)
    if cached_response:
        return cached_response
    
    # Get or create conversation
    if query_data.conversation_id:
        conversation = db.query(Conversation).filter(
            Conversation.id == query_data.conversation_id,
            Conversation.user_id == current_user.id
        ).first()
        
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found"
            )
    else:
        # Create new conversation
        conversation = Conversation(
            user_id=current_user.id,
            title=query_data.query[:100]  # Use first 100 chars as title
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
    
    # Get conversation history
    history_messages = db.query(Message).filter(
        Message.conversation_id == conversation.id
    ).order_by(Message.created_at).limit(10).all()
    
    conversation_history = [
        {"role": msg.role, "content": msg.content}
        for msg in history_messages
    ]
    
    # Save user message
    user_message = Message(
        conversation_id=conversation.id,
        role="user",
        content=query_data.query
    )
    db.add(user_message)
    
    # Process query through RAG pipeline
    try:
        result = rag_pipeline.process_query(
            query=query_data.query,
            conversation_history=conversation_history,
            language=query_data.language
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing query: {str(e)}"
        )
    
    # Save assistant message
    assistant_message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=result["response"],
        sources=result.get("sources", [])
    )
    db.add(assistant_message)
    db.commit()
    
    # Prepare response
    processing_time = time.time() - start_time
    
    response_data = {
        "response": result["response"],
        "sources": [SourceInfo(**src) for src in result.get("sources", [])],
        "conversation_id": conversation.id,
        "retrieved_count": result.get("retrieved_count", 0),
        "processing_time": processing_time
    }
    
    # Cache response
    cache_set(cache_key, response_data, ttl=3600)  # 1 hour
    
    return response_data


@router.get("/conversations", response_model=list)
def get_conversations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 50,
    offset: int = 0
):
    """Get user's conversations."""
    conversations = db.query(Conversation).filter(
        Conversation.user_id == current_user.id
    ).order_by(Conversation.updated_at.desc()).limit(limit).offset(offset).all()
    
    return conversations


@router.get("/conversations/{conversation_id}")
def get_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get specific conversation with messages."""
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == current_user.id
    ).first()
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    messages = db.query(Message).filter(
        Message.conversation_id == conversation_id
    ).order_by(Message.created_at).all()
    
    return {
        "conversation": conversation,
        "messages": messages
    }


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete conversation."""
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == current_user.id
    ).first()
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    db.delete(conversation)
    db.commit()
    
    return None
