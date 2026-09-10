"""Evidence-pinned operator review. The caller owns the transaction and locks."""
from __future__ import annotations

import hashlib
import json

from fastapi import HTTPException
from sqlalchemy.orm import Session

from core.time_utils import utc_now
from models import BillingProviderEvent, BillingReviewDecision, Payment, Subscription


def digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()


def snapshot(db: Session, checkout) -> dict:
    def fields(row, names):
        return {name: (str(getattr(row, name)) if getattr(row, name) is not None else None) for name in names} if row else None

    sub = db.query(Subscription).filter_by(user_id=checkout.user_id).populate_existing().first()
    payment = db.get(Payment, checkout.settled_payment_id) if checkout.settled_payment_id else None
    events = db.query(BillingProviderEvent).filter_by(checkout_id=checkout.id).order_by(BillingProviderEvent.id).all()
    return {
        "checkout": fields(checkout, (
            "id", "user_id", "plan", "months", "amount_minor", "currency", "provider", "provider_order_id",
            "status", "provider_status", "provider_checked_at", "settled_payment_id", "updated_at", "expires_at",
            "terms_version", "terms_accepted_at", "immediate_service_requested_at",
        )),
        "subscription": fields(sub, ("id", "plan", "status", "period_start", "period_end", "updated_at")),
        "payment": fields(payment, ("id", "subscription_id", "provider", "provider_tx_id", "amount_minor", "currency", "status")),
        "events_sha256": digest({"events": [fields(event, (
            "id", "provider_status", "payload_sha256", "processing_status", "error_code", "processed_at",
        )) for event in events]}),
    }


def assert_reviewable(checkout) -> None:
    overdue = (
        checkout.provider == "tbc" and checkout.status in {"pending", "expired"}
        and not checkout.settled_payment_id and checkout.expires_at < utc_now()
        and checkout.provider_status not in {"Failed", "Expired"}
    )
    if checkout.status not in {"provider_unknown", "provider_review"} and not overdue:
        raise HTTPException(409, "Checkout is no longer awaiting review.")


def allowed_actions(db: Session, checkout, evidence: dict | None) -> dict:
    actions = {"keep_review": "unchanged"}
    if not evidence or checkout.provider != "tbc" or (
        evidence["provider_order_id"] != checkout.provider_order_id
        or evidence["amount_minor"] != checkout.amount_minor or evidence["currency"] != checkout.currency
    ):
        return actions
    existing = db.query(Payment).filter_by(provider="tbc", provider_tx_id=checkout.provider_order_id).first()
    if checkout.settled_payment_id:
        sub = db.query(Subscription).filter_by(user_id=checkout.user_id).first()
        if (evidence["status"] == "Succeeded" and existing and sub
            and existing.id == checkout.settled_payment_id and existing.subscription_id == sub.id
            and existing.amount_minor == checkout.amount_minor and existing.currency == checkout.currency
            and existing.status == "succeeded"):
            actions["confirm_payment"] = "unchanged"
        return actions
    # A missing settlement reference must never be repaired by granting again.
    broken_history = db.query(BillingProviderEvent).filter(
        BillingProviderEvent.checkout_id == checkout.id,
        ((BillingProviderEvent.error_code == "settlement_record_missing")
         | ((BillingProviderEvent.provider_status == "Succeeded") & (BillingProviderEvent.processing_status == "applied"))),
    ).first()
    prior_grant = db.query(BillingReviewDecision).filter_by(checkout_id=checkout.id, access_effect="grant_period").first()
    if existing or broken_history or prior_grant:
        return actions
    if evidence["status"] in {"Failed", "Expired"}:
        actions["confirm_no_charge"] = "unchanged"
    sub = db.query(Subscription).filter_by(user_id=checkout.user_id).first()
    other_active_plan = sub and sub.plan != "pro" and sub.period_end and sub.period_end > utc_now()
    if (evidence["status"] == "Succeeded" and checkout.plan == "pro" and 1 <= checkout.months <= 24
        and not other_active_plan
        and checkout.terms_version and checkout.terms_accepted_at and checkout.immediate_service_requested_at):
        actions["confirm_payment"] = "grant_period"
    return actions


def decision_payload(row: BillingReviewDecision) -> dict:
    return {
        "id": str(row.id), "checkout_id": str(row.checkout_id), "actor_id": str(row.actor_id),
        "action": row.action, "reason": row.reason, "access_effect": row.access_effect,
        "before": row.before, "after": row.after, "provider_evidence": row.provider_evidence,
        "created_at": row.created_at.isoformat(),
    }
