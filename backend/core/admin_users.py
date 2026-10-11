"""Admin client management: list filters, the user card, plan grants and coded errors."""
from datetime import datetime, timedelta
from typing import Annotated, Optional

from fastapi import HTTPException
from pydantic import StringConstraints
from sqlalchemy import and_, case, func, literal, or_, select
from sqlalchemy.orm import Session

from core.time_utils import utc_now
from models import Subscription, User

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
