"""Admin answer quality: pseudonymous feed, detail, review, reveal and summary.
All endpoints require the admin role."""
from typing import List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from core.admin_quality import FeedFilter, answer_detail, answers_page, quality_summary
from core.database import get_db
from core.security import require_admin

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
