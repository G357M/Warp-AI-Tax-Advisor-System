"""Admin client management: list filters, the user card, plan grants and coded errors."""
from datetime import datetime, timedelta
from typing import Annotated, Optional

from fastapi import HTTPException
from pydantic import StringConstraints
from sqlalchemy import and_, case, func, literal, or_, select
from sqlalchemy.orm import Session

from core.plans import FREE_DAILY_QUESTIONS, questions_used_today_or_none
from core.time_utils import utc_now
from models import BillingCheckout, Conversation, Feedback, Message, Payment, Subscription, User

Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=1000)]
PAID_PLANS = ("pro", "business")
EXPIRING_DAYS = 7

STATUS_FILTERS = {
    "active": User.is_active.is_(True),
    "blocked": User.is_active.is_(False),
    "unverified": User.email_verified_at.is_(None),
    "admin": User.role == "admin",
}
SORTS = {
    "created_desc": (User.created_at.desc().nulls_last(), User.id),
    "last_login_desc": (User.last_login.desc().nulls_last(), User.id),
    "period_end_asc": (Subscription.period_end.asc().nulls_last(), User.id),
}


def admin_error(status_code: int, code: str, message: str) -> HTTPException:
    """Machine-readable admin error; the frontend localises by `code`."""
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _in_period(sub, now) -> bool:
    return sub.status == "active" and (sub.period_end is None or sub.period_end >= now)


def effective_plan(user, sub, now) -> str:
    """Same rules as core.plans.get_active_plan, without a query."""
    if user.role == "admin":
        return "business"
    if sub is not None and _in_period(sub, now):
        return sub.plan
    return "free"


def paid_subscription_active(sub, now) -> bool:
    return sub is not None and sub.plan in PAID_PLANS and _in_period(sub, now)


def _effective_plan_sql(now):
    return case(
        (User.role == "admin", literal("business")),
        (and_(Subscription.status == "active",
              or_(Subscription.period_end.is_(None), Subscription.period_end >= now)), Subscription.plan),
        else_=literal("free"),
    )


def _conditions(q, plan, status, now) -> list:
    conditions = []
    term = (q or "").strip()
    if term:
        pattern = f"%{escape_like(term)}%"
        conditions.append(or_(User.email.ilike(pattern, escape="\\"),
                              User.username.ilike(pattern, escape="\\"),
                              func.coalesce(User.full_name, "").ilike(pattern, escape="\\")))
    if plan == "expiring":
        conditions += [User.role != "admin", Subscription.status == "active", Subscription.plan.in_(PAID_PLANS),
                       Subscription.period_end >= now,
                       Subscription.period_end < now + timedelta(days=EXPIRING_DAYS)]
    elif plan:
        conditions.append(_effective_plan_sql(now) == plan)
    if status:
        conditions.append(STATUS_FILTERS[status])
    return conditions


def list_users_page(db: Session, *, q, plan, status, sort, limit, offset) -> dict:
    now = utc_now()
    conditions = _conditions(q, plan, status, now)
    join = (Subscription, Subscription.user_id == User.id)
    total = db.execute(
        select(func.count()).select_from(User).outerjoin(*join).where(*conditions)
    ).scalar_one()
    rows = db.execute(
        select(User, Subscription.period_end, _effective_plan_sql(now).label("plan"))
        .outerjoin(*join).where(*conditions)
        .order_by(*SORTS[sort]).limit(limit).offset(offset)
    ).all()
    return {"total": total, "items": [{
        "id": str(user.id), "username": user.username, "email": user.email, "role": user.role,
        "created_at": iso(user.created_at), "last_login": iso(user.last_login),
        "plan": plan_value, "period_end": iso(period_end),
        "is_active": user.is_active, "email_verified": user.email_verified,
    } for user, period_end, plan_value in rows]}


CARD_ROWS = 20


