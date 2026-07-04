"""
Billing: subscription state, checkout, and manual activation by an admin.
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from billing.gateway import get_gateway, PLAN_PRICES_GEL
from core.database import get_db
from core.plans import get_active_plan
from core.security import get_current_user, require_admin
from models import User, Subscription, Payment

router = APIRouter(prefix="/billing", tags=["Billing"])


class CheckoutRequest(BaseModel):
    plan: str = Field(pattern="^(pro|business)$")


class ActivateRequest(BaseModel):
    email: str
    plan: str = Field(pattern="^(pro|business)$")
    months: int = Field(default=1, ge=1, le=24)
    amount_gel: Optional[float] = None


@router.get("/subscription")
def my_subscription(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    plan = get_active_plan(db, current_user)
    sub = db.query(Subscription).filter_by(user_id=current_user.id).first()
    return {
        "plan": plan,
        "status": sub.status if sub else None,
        "period_end": sub.period_end.isoformat() if sub and sub.period_end else None,
        "payment_provider": sub.payment_provider if sub else None,
    }


@router.post("/checkout")
def create_checkout(
    body: CheckoutRequest,
    current_user: User = Depends(get_current_user),
):
    gateway = get_gateway()
    try:
        return gateway.create_checkout(current_user, body.plan)
    except NotImplementedError:
        # merchant creds exist but the API call is not wired yet — fall back
        from billing.gateway import ManualGateway
        return ManualGateway().create_checkout(current_user, body.plan)


@router.post("/admin/activate")
def activate_subscription(
    body: ActivateRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Manual activation/extension after an invoice payment (ManualGateway)."""
    user = db.query(User).filter_by(email=body.email.strip().lower()).first()
    if not user:
        raise HTTPException(status_code=404, detail="User with this email not found")

    now = datetime.utcnow()
    sub = db.query(Subscription).filter_by(user_id=user.id).first()
    base = now
    if sub and sub.period_end and sub.period_end > now and sub.plan == body.plan:
        base = sub.period_end  # extension stacks on the current period
    period_end = base + timedelta(days=30 * body.months)

    if sub is None:
        sub = Subscription(user_id=user.id)
        db.add(sub)
    sub.plan = body.plan
    sub.status = "active"
    sub.period_start = now
    sub.period_end = period_end
    sub.payment_provider = "manual"

    db.flush()
    db.add(Payment(
        subscription_id=sub.id,
        amount_gel=body.amount_gel if body.amount_gel is not None else PLAN_PRICES_GEL[body.plan] * body.months,
        provider="manual",
        status="succeeded",
    ))
    db.commit()
    return {
        "email": user.email,
        "plan": sub.plan,
        "status": sub.status,
        "period_end": sub.period_end.isoformat(),
    }
