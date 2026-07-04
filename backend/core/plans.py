"""
Subscription plans: feature gates and daily quotas.

Plan resolution: admin -> business; active subscription within its period ->
its plan; otherwise free. Quotas are daily Redis counters (fail-open when
Redis is unavailable so billing never takes the chat down).
"""
from datetime import datetime, date
from typing import Optional

import redis
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.config import settings
from core.database import get_db
from core.security import get_current_user
from models import User, Subscription

PLAN_ORDER = {"free": 0, "pro": 1, "business": 2}
FREE_DAILY_QUESTIONS = 5

_redis_client: Optional[redis.Redis] = None


def _redis() -> Optional[redis.Redis]:
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        except Exception:
            return None
    return _redis_client


def get_active_plan(db: Session, user: User) -> str:
    if user.role == "admin":
        return "business"
    sub = db.query(Subscription).filter_by(user_id=user.id, status="active").first()
    if sub and sub.plan in PLAN_ORDER:
        if sub.period_end is None or sub.period_end >= datetime.utcnow():
            return sub.plan
    return "free"


def require_plan(min_plan: str):
    """Dependency factory: 402 when the user's plan is below `min_plan`."""

    def dependency(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        plan = get_active_plan(db, current_user)
        if PLAN_ORDER.get(plan, 0) < PLAN_ORDER.get(min_plan, 0):
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Эта функция доступна на тарифе {min_plan.capitalize()} и выше.",
            )
        return current_user

    return dependency


def quota_key(user_id) -> str:
    return f"quota:questions:{user_id}:{date.today().isoformat()}"


def questions_used_today(user_id) -> int:
    client = _redis()
    if client is None:
        return 0
    try:
        return int(client.get(quota_key(user_id)) or 0)
    except Exception:
        return 0


def check_and_count_question(user: User, plan: str) -> None:
    """Raise 429 when a free user exhausted the daily question quota."""
    if plan != "free":
        return
    client = _redis()
    if client is None:
        return
    try:
        key = quota_key(user.id)
        used = client.incr(key)
        if used == 1:
            client.expire(key, 172800)
        if used > FREE_DAILY_QUESTIONS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Дневной лимит тарифа Free исчерпан ({FREE_DAILY_QUESTIONS} вопросов). "
                    "Перейдите на Pro для вопросов без ограничений."
                ),
            )
    except HTTPException:
        raise
    except Exception:
        return
