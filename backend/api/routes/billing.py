"""Billing catalog, checkout lifecycle, provider verification and settlement."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import timedelta
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from billing.catalog import (
    LEGAL_TERMS_VERSION,
    PLAN_CATALOG,
    get_plan,
    public_catalog,
)
from billing.gateway import (
    GatewayUnavailable,
    ProviderPayment,
    ProviderRequestError,
    get_gateway,
    payment_methods,
)
from billing.review import allowed_actions, assert_reviewable, decision_payload, digest, snapshot
from core.config import settings
from core.database import get_db
from core.plans import get_active_plan
from core.security import get_current_user, require_admin
from core.time_utils import utc_now
from models import BillingCheckout, BillingProviderEvent, BillingReviewDecision, Payment, Subscription, User

router = APIRouter(prefix="/billing", tags=["Billing"])

IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


class CheckoutRequest(BaseModel):
    plan: str = Field(pattern="^(pro|business)$")
    provider: Literal["manual", "tbc"] = "manual"
    language: Literal["ka", "ru", "en"] = "en"
    terms_version: Literal[LEGAL_TERMS_VERSION]
    terms_accepted: Literal[True]
    immediate_service_requested: Literal[True]


class ProviderCallback(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    payment_id: str = Field(alias="PaymentId", min_length=1, max_length=128)


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


class ReviewDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action: Literal["keep_review", "confirm_payment", "confirm_no_charge"]
    reason: str = Field(min_length=10, max_length=2000)
    expected_state_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_provider_sha256: Optional[str] = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    expected_access_effect: Literal["unchanged", "grant_period"]


def _checkout_payload(row: BillingCheckout) -> dict:
    return {
        "id": str(row.id),
        "plan": row.plan,
        "months": row.months,
        "amount_minor": row.amount_minor,
        "currency": row.currency,
        "provider": row.provider,
        "status": row.status,
        "provider_status": row.provider_status,
        "provider_redirect_url": row.provider_redirect_url,
        "provider_checked_at": (
            row.provider_checked_at.isoformat() if row.provider_checked_at else None
        ),
        "terms_version": row.terms_version,
        "terms_accepted_at": (
            row.terms_accepted_at.isoformat() if row.terms_accepted_at else None
        ),
        "immediate_service_requested_at": (
            row.immediate_service_requested_at.isoformat()
            if row.immediate_service_requested_at
            else None
        ),
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


def _available_gateway(provider: str):
    try:
        return get_gateway(provider)
    except GatewayUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail="Selected payment provider is not available.",
        ) from exc


def _stored_payment_method(checkout: BillingCheckout) -> dict:
    if checkout.provider == "manual":
        return get_gateway("manual").create_checkout(
            checkout,
            None,
            get_plan(checkout.plan),
            "en",
        )
    if checkout.provider == "tbc" and checkout.provider_redirect_url:
        return {
            "provider": "tbc",
            "method_id": "tbc_checkout",
            "status": "available",
            "instruction_code": "redirect_to_bank",
            "contact_email": None,
            "redirect_url": checkout.provider_redirect_url,
            "provider_order_id": checkout.provider_order_id,
            "provider_status": checkout.provider_status,
        }
    raise HTTPException(
        status_code=409,
        detail="Checkout requires payment reconciliation before it can be retried.",
    )


@router.get("/catalog")
def billing_catalog():
    """Public, non-secret catalog used by pricing and the client cabinet."""
    return {**public_catalog(), "payment_methods": payment_methods()}


def _reconciliation_payload(row: BillingCheckout) -> dict:
    """Minimal operator evidence; no email, bank redirect or raw payload."""
    reason = None
    if row.status in {"provider_unknown", "provider_review"}:
        reason = row.status
    elif (
        row.provider == "tbc" and row.status in {"pending", "expired"}
        and not row.settled_payment_id and row.expires_at < utc_now()
        and row.provider_status not in {"Failed", "Expired"}
    ):
        reason = "payment_verification_overdue"
    return {
        "id": str(row.id),
        "user_id": str(row.user_id),
        "plan": row.plan,
        "amount_minor": row.amount_minor,
        "currency": row.currency,
        "provider": row.provider,
        "provider_order_id": row.provider_order_id,
        "status": row.status,
        "provider_status": row.provider_status,
        "reason": reason,
        "settled_payment_id": str(row.settled_payment_id) if row.settled_payment_id else None,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        "expires_at": row.expires_at.isoformat(),
        "provider_checked_at": (
            row.provider_checked_at.isoformat() if row.provider_checked_at else None
        ),
    }


@router.get("/admin/reconciliation")
def reconciliation_queue(
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Read-only worklist, including orders whose final callback never arrived."""
    del admin
    rows = (
        db.query(BillingCheckout)
        .filter(or_(
            BillingCheckout.status.in_(("provider_unknown", "provider_review")),
            and_(
                BillingCheckout.provider == "tbc",
                BillingCheckout.status.in_(("pending", "expired")),
                BillingCheckout.settled_payment_id.is_(None),
                BillingCheckout.expires_at < utc_now(),
                or_(
                    BillingCheckout.provider_status.is_(None),
                    BillingCheckout.provider_status.notin_(("Failed", "Expired")),
                ),
            ),
        ))
        .order_by(BillingCheckout.created_at.asc(), BillingCheckout.id.asc())
        .offset(offset)
        .limit(limit + 1)
        .all()
    )
    return {
        "items": [_reconciliation_payload(row) for row in rows[:limit]],
        "next_offset": offset + limit if len(rows) > limit else None,
    }


