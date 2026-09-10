"""Real PostgreSQL locks, rollback and immutable journal, in a disposable schema."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from core.config import settings
from core.database import Base, engine
from core.time_utils import utc_now
from models import BillingCheckout, BillingProviderEvent, BillingReviewDecision, Payment, Subscription, User
from scripts.add_billing_review_journal import apply_schema, contract_sha256

pytestmark = pytest.mark.skipif(os.getenv("BILLING_PROVIDER_POSTGRES_TESTS") != "1", reason="requires dedicated PostgreSQL")


@pytest.fixture
def database():
    schema = "billing_review_test_" + uuid4().hex
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    local = create_engine(settings.DATABASE_URL, connect_args={"options": f"-csearch_path={schema}"})
    tables = [m.__table__ for m in (User, Subscription, Payment, BillingCheckout, BillingProviderEvent)]
    Base.metadata.create_all(local, tables=tables)
    with local.begin() as conn:
        assert apply_schema(conn) == apply_schema(conn)
    session = sessionmaker(bind=local, autoflush=False)
    with session() as db:
        user = User(email=f"{uuid4()}@example.test", username=uuid4().hex, password_hash="test", role="admin")
        db.add(user)
        db.flush()
        checkout = BillingCheckout(user_id=user.id, plan="pro", months=1, amount_minor=4900, currency="GEL",
            provider="tbc", provider_order_id=uuid4().hex, status="provider_review", idempotency_key=uuid4().hex,
            expires_at=utc_now() + timedelta(minutes=12), terms_version="2026-09-08",
            terms_accepted_at=utc_now(), immediate_service_requested_at=utc_now())
        db.add(checkout)
        db.commit()
        ids = user.id, checkout.id
    yield session, ids
    local.dispose()
    # The identifier is generated here, never supplied by an environment/user.
    with engine.begin() as conn:
        conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


def prepare(database, monkeypatch):
    # The integration harness imports routes without loading RAG models.
    from tests.test_integration import billing
    from billing.gateway import ProviderPayment
    sessions, (user_id, checkout_id) = database
    with sessions() as db:
        order_id = db.get(BillingCheckout, checkout_id).provider_order_id
    class Bank:
        def get_payment(self, order):
            assert order == order_id
            return ProviderPayment(order, "Succeeded", 4900, "GEL")
    monkeypatch.setattr(billing, "get_gateway", lambda _: Bank())
    with sessions() as db:
        preview = billing.review_preview(checkout_id, True, db.get(User, user_id), db)
    body = billing.ReviewDecisionRequest(action="confirm_payment", reason="Verified in a synthetic bank fixture.",
        expected_state_sha256=preview["state_sha256"], expected_provider_sha256=preview["provider_sha256"],
        expected_access_effect="grant_period")
    return billing, body


@pytest.mark.parametrize("same_key", [True, False])
def test_concurrent_decisions_credit_once(database, monkeypatch, same_key):
    billing, body = prepare(database, monkeypatch)
    sessions, (user_id, checkout_id) = database
    barrier, key = Barrier(2), uuid4().hex
    def decide(index):
        with sessions() as db:
            actor = db.get(User, user_id)
            barrier.wait(timeout=10)
            try:
                return billing.record_review_decision(checkout_id, body, key if same_key else f"{key}-{index}", actor, db)
            except HTTPException as exc:
                return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(decide, [0, 1]))
    if same_key:
        assert sorted(result["replayed"] for result in results) == [False, True]
        assert results[0]["decision"] == results[1]["decision"]
    else:
        assert sum(result == 409 for result in results) == 1
    with sessions() as db:
        assert db.query(Payment).count() == db.query(BillingReviewDecision).count() == 1
        assert db.query(Subscription).one().period_end < utc_now() + timedelta(days=31)


def test_journal_failure_rolls_back_payment_and_access(database, monkeypatch):
    billing, body = prepare(database, monkeypatch)
    sessions, (user_id, checkout_id) = database
    def reject(*_args):
        raise RuntimeError("synthetic journal write failure")
    event.listen(BillingReviewDecision, "before_insert", reject)
    try:
        with sessions() as db, pytest.raises(RuntimeError, match="synthetic journal"):
            billing.record_review_decision(checkout_id, body, uuid4().hex, db.get(User, user_id), db)
    finally:
        event.remove(BillingReviewDecision, "before_insert", reject)
    with sessions() as db:
        assert db.query(Payment).count() == db.query(Subscription).count() == db.query(BillingReviewDecision).count() == 0
        assert db.get(BillingCheckout, checkout_id).status == "provider_review"


@pytest.mark.parametrize("sql", ["UPDATE billing_review_decisions SET reason = 'rewritten'",
    "DELETE FROM billing_review_decisions", "TRUNCATE billing_review_decisions"])
def test_journal_is_immutable(database, monkeypatch, sql):
    assert contract_sha256() == "51ea189e55a2127a0d13bb0a60233714f6adeba4d8458371ae286d12a3bef610"
    billing, body = prepare(database, monkeypatch)
    sessions, (user_id, checkout_id) = database
    with sessions() as db:
        billing.record_review_decision(checkout_id, body, uuid4().hex, db.get(User, user_id), db)
    with sessions() as db, pytest.raises(DBAPIError, match="immutable"):
        db.execute(text(sql))
    with sessions() as db:
        assert db.query(BillingReviewDecision).one().reason == body.reason
