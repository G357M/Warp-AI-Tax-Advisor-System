"""Admin answer-quality helpers: pseudonyms, the answer feed, detail and summary."""
import hashlib
import hmac
from dataclasses import dataclass, field
from datetime import timedelta
from statistics import median
from typing import Optional

from sqlalchemy import and_, case, cast, func, select, tuple_
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, aliased

from core.admin_users import admin_error, escape_like, iso
from core.config import settings
from core.time_utils import utc_now
from models import AnswerRating, AnswerReview, Conversation, Message, User

REVIEW_REASONS = ("not_in_corpus", "wrong_version", "wrong_citation", "fabricated", "incomplete",
                  "language", "other")
VERDICTS = ("correct", "partial", "wrong")
FLAGS = ("no_precise_citation", "no_sources", "not_grounded", "slow", "no_evidence")
SLOW_MS = 30_000
PERIOD_DAYS = {"7d": 7, "30d": 30, "90d": 90, "all": None}
PREVIEW = 200


def pseudonym(user_id) -> str:
    digest = hmac.new(settings.SECRET_KEY.encode(), str(user_id).encode(), hashlib.sha256).hexdigest()
    return "U-" + digest[:6].upper()


@dataclass
class FeedFilter:
    period: str = "7d"
    rating: Optional[str] = None
    verdict: Optional[str] = None
    flags: list = field(default_factory=list)
    q: Optional[str] = None


Question = aliased(Message)


def _question_sq():
    return (select(Question.content)
            .where(Question.conversation_id == Message.conversation_id, Question.role == "user",
                   Question.created_at <= Message.created_at)
            .order_by(Question.created_at.desc()).limit(1).correlate(Message).scalar_subquery())


def _latest_verdict_sq():
    return (select(AnswerReview.verdict).where(AnswerReview.message_id == Message.id)
            .order_by(AnswerReview.created_at.desc(), AnswerReview.id.desc()).limit(1)
            .correlate(Message).scalar_subquery())


def _ev(key):
    return Message.evidence[key]


def _flag_condition(flag):
    # evidence may be SQL NULL or a JSON null (the ORM's JSON type stores None as 'null').
    has = func.coalesce(func.jsonb_typeof(cast(Message.evidence, JSONB)), "null") == "object"
    if flag == "no_evidence":
        return ~has
    if flag == "slow":
        return Message.processing_ms > SLOW_MS
    if flag == "no_precise_citation":
        return and_(has, func.coalesce(_ev("has_precise_citation").as_boolean(), False).is_(False))
    if flag == "no_sources":
        return and_(has, func.coalesce(_ev("source_count").as_integer(), 0) == 0)
    return and_(has, func.coalesce(_ev("status").as_string(), "") != "grounded")  # not_grounded


def _conditions(filt: FeedFilter, now) -> list:
    conditions = [Message.role == "assistant"]
    days = PERIOD_DAYS[filt.period]
    if days is not None:
        conditions.append(Message.created_at >= now - timedelta(days=days))
    if filt.rating == "up":
        conditions.append(AnswerRating.value == 1)
    elif filt.rating == "down":
        conditions.append(AnswerRating.value == -1)
    elif filt.rating == "none":
        conditions.append(AnswerRating.id.is_(None))
    verdict = _latest_verdict_sq()
    if filt.verdict == "unreviewed":
        conditions.append(verdict.is_(None))
    elif filt.verdict:
        conditions.append(verdict == filt.verdict)
    for flag in filt.flags:
        conditions.append(_flag_condition(flag))
    term = (filt.q or "").strip()
    if term:
        conditions.append(_question_sq().ilike(f"%{escape_like(term)}%", escape="\\"))
    return conditions


def _base(columns, conditions):
    return (select(*columns).select_from(Message)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .outerjoin(AnswerRating, AnswerRating.message_id == Message.id)
            .where(*conditions))


def _flags_of(message) -> list:
    ev, flags = message.evidence, []
    if ev is None:
        return ["no_evidence"]
    if not ev.get("has_precise_citation"):
        flags.append("no_precise_citation")
    if not ev.get("source_count"):
        flags.append("no_sources")
    if ev.get("status") != "grounded":
        flags.append("not_grounded")
    if (message.processing_ms or 0) > SLOW_MS:
        flags.append("slow")
    return flags


def answers_page(db: Session, filt: FeedFilter, limit: int, offset: int) -> dict:
    now = utc_now()
    conditions = _conditions(filt, now)
    total = db.execute(_base([func.count()], conditions)).scalar_one()
    rows = db.execute(
        _base([Message, Conversation.user_id, _question_sq().label("question"),
               AnswerRating.value.label("rating"), _latest_verdict_sq().label("verdict")], conditions)
        .order_by(Message.created_at.desc(), Message.id.desc()).limit(limit).offset(offset)
    ).all()
    return {"total": total, "items": [{
        "message_id": str(m.id), "created_at": iso(m.created_at), "pseudonym": pseudonym(user_id),
        "question": (question or "")[:PREVIEW], "answer": m.content[:PREVIEW], "flags": _flags_of(m),
        "rating": rating, "verdict": verdict, "processing_ms": m.processing_ms,
    } for m, user_id, question, rating, verdict in rows]}