@router.get("/admin/reconciliation/{checkout_id}")
def reconciliation_detail(
    checkout_id: UUID,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Bounded verified-event history; reading it never calls a bank or settles."""
    del admin
    checkout = db.get(BillingCheckout, checkout_id)
    if not checkout:
        raise HTTPException(status_code=404, detail="Checkout not found")
    events = (
        db.query(BillingProviderEvent)
        .filter_by(checkout_id=checkout_id)
        .order_by(BillingProviderEvent.created_at.desc(), BillingProviderEvent.id.desc())
        .limit(51)
        .all()
    )
    return {
        "checkout": _reconciliation_payload(checkout),
        "events": [
            {
                "id": str(event.id),
                "provider_status": event.provider_status,
                "payload_sha256": event.payload_sha256,
                "processing_status": event.processing_status,
                "error_code": event.error_code,
                "created_at": event.created_at.isoformat(),
                "processed_at": (
                    event.processed_at.isoformat() if event.processed_at else None
                ),
            }
            for event in events[:50]
        ],
        "events_truncated": len(events) > 50,
    }


def _review_checkout(db: Session, checkout_id: UUID) -> BillingCheckout:
    checkout = db.query(BillingCheckout).filter_by(id=checkout_id).populate_existing().with_for_update().first()
    if not checkout:
        raise HTTPException(404, "Checkout not found")
    # Same lock order as callback settlement, including first subscription creation.
    db.query(User).filter_by(id=checkout.user_id).with_for_update().one()
    return checkout


def _review_bank_evidence(checkout: BillingCheckout) -> dict:
    if checkout.provider != "tbc" or not checkout.provider_order_id:
        raise HTTPException(409, "No verifiable bank order is recorded.")
    try:
        payment = _available_gateway("tbc").get_payment(checkout.provider_order_id)
    except (GatewayUnavailable, ProviderRequestError) as exc:
        raise HTTPException(503, "Bank verification is unavailable. No decision was recorded.") from exc
    return {
        "provider_order_id": payment.provider_order_id, "status": payment.status,
        "amount_minor": payment.amount_minor, "currency": payment.currency,
    }


@router.get("/admin/reconciliation/{checkout_id}/decisions")
def review_history(
    checkout_id: UUID, limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
    admin: User = Depends(require_admin), db: Session = Depends(get_db),
):
    del admin
    if not db.get(BillingCheckout, checkout_id):
        raise HTTPException(404, "Checkout not found")
    rows = db.query(BillingReviewDecision).filter_by(checkout_id=checkout_id).order_by(
        BillingReviewDecision.created_at.desc(), BillingReviewDecision.id.desc(),
    ).offset(offset).limit(limit + 1).all()
    return {"items": [decision_payload(row) for row in rows[:limit]],
            "next_offset": offset + limit if len(rows) > limit else None}


@router.post("/admin/reconciliation/{checkout_id}/preview")
def review_preview(
    checkout_id: UUID, verify_provider: bool = Query(default=False),
    admin: User = Depends(require_admin), db: Session = Depends(get_db),
):
    del admin
    checkout = _review_checkout(db, checkout_id)
    assert_reviewable(checkout)
    evidence = _review_bank_evidence(checkout) if verify_provider else None
    state = snapshot(db, checkout)
    return {
        "state_sha256": digest(state), "provider_sha256": digest(evidence) if evidence else None,
        "provider_evidence": evidence, "before": state,
        "actions": allowed_actions(db, checkout, evidence),
    }


@router.post("/admin/reconciliation/{checkout_id}/decisions")
def record_review_decision(
    checkout_id: UUID, body: ReviewDecisionRequest,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    admin: User = Depends(require_admin), db: Session = Depends(get_db),
):
    if not IDEMPOTENCY_KEY_RE.fullmatch(idempotency_key):
        raise HTTPException(422, "Invalid Idempotency-Key")
    checkout = _review_checkout(db, checkout_id)
    request_hash = digest(body.model_dump())
    existing = db.query(BillingReviewDecision).filter_by(
        checkout_id=checkout_id, idempotency_key=idempotency_key,
    ).first()
    if existing:
        if existing.actor_id != admin.id or existing.request_sha256 != request_hash:
            raise HTTPException(409, "Idempotency key is already bound to another decision.")
        return {"decision": decision_payload(existing), "replayed": True}
    assert_reviewable(checkout)
    before = snapshot(db, checkout)
    if digest(before) != body.expected_state_sha256:
        raise HTTPException(409, "Recorded evidence changed. Prepare a new preview.")
    evidence = None
    if body.action != "keep_review":
        evidence = _review_bank_evidence(checkout)
        if digest(evidence) != body.expected_provider_sha256:
            raise HTTPException(409, "Bank evidence changed. Prepare a new preview.")
    effect = allowed_actions(db, checkout, evidence).get(body.action)
    if effect is None or effect != body.expected_access_effect:
        raise HTTPException(409, "This decision or access effect is not supported by the evidence.")
    now = utc_now()
    if body.action == "keep_review":
        checkout.status = "provider_review"
    else:
        checkout.provider_status = evidence["status"]
        checkout.provider_checked_at = now
        if body.action == "confirm_payment":
            if effect == "grant_period":
                _settle_checkout(db, db.get(User, checkout.user_id), checkout, "tbc", checkout.provider_order_id)
            else:
                checkout.status = "paid"
        else:
            checkout.status = "failed" if evidence["status"] == "Failed" else "expired"
    checkout.updated_at = now
    try:
        db.flush()
        decision = BillingReviewDecision(
            checkout_id=checkout.id, actor_id=admin.id, idempotency_key=idempotency_key,
            request_sha256=request_hash, action=body.action, reason=body.reason,
            access_effect=effect, before=before, after=snapshot(db, checkout),
            provider_evidence=evidence,
        )
        db.add(decision)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Concurrent settlement conflict. Reload the evidence.") from exc
    return {"decision": decision_payload(decision), "replayed": False}


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
                "amount_minor": payment.amount_minor,
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
    """Persist a server-priced intent before creating any remote bank order."""
    if not IDEMPOTENCY_KEY_RE.fullmatch(idempotency_key):
        raise HTTPException(
            status_code=422,
            detail="Idempotency-Key must be 8-128 URL-safe characters",
        )

    plan = get_plan(body.plan)
    gateway = _available_gateway(body.provider)
    existing = (
        db.query(BillingCheckout)
        .filter_by(user_id=current_user.id, idempotency_key=idempotency_key)
        .first()
    )
    if existing:
        if (
            existing.plan != body.plan
            or existing.provider != body.provider
            or existing.terms_version != body.terms_version
            or existing.terms_accepted_at is None
            or existing.immediate_service_requested_at is None
        ):
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
            "payment_method": _stored_payment_method(existing),
            "replayed": True,
        }

    now = utc_now()
    ttl = (
        timedelta(hours=settings.BILLING_MANUAL_CHECKOUT_TTL_HOURS)
        if body.provider == "manual"
        else timedelta(minutes=settings.TBC_CHECKOUT_EXPIRATION_MINUTES)
    )
    checkout = BillingCheckout(
        user_id=current_user.id,
        plan=plan.id,
        months=1,
        amount_minor=plan.price_minor,
        currency=plan.currency,
        provider=body.provider,
        status="pending",
        idempotency_key=idempotency_key,
        expires_at=now + ttl,
        terms_version=body.terms_version,
        terms_accepted_at=now,
        immediate_service_requested_at=now,
    )
    db.add(checkout)
    try:
        db.commit()
        db.refresh(checkout)
    except IntegrityError:
        # A concurrent retry may win the unique constraint. Never create a
        # second provider order from the losing request.
        db.rollback()
        checkout = (
            db.query(BillingCheckout)
            .filter_by(user_id=current_user.id, idempotency_key=idempotency_key)
            .one()
        )
        if (
            checkout.plan != body.plan
            or checkout.provider != body.provider
            or checkout.terms_version != body.terms_version
            or checkout.terms_accepted_at is None
            or checkout.immediate_service_requested_at is None
        ):
            raise HTTPException(
                status_code=409,
                detail="Idempotency-Key already belongs to another checkout",
            )
        if checkout.provider == "tbc" and not checkout.provider_redirect_url:
            raise HTTPException(
                status_code=409,
                detail="Checkout creation is already in progress.",
            )
        return {
            "checkout": _checkout_payload(checkout),
            "payment_method": _stored_payment_method(checkout),
            "replayed": True,
        }

    try:
        method = gateway.create_checkout(checkout, current_user, plan, body.language)
    except ProviderRequestError as exc:
        checkout.status = "provider_unknown"
        checkout.provider_status = exc.code
        checkout.provider_checked_at = utc_now()
        checkout.updated_at = utc_now()
        db.commit()
        raise HTTPException(
            status_code=502,
            detail=(
                "Payment provider did not confirm order creation; "
                "no automatic retry was attempted."
            ),
        ) from exc

    if body.provider == "tbc":
        checkout.provider_order_id = method["provider_order_id"]
        checkout.provider_status = method["provider_status"]
        checkout.provider_redirect_url = method["redirect_url"]
        checkout.provider_checked_at = utc_now()
        checkout.expires_at = now + timedelta(minutes=method["expires_in_minutes"])
        checkout.updated_at = utc_now()
        try:
            db.commit()
            db.refresh(checkout)
        except IntegrityError as exc:
            db.rollback()
            saved = db.get(BillingCheckout, checkout.id)
            if saved:
                saved.status = "provider_unknown"
                saved.provider_status = "duplicate_provider_order"
                saved.updated_at = utc_now()
                db.commit()
            raise HTTPException(
                status_code=502,
                detail="Provider returned a conflicting order identifier.",
            ) from exc

    return {
        "checkout": _checkout_payload(checkout),
        "payment_method": method,
        "replayed": False,
    }


def _settle_checkout(
    db: Session,
    user: User,
    checkout: BillingCheckout,
    provider: str,
    provider_tx_id: Optional[str],
) -> Payment:
    now = utc_now()
    # Serialize every settlement for a user, including the first one before a
    # subscription row exists. Two different paid checkouts must never lose a
    # month by updating the same entitlement concurrently.
    locked_user = (
        db.query(User)
        .filter(User.id == user.id)
        .with_for_update()
        .one()
    )
    sub = (
        db.query(Subscription)
        .filter_by(user_id=locked_user.id)
        .with_for_update()
        .first()
    )
    base = now
    if sub and sub.period_end and sub.period_end > now and sub.plan == checkout.plan:
        base = sub.period_end
    period_end = base + timedelta(days=30 * checkout.months)

    if sub is None:
        sub = Subscription(user_id=locked_user.id)
        db.add(sub)
    sub.plan = checkout.plan
    sub.status = "active"
    sub.period_start = now
    sub.period_end = period_end
    sub.payment_provider = provider
    sub.auto_renew = False

    db.flush()
    payment = Payment(
        subscription_id=sub.id,
        amount_gel=checkout.amount_minor / 100,
        amount_minor=checkout.amount_minor,
        currency=checkout.currency,
        provider=provider,
        provider_tx_id=provider_tx_id,
        status="succeeded",
    )
    db.add(payment)
    db.flush()

    checkout.status = "paid"
    checkout.settled_payment_id = payment.id
    checkout.updated_at = now
    return payment


def _normalized_payment_digest(payment: ProviderPayment) -> str:
    raw = json.dumps(
        {
            "amount_minor": payment.amount_minor,
            "currency": payment.currency,
            "provider_order_id": payment.provider_order_id,
            "status": payment.status,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(raw).hexdigest()


def _reconcile_tbc_payment(
    db: Session,
    checkout: BillingCheckout,
    payment: ProviderPayment,
) -> dict:
    now = utc_now()
    checkout.provider_status = payment.status
    checkout.provider_checked_at = now
    checkout.updated_at = now

    event_id = f"{payment.provider_order_id}:{payment.status}"
    existing_event = (
        db.query(BillingProviderEvent)
        .filter_by(provider="tbc", event_id=event_id)
        .first()
    )
    if existing_event:
        if existing_event.payload_sha256 != _normalized_payment_digest(payment):
            checkout.status = "provider_review"
            existing_event.processing_status = "error"
            existing_event.error_code = "event_digest_mismatch"
            existing_event.processed_at = now
            db.commit()
            db.refresh(checkout)
            return {
                "accepted": True,
                "replayed": False,
                "checkout": _checkout_payload(checkout),
            }
        if checkout.settled_payment_id and payment.status != "Succeeded":
            checkout.status = "provider_review"
            existing_event.processing_status = "review"
            existing_event.error_code = "settled_payment_state_conflict"
            existing_event.processed_at = now
        elif checkout.status == "paid" and not checkout.settled_payment_id:
            checkout.status = "provider_review"
            existing_event.processing_status = "error"
            existing_event.error_code = "settlement_record_missing"
            existing_event.processed_at = now
        db.commit()
        return {
            "accepted": True,
            "replayed": True,
            "checkout": _checkout_payload(checkout),
        }

    event = BillingProviderEvent(
        checkout_id=checkout.id,
        provider="tbc",
        event_id=event_id,
        provider_status=payment.status,
        payload_sha256=_normalized_payment_digest(payment),
        processing_status="received",
    )
    db.add(event)

    if payment.provider_order_id != checkout.provider_order_id:
        checkout.status = "provider_review"
        event.processing_status = "error"
        event.error_code = "provider_order_mismatch"
    elif payment.amount_minor != checkout.amount_minor:
        checkout.status = "provider_review"
        event.processing_status = "error"
        event.error_code = "amount_mismatch"
    elif payment.currency != checkout.currency:
        checkout.status = "provider_review"
        event.processing_status = "error"
        event.error_code = "currency_mismatch"
    elif checkout.status == "provider_review":
        # A later observation must not erase an unresolved conflict or refund.
        # Only a separately audited operator decision can release this hold.
        event.processing_status = "review"
        event.error_code = "checkout_requires_review"
    elif checkout.settled_payment_id:
        # Settlement identity is durable even if a prior observation changed
        # the display status. Never create another entitlement for this order.
        if payment.status == "Succeeded":
            checkout.status = "paid"
            event.processing_status = "ignored"
        else:
            checkout.status = "provider_review"
            event.processing_status = "review"
            event.error_code = "settled_payment_state_conflict"
    elif checkout.status == "paid":
        checkout.status = "provider_review"
        event.processing_status = "error"
        event.error_code = "settlement_record_missing"
    elif payment.status == "Succeeded":
        user = db.get(User, checkout.user_id)
        if not user:
            checkout.status = "provider_review"
            event.processing_status = "error"
            event.error_code = "checkout_user_missing"
        else:
            _settle_checkout(db, user, checkout, "tbc", payment.provider_order_id)
            event.processing_status = "applied"
    elif payment.status == "Failed":
        checkout.status = "failed"
        event.processing_status = "applied"
    elif payment.status == "Expired":
        checkout.status = "expired"
        event.processing_status = "applied"
    elif payment.status in {"Returned", "PartialReturned", "WaitingConfirm"}:
        # Refunds and the unexpected pre-authorization state require a human
        # decision; access is never silently revoked or extended here.
        checkout.status = "provider_review"
        event.processing_status = "review"
        event.error_code = "provider_state_requires_review"
    else:
        checkout.status = "pending"
        event.processing_status = "observed"

    event.processed_at = now
    db.commit()
    db.refresh(checkout)
    return {
        "accepted": True,
        "replayed": False,
        "checkout": _checkout_payload(checkout),
    }


@router.post("/providers/tbc/callback")
def tbc_callback(body: ProviderCallback, db: Session = Depends(get_db)):
    """Acknowledge a known payId only after authoritative bank verification."""
    gateway = _available_gateway("tbc")
    known = (
        db.query(BillingCheckout.id)
        .filter_by(provider="tbc", provider_order_id=body.payment_id)
        .first()
    )
    if not known:
        # Unknown IDs trigger no outbound request and reveal no order state.
        return {"accepted": True, "ignored": True}
    try:
        payment = gateway.get_payment(body.payment_id)
    except ProviderRequestError as exc:
        raise HTTPException(
            status_code=503,
            detail="Payment status could not be verified.",
        ) from exc
    checkout = (
        db.query(BillingCheckout)
        .filter(BillingCheckout.id == known[0])
        .with_for_update()
        .one()
    )
    return _reconcile_tbc_payment(db, checkout, payment)


@router.post("/checkout/{checkout_id}/refresh")
def refresh_checkout(
    checkout_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reconcile a client's known TBC order after the browser returns."""
    checkout = (
        db.query(BillingCheckout)
        .filter(
            BillingCheckout.id == checkout_id,
            BillingCheckout.user_id == current_user.id,
        )
        .with_for_update()
        .first()
    )
    if not checkout:
        raise HTTPException(status_code=404, detail="Checkout not found")
    if checkout.provider != "tbc" or not checkout.provider_order_id:
        raise HTTPException(status_code=409, detail="Checkout has no online payment to refresh")
    if checkout.status == "paid" and checkout.settled_payment_id:
        return {"accepted": True, "replayed": True, "checkout": _checkout_payload(checkout)}

    gateway = _available_gateway("tbc")
    try:
        payment = gateway.get_payment(checkout.provider_order_id)
    except ProviderRequestError as exc:
        raise HTTPException(
            status_code=503,
            detail="Payment status could not be verified.",
        ) from exc
    return _reconcile_tbc_payment(db, checkout, payment)


@router.post("/admin/activate")
def activate_subscription(
    body: ActivateRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Settle a manual checkout, or use the temporary legacy email workflow."""
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
        if checkout.provider != "manual":
            raise HTTPException(
                status_code=409,
                detail="Online checkouts must be settled from verified provider status.",
            )
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
                "status": sub.status,
                "period_end": sub.period_end.isoformat() if sub.period_end else None,
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
        payment = _settle_checkout(db, user, checkout, "manual", None)
        db.commit()
        return {
            "email": user.email,
            "plan": checkout.plan,
            "status": "active",
            "period_end": (
                db.query(Subscription).filter_by(user_id=user.id).one().period_end.isoformat()
            ),
            "checkout_id": str(checkout.id),
            "payment_id": str(payment.id),
            "replayed": False,
        }

    email = (body.email or "").strip().lower()
    user = db.query(User).filter_by(email=email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User with this email not found")
    plan = PLAN_CATALOG[body.plan or ""]
    now = utc_now()
    legacy_checkout = BillingCheckout(
        user_id=user.id,
        plan=plan.id,
        months=body.months,
        amount_minor=plan.price_minor * body.months,
        currency=plan.currency,
        provider="manual",
        status="pending",
        idempotency_key=f"legacy-admin:{now.timestamp()}:{user.id}",
        expires_at=now + timedelta(hours=1),
    )
    db.add(legacy_checkout)
    db.flush()
    payment = _settle_checkout(db, user, legacy_checkout, "manual", None)
    db.commit()
    sub = db.query(Subscription).filter_by(user_id=user.id).one()
    return {
        "email": user.email,
        "plan": sub.plan,
        "status": sub.status,
        "period_end": sub.period_end.isoformat() if sub.period_end else None,
        "checkout_id": str(legacy_checkout.id),
        "payment_id": str(payment.id),
        "replayed": False,
    }
