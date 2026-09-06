"""Billing catalog, persisted checkout intents, and manual settlement."""
import re
from datetime import timedelta
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from billing.catalog import PLAN_CATALOG, get_plan, public_catalog
from billing.gateway import get_gateway, payment_methods
from core.config import settings
from core.database import get_db
from core.plans import get_active_plan
from core.security import get_current_user, require_admin
from core.time_utils import utc_now
from models import BillingCheckout, Payment, Subscription, User

router = APIRouter(prefix="/billing", tags=["Billing"])

IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


class CheckoutRequest(BaseModel):
    plan: str = Field(pattern="^(pro|business)$")
    provider: Literal["manual"] = "manual"


class ActivateRequest(BaseModel):
    checkout_id: Optional[UUID] = None
    email: Optional[str] = None
    plan: Optional[str] = Field(default=None, pattern="^(pro|business)$")
    months: int = Field(default=1, ge=1, le=24)

    @model_validator(mode="after")
    def require_checkout_or_legacy_identity(self) -> "ActivateRequest":
        if self.checkout_id is None and (not self.email or not self.plan):
            raise ValueError("checkout_id or both email and plan are required")
        return self


def _checkout_payload(row: BillingCheckout) -> dict:
    return {
        "id": str(row.id),
        "plan": row.plan,
        "months": row.months,
        "amount_minor": row.amount_minor,
        "currency": row.currency,
        "provider": row.provider,
        "status": row.status,
        "expires_at": row.expires_at.isoformat(),
        "created_at": row.created_at.isoformat(),
    }


def _subscription_payload(db: Session, user: User) -> dict:
    plan = get_active_plan(db, user)
    sub = db.query(Subscription).filter_by(user_id=user.id).first()
    return {
        "plan": plan,
        "status": sub.status if sub else None,
        "period_start": sub.period_start.isoformat() if sub and sub.period_start else None,
        "period_end": sub.period_end.isoformat() if sub and sub.period_end else None,
        "auto_renew": sub.auto_renew if sub else False,
        "payment_provider": sub.payment_provider if sub else None,
    }


def _mark_expired_checkouts(db: Session, user_id) -> None:
    now = utc_now()
    expired = (
        db.query(BillingCheckout)
        .filter(
            BillingCheckout.user_id == user_id,
            BillingCheckout.status == "pending",
            BillingCheckout.expires_at < now,
        )
        .all()
    )
    if not expired:
        return
    for checkout in expired:
        checkout.status = "expired"
        checkout.updated_at = now
    db.commit()


@router.get("/catalog")
def billing_catalog():
    """Public, non-secret catalog used by pricing and the client cabinet."""
    return {**public_catalog(), "payment_methods": payment_methods()}


