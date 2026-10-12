"""Admin trends: Tbilisi-local time series and the previous-window comparison (read-only)."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import and_, case, distinct, func, or_, select
from sqlalchemy.orm import Session

from core.admin_quality import flag_condition, has_evidence
from models import AnswerRating, Conversation, Message, Payment, Subscription, User

# Georgia has stayed on UTC+4 without daylight saving since 2005; timestamps are naive UTC.
TBILISI_OFFSET = timedelta(hours=4)
PERIODS = {"30d": ("day", 30), "90d": ("week", 13), "12m": ("month", 12)}
TOTAL_KEYS = ("signups", "askers", "questions", "payments", "revenue_minor", "up", "down")
CONTENT_FLAGS = ("no_precise_citation", "no_sources", "not_grounded", "slow")


def _floor(d: date, bucket: str) -> date:
    if bucket == "week":
        return d - timedelta(days=d.weekday())
    if bucket == "month":
        return d.replace(day=1)
    return d


def _step(d: date, bucket: str, n: int) -> date:
    if bucket == "day":
        return d + timedelta(days=n)
    if bucket == "week":
        return d + timedelta(weeks=n)
    month = d.year * 12 + d.month - 1 + n
    return date(month // 12, month % 12 + 1, 1)


def _utc(d: date) -> datetime:
    return datetime.combine(d, datetime.min.time()) - TBILISI_OFFSET


@dataclass(frozen=True)
class Window:
    bucket: str
    starts: list
    end: date
    previous_start: date


def window(period: str, now: datetime) -> Window:
    bucket, count = PERIODS[period]
    last = _floor((now + TBILISI_OFFSET).date(), bucket)
    first = _step(last, bucket, -(count - 1))
    return Window(bucket, [_step(first, bucket, i) for i in range(count)],
                  _step(last, bucket, 1), _step(first, bucket, -count))


def _sources() -> dict:
    """name -> (created_at column, aggregate columns, filters). Admin accounts are excluded everywhere."""
    owner = and_(Conversation.id == Message.conversation_id, User.id == Conversation.user_id, User.role != "admin")
    flagged = and_(has_evidence(), or_(*(flag_condition(f) for f in CONTENT_FLAGS)))
    return {
        "users": (User.created_at, [func.count(User.id).label("signups")], [User.role != "admin"]),
        "questions": (Message.created_at,
                      [func.count(Message.id).label("questions"),
                       func.count(distinct(Conversation.user_id)).label("askers")],
                      [Message.role == "user", owner]),
        "payments": (Payment.created_at,
                     [func.count(Payment.id).label("payments"),
                      func.coalesce(func.sum(Payment.amount_minor), 0).label("revenue_minor")],
                     [Payment.status == "succeeded", Subscription.id == Payment.subscription_id,
                      User.id == Subscription.user_id, User.role != "admin"]),
        "ratings": (AnswerRating.created_at,
                    [func.coalesce(func.sum(case((AnswerRating.value == 1, 1), else_=0)), 0).label("up"),
                     func.coalesce(func.sum(case((AnswerRating.value == -1, 1), else_=0)), 0).label("down")],
                    [User.id == AnswerRating.user_id, User.role != "admin"]),
        "answers": (Message.created_at,
                    [func.count(Message.id).label("answers"),
                     func.count(Message.id).filter(has_evidence()).label("answers_with_evidence"),
                     func.count(Message.id).filter(flagged).label("flagged"),
                     func.percentile_cont(0.5).within_group(Message.processing_ms).label("median_processing_ms")],
                    [Message.role == "assistant", owner]),
    }


def _query(db: Session, source, lo: datetime, hi: datetime, bucket: str | None = None):
    created, columns, where = source
    stmt = select(*columns).where(*where, created >= lo, created < hi)
    if bucket:
        key = func.date_trunc(bucket, created + TBILISI_OFFSET).label("bucket")
        stmt = stmt.add_columns(key).group_by(key)
    return db.execute(stmt).mappings().all()


def _int(value):
    return None if value is None else int(value)


def _totals(db: Session, sources: dict, lo: datetime, hi: datetime) -> dict:
    out = {}
    for name in ("users", "questions", "payments", "ratings"):
        out.update({k: int(v or 0) for k, v in _query(db, sources[name], lo, hi)[0].items()})
    return {k: out[k] for k in TOTAL_KEYS}


def _empty_bucket(start: date, partial: bool) -> dict:
    return {"start": start.isoformat(), "partial": partial, "signups": 0, "askers": 0, "questions": 0,
            "payments": 0, "revenue_minor": 0, "up": 0, "down": 0, "answers": 0, "answers_with_evidence": 0,
            "flagged": 0, "median_processing_ms": None}


def trends(db: Session, period: str, now: datetime) -> dict:
    w = window(period, now)
    sources = _sources()
    lo, hi = _utc(w.starts[0]), _utc(w.end)
    buckets = {s: _empty_bucket(s, s == w.starts[-1]) for s in w.starts}
    for source in sources.values():
        for row in _query(db, source, lo, hi, w.bucket):
            slot = buckets.get(row["bucket"].date())
            if slot is not None:
                slot.update({k: _int(v) for k, v in row.items() if k != "bucket"})
    # The previous window lasts as long as the elapsed part of the current one, so a
    # partial last bucket is compared fairly rather than against a full one.
    previous_lo = _utc(w.previous_start)
    first_evidence = db.execute(select(func.min(Message.created_at)).where(
        Message.role == "assistant", has_evidence(), Conversation.id == Message.conversation_id,
        User.id == Conversation.user_id, User.role != "admin")).scalar()
    return {
        "period": period, "bucket": w.bucket, "timezone": "Asia/Tbilisi",
        "quality_since": (first_evidence + TBILISI_OFFSET).date().isoformat() if first_evidence else None,
        "median_processing_ms": _int(_query(db, sources["answers"], lo, hi)[0]["median_processing_ms"]),
        "buckets": [buckets[s] for s in w.starts],
        "totals": {"current": _totals(db, sources, lo, hi),
                   "previous": _totals(db, sources, previous_lo, previous_lo + (now - lo))},
    }