def _neighbors(db: Session, message, filt: FeedFilter) -> dict:
    conditions = _conditions(filt, utc_now())
    key = tuple_(Message.created_at, Message.id)
    current = tuple_(message.created_at, message.id)
    newer = db.execute(_base([Message.id], conditions + [key > current])
                       .order_by(Message.created_at.asc(), Message.id.asc()).limit(1)).scalar()
    older = db.execute(_base([Message.id], conditions + [key < current])
                       .order_by(Message.created_at.desc(), Message.id.desc()).limit(1)).scalar()
    return {"prev_id": str(newer) if newer else None, "next_id": str(older) if older else None}


def answer_detail(db: Session, message_id, filt: FeedFilter) -> dict:
    message = db.get(Message, message_id)
    if message is None or message.role != "assistant":
        raise admin_error(404, "message_not_found", "Message not found")
    conversation = db.get(Conversation, message.conversation_id)
    dialog = (db.query(Message).filter(Message.conversation_id == conversation.id)
              .order_by(Message.created_at, case((Message.role == "user", 0), else_=1), Message.id).all())
    rating = db.query(AnswerRating).filter_by(message_id=message.id).first()
    reviews = (db.query(AnswerReview, User.username)
               .outerjoin(User, User.id == AnswerReview.reviewer_id)
               .filter(AnswerReview.message_id == message.id)
               .order_by(AnswerReview.created_at.desc(), AnswerReview.id.desc()).all())
    return {
        "message": {"id": str(message.id), "created_at": iso(message.created_at), "content": message.content,
                    "sources": message.sources or [], "evidence": message.evidence,
                    "processing_ms": message.processing_ms, "flags": _flags_of(message)},
        "conversation": {"pseudonym": pseudonym(conversation.user_id), "messages": [
            {"id": str(m.id), "role": m.role, "content": m.content, "created_at": iso(m.created_at)}
            for m in dialog]},
        "rating": ({"value": rating.value, "comment": rating.comment, "updated_at": iso(rating.updated_at)}
                   if rating else None),
        "reviews": [{"verdict": r.verdict, "reasons": list(r.reasons or []), "note": r.note,
                     "created_at": iso(r.created_at), "reviewer": {"username": username}}
                    for r, username in reviews],
        "neighbors": _neighbors(db, message, filt),
    }


def down_unreviewed(db: Session) -> int:
    reviewed = select(AnswerReview.id).where(AnswerReview.message_id == AnswerRating.message_id).exists()
    return db.execute(select(func.count()).select_from(AnswerRating)
                      .where(AnswerRating.value == -1, ~reviewed)).scalar_one()


def quality_summary(db: Session, period: str) -> dict:
    now = utc_now()
    conditions = [Message.role == "assistant"]
    days = PERIOD_DAYS[period]
    if days is not None:
        conditions.append(Message.created_at >= now - timedelta(days=days))
    messages = db.execute(select(Message.id, Message.evidence, Message.processing_ms)
                          .where(*conditions)).all()
    ids = [m.id for m in messages]
    ratings = dict(db.execute(select(AnswerRating.message_id, AnswerRating.value)
                              .where(AnswerRating.message_id.in_(ids))).all()) if ids else {}
    latest = {}
    if ids:
        for review in db.query(AnswerReview).filter(AnswerReview.message_id.in_(ids)).order_by(
                AnswerReview.created_at, AnswerReview.id):
            latest[review.message_id] = review
    with_evidence = [m for m in messages if m.evidence is not None]
    no_cite = [m for m in with_evidence if not m.evidence.get("has_precise_citation")]
    timings = [m.processing_ms for m in messages if m.processing_ms is not None]
    rated, down = len(ratings), sum(1 for v in ratings.values() if v == -1)
    reasons = {reason: 0 for reason in REVIEW_REASONS}
    for review in latest.values():
        for reason in review.reasons or []:
            if reason in reasons:
                reasons[reason] += 1
    share = lambda part, whole: round(part / whole, 4) if whole else None  # noqa: E731
    return {
        "answers": len(messages), "rated": rated, "down": down, "down_share": share(down, rated),
        "reviewed": len(latest), "reviewed_share": share(len(latest), len(messages)),
        "verdicts": {v: sum(1 for r in latest.values() if r.verdict == v) for v in VERDICTS},
        "reasons": reasons,
        "no_precise_citation_share": share(len(no_cite), len(with_evidence)),
        "median_processing_ms": int(median(timings)) if timings else None,
        "down_unreviewed": down_unreviewed(db),
    }