@router.get("/subscription")
def my_subscription(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Backward-compatible compact subscription response."""
    return _subscription_payload(db, current_user)


@router.get("/overview")
def billing_overview(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """One client-cabinet read model with no sensitive provider payloads."""
    _mark_expired_checkouts(db, current_user.id)
    checkouts = (
        db.query(BillingCheckout)
        .filter_by(user_id=current_user.id)
        .order_by(BillingCheckout.created_at.desc())
        .limit(20)
        .all()
    )
    payments = (
        db.query(Payment)
        .join(Subscription, Payment.subscription_id == Subscription.id)
        .filter(Subscription.user_id == current_user.id)
        .order_by(Payment.created_at.desc())
        .limit(20)
        .all()
    )
    return {
        "subscription": _subscription_payload(db, current_user),
        "checkouts": [_checkout_payload(row) for row in checkouts],
        "payments": [
            {
                "id": str(payment.id),
                "amount_minor": int(round(payment.amount_gel * 100)),
                "currency": payment.currency,
                "provider": payment.provider,
                "status": payment.status,
                "created_at": payment.created_at.isoformat(),
            }
            for payment in payments
        ],
        "payment_methods": payment_methods(include_contact=True),
    }


@router.post("/checkout")
def create_checkout(
    body: CheckoutRequest,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Persist a server-priced payment intent; safe to repeat with one key."""
    if not IDEMPOTENCY_KEY_RE.fullmatch(idempotency_key):
        raise HTTPException(
            status_code=422,
            detail="Idempotency-Key must be 8-128 URL-safe characters",
        )

    plan = get_plan(body.plan)
    gateway = get_gateway(body.provider)
    existing = (
        db.query(BillingCheckout)
        .filter_by(user_id=current_user.id, idempotency_key=idempotency_key)
        .first()
    )
    if existing:
        if existing.plan != body.plan or existing.provider != body.provider:
            raise HTTPException(
                status_code=409,
                detail="Idempotency-Key already belongs to another checkout",
            )
        if existing.status == "pending" and existing.expires_at < utc_now():
            existing.status = "expired"
            existing.updated_at = utc_now()
            db.commit()
            raise HTTPException(
                status_code=409,
                detail="Checkout has expired; create a new request",
            )
        return {
            "checkout": _checkout_payload(existing),
            "payment_method": gateway.create_checkout(current_user, plan),
            "replayed": True,
        }

    now = utc_now()
    checkout = BillingCheckout(
        user_id=current_user.id,
        plan=plan.id,
        months=1,
        amount_minor=plan.price_minor,
        currency=plan.currency,
        provider=body.provider,
        status="pending",
        idempotency_key=idempotency_key,
        expires_at=now + timedelta(hours=settings.BILLING_MANUAL_CHECKOUT_TTL_HOURS),
    )
    db.add(checkout)
    try:
        db.commit()
        db.refresh(checkout)
    except IntegrityError:
        # A concurrent retry may win the unique constraint.  Return its row
        # only when it represents the exact same checkout request.
        db.rollback()
        checkout = (
            db.query(BillingCheckout)
            .filter_by(user_id=current_user.id, idempotency_key=idempotency_key)
            .one()
        )
        if checkout.plan != body.plan or checkout.provider != body.provider:
            raise HTTPException(
                status_code=409,
                detail="Idempotency-Key already belongs to another checkout",
            )
        return {
            "checkout": _checkout_payload(checkout),
            "payment_method": gateway.create_checkout(current_user, plan),
            "replayed": True,
        }

    return {
        "checkout": _checkout_payload(checkout),
        "payment_method": gateway.create_checkout(current_user, plan),
        "replayed": False,
    }


def _activate(
    db: Session,
    user: User,
    plan_id: str,
    months: int,
    amount_minor: int,
    checkout: Optional[BillingCheckout],
) -> dict:
    now = utc_now()
    sub = db.query(Subscription).filter_by(user_id=user.id).first()
    base = now
    if sub and sub.period_end and sub.period_end > now and sub.plan == plan_id:
        base = sub.period_end
    period_end = base + timedelta(days=30 * months)

    if sub is None:
        sub = Subscription(user_id=user.id)
        db.add(sub)
    sub.plan = plan_id
    sub.status = "active"
    sub.period_start = now
    sub.period_end = period_end
    sub.payment_provider = "manual"
    sub.auto_renew = False

    db.flush()
    payment = Payment(
        subscription_id=sub.id,
        amount_gel=amount_minor / 100,
        currency="GEL",
        provider="manual",
        status="succeeded",
    )
    db.add(payment)
    db.flush()

    if checkout is not None:
        checkout.status = "paid"
        checkout.settled_payment_id = payment.id
        checkout.updated_at = now

    db.commit()
    return {
        "email": user.email,
        "plan": sub.plan,
        "status": sub.status,
        "period_end": sub.period_end.isoformat(),
        "checkout_id": str(checkout.id) if checkout else None,
        "payment_id": str(payment.id),
        "replayed": False,
    }


@router.post("/admin/activate")
def activate_subscription(
    body: ActivateRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Settle a checkout, or use the temporary legacy email workflow."""
    del admin
    if body.checkout_id is not None:
        checkout = (
            db.query(BillingCheckout)
            .filter(BillingCheckout.id == body.checkout_id)
            .with_for_update()
            .first()
        )
        if not checkout:
            raise HTTPException(status_code=404, detail="Checkout not found")
        user = db.get(User, checkout.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="Checkout user not found")
        if checkout.status == "paid":
            sub = db.query(Subscription).filter_by(user_id=user.id).first()
            if not sub or not checkout.settled_payment_id:
                raise HTTPException(
                    status_code=409,
                    detail="Paid checkout is missing settlement records",
                )
            return {
                "email": user.email,
                "plan": checkout.plan,
                "status": sub.status if sub else "active",
                "period_end": sub.period_end.isoformat() if sub and sub.period_end else None,
                "checkout_id": str(checkout.id),
                "payment_id": str(checkout.settled_payment_id),
                "replayed": True,
            }
        if checkout.status != "pending":
            raise HTTPException(status_code=409, detail="Checkout is not pending")
        if checkout.expires_at < utc_now():
            checkout.status = "expired"
            checkout.updated_at = utc_now()
            db.commit()
            raise HTTPException(status_code=409, detail="Checkout has expired")
        return _activate(
            db,
            user,
            checkout.plan,
            checkout.months,
            checkout.amount_minor,
            checkout,
        )

    email = (body.email or "").strip().lower()
    user = db.query(User).filter_by(email=email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User with this email not found")
    plan = PLAN_CATALOG[body.plan or ""]
    return _activate(
        db,
        user,
        plan.id,
        body.months,
        plan.price_minor * body.months,
        None,
    )