def subscription_snapshot(sub) -> Optional[dict]:
    """Access-relevant subscription fields for the admin journal; no payment data."""
    if sub is None:
        return None
    return {"plan": sub.plan, "status": sub.status, "period_end": iso(sub.period_end),
            "source": "grant" if sub.payment_provider == "grant" else "payment"}


def _activity(db: Session, user, plan: str, now) -> dict:
    d7, d30 = now - timedelta(days=7), now - timedelta(days=30)
    conversations = db.execute(
        select(func.count().filter(Conversation.created_at >= d7),
               func.count().filter(Conversation.created_at >= d30))
        .where(Conversation.user_id == user.id)
    ).one()
    questions = db.execute(
        select(func.count().filter(Message.created_at >= d7), func.count().filter(Message.created_at >= d30))
        .select_from(Message).join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.user_id == user.id, Message.role == "user")
    ).one()
    feedback_total = db.execute(
        select(func.count()).select_from(Feedback).where(Feedback.user_id == user.id)
    ).scalar_one()
    return {
        "conversations_7d": conversations[0], "conversations_30d": conversations[1],
        "questions_7d": questions[0], "questions_30d": questions[1],
        "questions_today": questions_used_today_or_none(user.id),
        "daily_limit": FREE_DAILY_QUESTIONS if plan == "free" else None,
        "feedback_total": feedback_total,
    }


def user_card(db: Session, user) -> dict:
    now = utc_now()
    sub = db.query(Subscription).filter_by(user_id=user.id).first()
    plan = effective_plan(user, sub, now)
    subscription = None
    if sub is not None:
        live = sub.status == "active" and sub.period_end is not None and sub.period_end >= now
        snapshot = subscription_snapshot(sub)
        subscription = {**snapshot, "period_start": iso(sub.period_start),
                        "days_left": max(0, (sub.period_end - now).days) if live else None}
    payments = (db.query(Payment).join(Subscription, Payment.subscription_id == Subscription.id)
                .filter(Subscription.user_id == user.id).order_by(Payment.created_at.desc()).limit(CARD_ROWS).all())
    checkouts = (db.query(BillingCheckout).filter(BillingCheckout.user_id == user.id)
                 .order_by(BillingCheckout.created_at.desc()).limit(CARD_ROWS).all())
    return {
        "profile": {
            "id": str(user.id), "username": user.username, "email": user.email, "full_name": user.full_name,
            "role": user.role, "effective_plan": plan, "is_active": user.is_active,
            "email_verified": user.email_verified, "created_at": iso(user.created_at),
            "last_login": iso(user.last_login),
        },
        "subscription": subscription,
        "payments": [{"id": str(p.id), "created_at": iso(p.created_at), "amount_minor": p.amount_minor,
                      "currency": p.currency, "provider": p.provider, "status": p.status} for p in payments],
        "checkouts": [{"id": str(c.id), "created_at": iso(c.created_at), "plan": c.plan, "months": c.months,
                       "amount_minor": c.amount_minor, "currency": c.currency, "provider": c.provider,
                       "status": c.status, "expires_at": iso(c.expires_at)} for c in checkouts],
        "activity": _activity(db, user, plan, now),
    }


def guard_active_plan(sub, plan: str, now, replace_active: bool) -> None:
    """Raise coded 409s when an admin plan action would cut short or flatten paid access."""
    if not paid_subscription_active(sub, now):
        return
    if sub.plan == plan:
        if sub.period_end is None:
            raise admin_error(409, "plan_unlimited", "The active plan has no end date")
    elif not replace_active:
        raise admin_error(409, "active_plan_differs", "Another paid plan is active")


def grant_window(sub, plan: str, days: int, now, replace_active: bool) -> tuple:
    """(period_start, period_end) for a free grant; raises coded 409s instead of losing paid time."""
    guard_active_plan(sub, plan, now, replace_active)
    if paid_subscription_active(sub, now) and sub.plan == plan:
        return sub.period_start or now, sub.period_end + timedelta(days=days)
    return now, now + timedelta(days=days)
