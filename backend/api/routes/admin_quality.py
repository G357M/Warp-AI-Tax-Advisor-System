"""Admin answer quality: pseudonymous feed, detail, review, reveal and summary.
All endpoints require the admin role."""
from typing import List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from core.admin_audit import record_admin_action
from core.admin_users import Reason, admin_error
from core.admin_quality import FeedFilter, answer_detail, answers_page, quality_summary
from core.database import get_db
from core.security import require_admin
from models import AnswerReview, Conversation, Message, User

router = APIRouter(prefix="/admin/quality", tags=["Admin"], dependencies=[Depends(require_admin)])

Period = Literal["7d", "30d", "90d", "all"]
RatingFilter = Literal["up", "down", "none"]
VerdictFilter = Literal["unreviewed", "correct", "partial", "wrong"]
Flag = Literal["no_precise_citation", "no_sources", "not_grounded", "slow", "no_evidence"]


def _filter(period, rating, verdict, flags, q) -> FeedFilter:
    return FeedFilter(period=period, rating=rating, verdict=verdict, flags=list(dict.fromkeys(flags or [])), q=q)


@router.get("/answers")
def list_answers(
    period: Period = "7d",
    rating: Optional[RatingFilter] = None,
    verdict: Optional[VerdictFilter] = None,
    flags: List[Flag] = Query(default=[]),
    q: Optional[str] = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    return answers_page(db, _filter(period, rating, verdict, flags, q), limit, offset)


@router.get("/answers/{message_id}", responses={404: {"description": "Message not found"}})
def get_answer(
    message_id: UUID,
    period: Period = "7d",
    rating: Optional[RatingFilter] = None,
    verdict: Optional[VerdictFilter] = None,
    flags: List[Flag] = Query(default=[]),
    q: Optional[str] = Query(default=None, max_length=200),
    db: Session = Depends(get_db),
):
    return answer_detail(db, message_id, _filter(period, rating, verdict, flags, q))


@router.get("/summary")
def get_summary(period: Period = "7d", db: Session = Depends(get_db)):
    return quality_summary(db, period)


ReviewReason = Literal["not_in_corpus", "wrong_version", "wrong_citation", "fabricated", "incomplete",
                       "language", "other"]


class ReviewRequest(BaseModel):
    verdict: Literal["correct", "partial", "wrong"]
    reasons: List[ReviewReason] = Field(default_factory=list, max_length=7)
    note: Optional[str] = Field(default=None, max_length=2000)
    reason: Reason

    @field_validator("reasons")
    @classmethod
    def unique_reasons(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("reasons must be unique")
        return value


class RevealRequest(BaseModel):
    reason: Reason


def _assistant_message(db: Session, message_id: UUID) -> Message:
    message = db.get(Message, message_id)
    if message is None or message.role != "assistant":
        raise admin_error(404, "message_not_found", "Message not found")
    return message


@router.post("/answers/{message_id}/review", responses={404: {"description": "Message not found"}})
def review_answer(message_id: UUID, body: ReviewRequest, admin: User = Depends(require_admin),
                  db: Session = Depends(get_db)):
    message = _assistant_message(db, message_id)
    note = (body.note or "").strip() or None
    db.add(AnswerReview(message_id=message.id, reviewer_id=admin.id, verdict=body.verdict,
                        reasons=list(body.reasons), note=note))
    db.flush()
    record_admin_action(db, actor=admin, action="answer.reviewed", target_type="message", target_id=message.id,
                        after={"verdict": body.verdict, "reasons": list(body.reasons)}, reason=body.reason)
    db.commit()
    return answer_detail(db, message.id, FeedFilter(period="all"))


@router.post("/answers/{message_id}/reveal-user", responses={404: {"description": "Message not found"}})
def reveal_user(message_id: UUID, body: RevealRequest, admin: User = Depends(require_admin),
                db: Session = Depends(get_db)):
    message = _assistant_message(db, message_id)
    user_id = db.get(Conversation, message.conversation_id).user_id
    record_admin_action(db, actor=admin, action="user.identity_revealed", target_type="message",
                        target_id=message.id, after={"user_id": str(user_id)}, reason=body.reason)
    db.commit()
    return {"user_id": str(user_id)}
