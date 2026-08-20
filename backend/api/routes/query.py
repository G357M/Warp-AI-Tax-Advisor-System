"""
Query processing API routes.
"""
import logging
import time
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from core.database import get_db
from core.plans import get_active_plan, check_and_count_question, refund_question, require_plan
from core.security import get_current_user
from core.time_utils import utc_now
from models import User, Conversation, Message
from api.schemas import ConversationResponse, QueryRequest, QueryResponse, SourceInfo
from api.evidence import attach_evidence
from rag.pipeline import rag_pipeline
from rag_v2.shadow_runtime import maybe_run_shadow
from rag_v2.live_runtime import maybe_run_live_rollout


router = APIRouter(prefix="/query", tags=["Query"])
logger = logging.getLogger(__name__)


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
    
    # Validate a requested conversation before reserving quota. Invalid IDs
    # must not count as questions.
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
        conversation = None

    plan = get_active_plan(db, current_user)
    check_and_count_question(current_user, plan)

    try:
        # The conversation and both messages are committed atomically. A failed
        # RAG call therefore cannot leave an empty conversation in history.
        if conversation is None:
            conversation = Conversation(
                user_id=current_user.id,
                title=query_data.query[:100],
            )
            db.add(conversation)
            db.flush()

        history_messages = db.query(Message).filter(
            Message.conversation_id == conversation.id
        ).order_by(Message.created_at.desc()).limit(10).all()
        history_messages.reverse()
        conversation_history = [
            {"role": msg.role, "content": msg.content}
            for msg in history_messages
        ]

        db.add(Message(
            conversation_id=conversation.id,
            role="user",
            content=query_data.query,
        ))

        result = maybe_run_live_rollout(
            query=query_data.query,
            language=query_data.language,
            conversation_history=conversation_history,
        )
        if result is None:
            result = rag_pipeline.process_query(
                query=query_data.query,
                conversation_history=conversation_history,
                language=query_data.language
            )

        maybe_run_shadow(
            query=query_data.query,
            language=query_data.language or "ru",
            route="/api/v1/query",
            legacy_result=result,
            extra={"surface": "authenticated", "conversation_id": str(conversation.id)},
        )
        result = attach_evidence(result)

        db.add(Message(
            conversation_id=conversation.id,
            role="assistant",
            content=result["response"],
            sources=result.get("sources", []),
        ))
        conversation.updated_at = utc_now()
        db.commit()
    except Exception:
        db.rollback()
        refund_question(current_user, plan)
        logger.exception("Authenticated query processing failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to process the query right now. Please try again later."
        )
    
    # Prepare response
    processing_time = time.time() - start_time
    
    response_data = {
        "response": result["response"],
        "sources": [SourceInfo(**src) for src in result.get("sources", [])],
        "evidence": result["evidence"],
        "conversation_id": conversation.id,
        "retrieved_count": result.get("retrieved_count", 0),
        "processing_time": processing_time
    }
    
    return response_data


@router.get("/conversations", response_model=list[ConversationResponse])
def get_conversations(
    current_user: User = Depends(require_plan("pro")),
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """Get user's conversations."""
    rows = (
        db.query(Conversation, func.count(Message.id).label("messages_count"))
        .outerjoin(Message, Message.conversation_id == Conversation.id)
        .filter(Conversation.user_id == current_user.id)
        .group_by(Conversation.id)
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    
    return [
        {
            "id": conversation.id,
            "title": conversation.title,
            "created_at": conversation.created_at,
            "updated_at": conversation.updated_at,
            "messages_count": messages_count,
        }
        for conversation, messages_count in rows
    ]


@router.get("/conversations/{conversation_id}")
def get_conversation(
    conversation_id: UUID,
    current_user: User = Depends(require_plan("pro")),
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
        "conversation": {
            "id": conversation.id,
            "title": conversation.title,
            "created_at": conversation.created_at,
            "updated_at": conversation.updated_at,
        },
        "messages": [
            {
                "id": message.id,
                "role": message.role,
                "content": message.content,
                "sources": message.sources,
                "created_at": message.created_at,
            }
            for message in messages
        ],
    }


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: UUID,
    current_user: User = Depends(require_plan("pro")),
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
