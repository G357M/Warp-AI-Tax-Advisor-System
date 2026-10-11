"""
Query processing API routes.
"""
import logging
import time
from typing import Literal, Optional
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from core.admin_users import admin_error
from core.database import get_db
from core.plans import get_active_plan, check_and_count_question, refund_question, require_plan, _redis
from core.security import get_current_user
from core.time_utils import utc_now
from models import User, Conversation, Message, AnswerRating
from api.schemas import ConversationResponse, QueryRequest, QueryResponse, SourceInfo
from api.evidence import attach_evidence
from rag_v2.legal_answer_contracts import ensure_exact_provision_citations
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
        result = ensure_exact_provision_citations(result, query_data.language)

        assistant_id = uuid4()
        db.add(Message(
            id=assistant_id,
            conversation_id=conversation.id,
            role="assistant",
            content=result["response"],
            sources=result.get("sources", []),
            evidence={**dict(result["evidence"]), "retrieved_count": int(result.get("retrieved_count") or 0)},
            processing_ms=max(0, int((time.time() - start_time) * 1000)),
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
        "message_id": assistant_id,
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

    ratings = {r.message_id: r for r in db.query(AnswerRating).filter(
        AnswerRating.message_id.in_([m.id for m in messages if m.role == "assistant"])).all()}

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
                "rating": ({"value": ratings[message.id].value, "comment": ratings[message.id].comment}
                           if message.id in ratings else None),
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


RATING_LIMIT_PER_HOUR = 60


class RatingRequest(BaseModel):
    value: Literal[1, -1]
    comment: Optional[str] = Field(default=None, max_length=1000)


def rating_rate_limited(user_id) -> bool:
    """True when the user exceeded RATING_LIMIT_PER_HOUR changes; no Redis -> no limit."""
    client = _redis()
    if client is None:
        return False
    key = f"rating:{user_id}:{utc_now().strftime('%Y%m%d%H')}"
    try:
        count = client.incr(key)
        if count == 1:
            client.expire(key, 3600)
        return count > RATING_LIMIT_PER_HOUR
    except Exception:
        return False


def _owned_assistant_message(db: Session, user: User, message_id: UUID) -> Message:
    message = (db.query(Message).join(Conversation, Message.conversation_id == Conversation.id)
               .filter(Message.id == message_id, Conversation.user_id == user.id).first())
    if message is None:
        raise admin_error(404, "message_not_found", "Message not found")
    if message.role != "assistant":
        raise admin_error(409, "not_assistant_message", "Only assistant answers can be rated")
    return message


def _check_rating_limit(user: User) -> None:
    if rating_rate_limited(user.id):
        raise admin_error(429, "rating_rate_limited", "Too many rating changes, try again later")


@router.put(
    "/messages/{message_id}/rating",
    responses={
        404: {"description": "Message not found"},
        409: {"description": "Only assistant answers can be rated"},
        429: {"description": "Too many rating changes"},
    },
)
def rate_answer(message_id: UUID, body: RatingRequest, current_user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    _check_rating_limit(current_user)
    message = _owned_assistant_message(db, current_user, message_id)
    comment = (body.comment or "").strip() or None
    rating = db.query(AnswerRating).filter_by(message_id=message.id).first()
    if rating is None:
        rating = AnswerRating(message_id=message.id, user_id=current_user.id, value=body.value, comment=comment)
        db.add(rating)
    else:
        rating.value, rating.comment = body.value, comment
    db.commit()
    return {"value": rating.value, "comment": rating.comment}


@router.delete(
    "/messages/{message_id}/rating",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        404: {"description": "Message not found"},
        409: {"description": "Only assistant answers can be rated"},
        429: {"description": "Too many rating changes"},
    },
)
def unrate_answer(message_id: UUID, current_user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    _check_rating_limit(current_user)
    message = _owned_assistant_message(db, current_user, message_id)
    db.query(AnswerRating).filter_by(message_id=message.id).delete()
    db.commit()
