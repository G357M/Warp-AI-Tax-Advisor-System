"""Current API integration tests using an isolated in-memory database."""

from datetime import timedelta
from types import ModuleType, SimpleNamespace
import sys
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.time_utils import utc_now

# API route imports must stay deterministic in CI: the real RAG modules load a
# multi-gigabyte embedding model and verify pgvector at import time. Integration
# tests replace only that external boundary and exercise the real API/database
# behavior around it.
rag_package = ModuleType("rag")
rag_package.__path__ = []
rag_pipeline_module = ModuleType("rag.pipeline")
rag_pipeline_module.rag_pipeline = SimpleNamespace(
    process_query=lambda **_kwargs: (_ for _ in ()).throw(
        AssertionError("RAG must be mocked by the test")
    )
)
shadow_module = ModuleType("rag_v2.shadow_runtime")
shadow_module.maybe_run_shadow = lambda **_kwargs: None
live_module = ModuleType("rag_v2.live_runtime")
live_module.maybe_run_live_rollout = lambda **_kwargs: None
public_response_module = ModuleType("rag_v2.public_response")
public_response_module.is_pure_refusal = lambda _text: False
_stubbed_rag_modules = {
    "rag": rag_package,
    "rag.pipeline": rag_pipeline_module,
    "rag_v2.shadow_runtime": shadow_module,
    "rag_v2.live_runtime": live_module,
    "rag_v2.public_response": public_response_module,
}
_missing_module = object()
_original_rag_modules = {
    name: sys.modules.get(name, _missing_module) for name in _stubbed_rag_modules
}
sys.modules.update(_stubbed_rag_modules)

from api.routes import account, auth, billing, query as query_routes
from core.config import settings
from core.database import Base, get_db
from models import (
    AuthActionToken,
    BillingCheckout,
    BillingProviderEvent,
    BillingReviewDecision,
    Conversation,
    Message,
    Payment,
    Subscription,
    User,
)

CHECKOUT_CONSENT = {
    "terms_version": "2026-09-08",
    "terms_accepted": True,
    "immediate_service_requested": True,
}

# The imported API modules retain the lightweight boundaries above. Restore the
# process module registry so later-collected tests load the real RAG v2 package.
for _name, _module in _original_rag_modules.items():
    if _module is _missing_module:
        sys.modules.pop(_name, None)
    else:
        sys.modules[_name] = _module


app = FastAPI()
app.include_router(auth.router, prefix=settings.API_PREFIX)
app.include_router(query_routes.router, prefix=settings.API_PREFIX)
app.include_router(billing.router, prefix=settings.API_PREFIX)
app.include_router(account.router, prefix=settings.API_PREFIX)


@app.get("/")
def root():
    return {"status": "running"}


@app.get("/health")
def health():
    return {"status": "healthy"}


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
TEST_TABLES = [
    User.__table__,
    AuthActionToken.__table__,
    Conversation.__table__,
    Message.__table__,
    Subscription.__table__,
    Payment.__table__,
    BillingCheckout.__table__,
    BillingProviderEvent.__table__,
    BillingReviewDecision.__table__,
]


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="module", autouse=True)
def isolated_database():
    Base.metadata.create_all(engine, tables=TEST_TABLES)
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)
    Base.metadata.drop_all(engine, tables=list(reversed(TEST_TABLES)))


@pytest.fixture()
def client():
    test_client = TestClient(app)
    yield test_client
    test_client.close()


def register_and_login(client: TestClient, username: str) -> None:
    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"{username}@example.com",
            "username": username,
            "password": "safe-password-123",
        },
    )
    assert register.status_code == 201

    login = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "safe-password-123"},
    )
    assert login.status_code == 200
    assert login.json()["token_type"] == "bearer"
    assert client.cookies.get("ta_session")


def test_health_contract(client):
    assert client.get("/").json()["status"] == "running"
    assert client.get("/health").json()["status"] == "healthy"


def test_cookie_session_authenticates_account(client):
    register_and_login(client, "account-user")

    response = client.get("/api/v1/account")

    assert response.status_code == 200
    assert response.json()["username"] == "account-user"
    assert response.json()["plan"] == "free"


def test_billing_catalog_is_public_and_marks_unwired_banks_unavailable(client):
    client.cookies.clear()

    response = client.get("/api/v1/billing/catalog")

    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == "2026-09-08"
    assert payload["terms_version"] == "2026-09-08"
    assert payload["legal_urls"] == {
        "terms": "/legal/terms",
        "refunds": "/legal/refunds",
        "privacy": "/legal/privacy",
        "delivery": "/legal/delivery",
        "contact": "/legal/contact",
    }
    assert payload["currency_minor_unit"] == 2
    assert {plan["id"]: plan["price_minor"] for plan in payload["plans"]} == {
        "free": 0,
        "pro": 4900,
        "business": 14900,
    }
    assert all(plan["pricing_preliminary"] is False for plan in payload["plans"])
    methods = {method["provider"]: method for method in payload["payment_methods"]}
    assert methods["manual"]["status"] == "available"
    assert methods["manual"]["contact_email"] is None
    assert methods["tbc"]["status"] == "requires_merchant_activation"
    assert methods["bog"]["status"] == "requires_merchant_activation"


def test_checkout_is_server_priced_persisted_and_idempotent(client):
    register_and_login(client, "checkout-user")
    headers = {"Idempotency-Key": "checkout-user-pro-001"}

    created = client.post(
        "/api/v1/billing/checkout",
        headers=headers,
        json={"plan": "pro", "provider": "manual", **CHECKOUT_CONSENT},
    )

    assert created.status_code == 200
    payload = created.json()
    assert payload["replayed"] is False
    assert payload["checkout"]["amount_minor"] == 4900
    assert payload["checkout"]["currency"] == "GEL"
    assert payload["checkout"]["status"] == "pending"
    assert payload["checkout"]["terms_version"] == "2026-09-08"
    assert payload["checkout"]["terms_accepted_at"] is not None
    assert payload["checkout"]["immediate_service_requested_at"] is not None
    assert payload["payment_method"]["instruction_code"] == "contact_for_invoice"

    replay = client.post(
        "/api/v1/billing/checkout",
        headers=headers,
        json={"plan": "pro", "provider": "manual", **CHECKOUT_CONSENT},
    )
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert replay.json()["checkout"]["id"] == payload["checkout"]["id"]

    conflict = client.post(
        "/api/v1/billing/checkout",
        headers=headers,
        json={"plan": "business", "provider": "manual", **CHECKOUT_CONSENT},
    )
    assert conflict.status_code == 409

    overview = client.get("/api/v1/billing/overview")
    assert overview.status_code == 200
    assert overview.json()["checkouts"][0]["id"] == payload["checkout"]["id"]

    db = TestingSessionLocal()
    try:
        assert db.query(BillingCheckout).filter_by(plan="pro").count() >= 1
    finally:
        db.close()


def test_checkout_requires_current_terms_and_explicit_immediate_service_request(client):
    register_and_login(client, "checkout-consent-user")

    missing = client.post(
        "/api/v1/billing/checkout",
        headers={"Idempotency-Key": "checkout-consent-missing-001"},
        json={"plan": "pro", "provider": "manual"},
    )
    stale = client.post(
        "/api/v1/billing/checkout",
        headers={"Idempotency-Key": "checkout-consent-stale-001"},
        json={
            "plan": "pro",
            "provider": "manual",
            **CHECKOUT_CONSENT,
            "terms_version": "2026-09-07",
        },
    )
    no_immediate_start = client.post(
        "/api/v1/billing/checkout",
        headers={"Idempotency-Key": "checkout-consent-false-001"},
        json={
            "plan": "pro",
            "provider": "manual",
            **CHECKOUT_CONSENT,
            "immediate_service_requested": False,
        },
    )

    assert missing.status_code == 422
    assert stale.status_code == 422
    assert no_immediate_start.status_code == 422
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter_by(username="checkout-consent-user").one()
        assert db.query(BillingCheckout).filter_by(user_id=user.id).count() == 0
    finally:
        db.close()


def test_admin_checkout_settlement_is_idempotent(client):
    customer_username = "settlement-customer"
    register_and_login(client, customer_username)
    checkout_response = client.post(
        "/api/v1/billing/checkout",
        headers={"Idempotency-Key": "settlement-customer-pro-001"},
        json={"plan": "pro", **CHECKOUT_CONSENT},
    )
    checkout_id = checkout_response.json()["checkout"]["id"]

    admin_username = "settlement-admin"
    register_and_login(client, admin_username)
    db = TestingSessionLocal()
    admin_user = db.query(User).filter_by(username=admin_username).one()
    admin_user.role = "admin"
    db.commit()
    db.close()

    activated = client.post(
        "/api/v1/billing/admin/activate",
        json={"checkout_id": checkout_id},
    )
    assert activated.status_code == 200
    assert activated.json()["replayed"] is False
    assert activated.json()["plan"] == "pro"

    replay = client.post(
        "/api/v1/billing/admin/activate",
        json={"checkout_id": checkout_id},
    )
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert replay.json()["payment_id"] == activated.json()["payment_id"]

    db = TestingSessionLocal()
    try:
        customer = db.query(User).filter_by(username=customer_username).one()
        subscription = db.query(Subscription).filter_by(user_id=customer.id).one()
        assert subscription.plan == "pro"
        assert db.query(Payment).filter_by(subscription_id=subscription.id).count() == 1
        checkout = db.get(BillingCheckout, UUID(checkout_id))
        assert checkout.status == "paid"
        assert str(checkout.settled_payment_id) == activated.json()["payment_id"]
        payment = db.query(Payment).filter_by(subscription_id=subscription.id).one()
        assert payment.amount_minor == 4900
    finally:
        db.close()


def test_tbc_checkout_is_unavailable_without_explicit_merchant_activation(client):
    register_and_login(client, "tbc-disabled-user")

    response = client.post(
        "/api/v1/billing/checkout",
        headers={"Idempotency-Key": "tbc-disabled-checkout-001"},
        json={"plan": "pro", "provider": "tbc", "language": "ka", **CHECKOUT_CONSENT},
    )

    assert response.status_code == 503
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter_by(username="tbc-disabled-user").one()
        assert db.query(BillingCheckout).filter_by(user_id=user.id).count() == 0
    finally:
        db.close()


def test_verified_tbc_status_settles_once_and_records_only_a_digest(
    client,
    monkeypatch,
):
    from billing.gateway import ProviderPayment

    class FakeTBCGateway:
        amount_minor = 4900

        def create_checkout(self, checkout, _user, _plan, language):
            assert language == "ka"
            return {
                "provider": "tbc",
                "method_id": "tbc_checkout",
                "status": "available",
                "instruction_code": "redirect_to_bank",
                "contact_email": None,
                "redirect_url": "https://tpay.tbcbank.ge/checkout/test-pay-001",
                "provider_order_id": "test-pay-001",
                "provider_status": "Created",
                "expires_in_minutes": 12,
            }

        def get_payment(self, provider_order_id):
            assert provider_order_id == "test-pay-001"
            return ProviderPayment(
                provider_order_id=provider_order_id,
                status="Succeeded",
                amount_minor=self.amount_minor,
                currency="GEL",
            )

    real_get_gateway = billing.get_gateway
    monkeypatch.setattr(
        billing,
        "get_gateway",
        lambda provider="manual": FakeTBCGateway()
        if provider == "tbc"
        else real_get_gateway(provider),
    )
    register_and_login(client, "tbc-success-user")

    created = client.post(
        "/api/v1/billing/checkout",
        headers={"Idempotency-Key": "tbc-success-checkout-001"},
        json={"plan": "pro", "provider": "tbc", "language": "ka", **CHECKOUT_CONSENT},
    )
    assert created.status_code == 200
    checkout_id = created.json()["checkout"]["id"]
    assert created.json()["payment_method"]["redirect_url"].startswith(
        "https://tpay.tbcbank.ge/"
    )

    refreshed = client.post(f"/api/v1/billing/checkout/{checkout_id}/refresh")
    assert refreshed.status_code == 200
    assert refreshed.json()["checkout"]["status"] == "paid"

    duplicate_callback = client.post(
        "/api/v1/billing/providers/tbc/callback",
        json={"PaymentId": "test-pay-001"},
    )
    assert duplicate_callback.status_code == 200
    assert duplicate_callback.json()["replayed"] is True

    FakeTBCGateway.amount_minor = 5000
    conflicting_callback = client.post(
        "/api/v1/billing/providers/tbc/callback",
        json={"PaymentId": "test-pay-001"},
    )
    assert conflicting_callback.status_code == 200
    assert conflicting_callback.json()["replayed"] is False
    assert conflicting_callback.json()["checkout"]["status"] == "provider_review"

    db = TestingSessionLocal()
    try:
        checkout = db.get(BillingCheckout, UUID(checkout_id))
        assert checkout.provider_status == "Succeeded"
        assert db.query(Payment).filter_by(provider="tbc").count() == 1
        event = db.query(BillingProviderEvent).filter_by(checkout_id=checkout.id).one()
        assert event.processing_status == "error"
        assert len(event.payload_sha256) == 64
        assert event.error_code == "event_digest_mismatch"
    finally:
        db.close()


def test_free_account_cannot_read_conversation_history(client):
    register_and_login(client, "free-history-user")

    response = client.get("/api/v1/query/conversations")

    assert response.status_code == 402


def test_pro_query_persists_answer_sources_and_supports_deletion(client, monkeypatch):
    username = "pro-history-user"
    register_and_login(client, username)

    db = TestingSessionLocal()
    user = db.query(User).filter(User.username == username).one()
    db.add(Subscription(
        user_id=user.id,
        plan="pro",
        status="active",
        period_start=utc_now(),
        period_end=utc_now() + timedelta(days=30),
    ))
    db.commit()
    db.close()

    monkeypatch.setattr(query_routes, "check_and_count_question", lambda *_args: None)
    monkeypatch.setattr(
        query_routes.rag_pipeline,
        "process_query",
        lambda **_kwargs: {
            "response": "The VAT rate is grounded in Article 166.",
            "sources": [{
                "document_id": None,
                "title": "Tax Code of Georgia",
                "document_type": "law",
                "url": "https://matsne.gov.ge/",
                "relevance": 0.99,
                "article_ref": "166",
            }],
            "retrieved_count": 1,
        },
    )

    answer = client.post(
        "/api/v1/query",
        json={"query": "What is the VAT rate?", "language": "en"},
    )
    assert answer.status_code == 200
    payload = answer.json()
    assert payload["evidence"]["status"] == "grounded"
    assert payload["evidence"]["has_precise_citation"] is True
    conversation_id = payload["conversation_id"]

    listing = client.get("/api/v1/query/conversations?limit=20")
    assert listing.status_code == 200
    assert listing.json()[0]["messages_count"] == 2

    detail = client.get(f"/api/v1/query/conversations/{conversation_id}")
    assert detail.status_code == 200
    assert len(detail.json()["messages"]) == 2
    assert detail.json()["messages"][1]["sources"][0]["article_ref"] == "166"

    deleted = client.delete(f"/api/v1/query/conversations/{conversation_id}")
    assert deleted.status_code == 204
    assert client.get("/api/v1/query/conversations").json() == []


def test_protected_query_rejects_missing_session(client):
    client.cookies.clear()

    response = client.post(
        "/api/v1/query",
        json={"query": "VAT", "language": "en"},
    )

    assert response.status_code == 401


def test_email_verification_token_is_hashed_one_time_and_unlocks_login(
    client,
    monkeypatch,
):
    sent = []
    monkeypatch.setattr(settings, "EMAIL_DELIVERY_ENABLED", True)
    monkeypatch.setattr(auth, "send_auth_email", lambda *args: sent.append(args))

    registered = client.post(
        "/api/v1/auth/register",
        json={
            "email": "verify-user@example.com",
            "username": "verify-user",
            "password": "safe-password-123",
        },
    )
    assert registered.status_code == 201
    assert registered.json()["verification_required"] is True
    assert registered.json()["email_verified"] is False
    assert len(sent) == 1
    raw_token = sent[0][2]

    db = TestingSessionLocal()
    stored = db.query(AuthActionToken).filter_by(purpose="email_verification").one()
    assert stored.token_hash != raw_token
    assert len(stored.token_hash) == 64
    db.close()

    blocked = client.post(
        "/api/v1/auth/login",
        json={"username": "verify-user", "password": "safe-password-123"},
    )
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "Email verification required"

    verified = client.post(
        "/api/v1/auth/verify-email",
        json={"token": raw_token},
    )
    assert verified.status_code == 200
    assert client.post(
        "/api/v1/auth/verify-email",
        json={"token": raw_token},
    ).status_code == 400

    login = client.post(
        "/api/v1/auth/login",
        json={"username": "verify-user", "password": "safe-password-123"},
    )
    assert login.status_code == 200


def test_password_reset_is_generic_one_time_and_revokes_existing_session(
    client,
    monkeypatch,
):
    username = "reset-user"
    register_and_login(client, username)
    sent = []
    monkeypatch.setattr(settings, "EMAIL_DELIVERY_ENABLED", True)
    monkeypatch.setattr(auth, "send_auth_email", lambda *args: sent.append(args))

    unknown = client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "missing-user@example.com"},
    )
    known = client.post(
        "/api/v1/auth/forgot-password",
        json={"email": f"{username}@example.com"},
    )
    assert unknown.status_code == known.status_code == 200
    assert unknown.json() == known.json()
    assert len(sent) == 1
    raw_token = sent[0][2]

    reset = client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw_token, "new_password": "new-safe-password-456"},
    )
    assert reset.status_code == 200
    assert client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw_token, "new_password": "another-password-789"},
    ).status_code == 400

    assert client.get("/api/v1/account").status_code == 401
    assert client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "safe-password-123"},
    ).status_code == 401
    assert client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "new-safe-password-456"},
    ).status_code == 200


def test_recovery_reports_unavailable_when_email_delivery_is_disabled(
    client,
    monkeypatch,
):
    monkeypatch.setattr(settings, "EMAIL_DELIVERY_ENABLED", False)

    response = client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "anyone@example.com"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Account email delivery is not configured."


@pytest.fixture()
def online_checkout(client, monkeypatch):
    """Real checkout/DB flow with only the authenticated bank boundary replaced."""
    from billing.gateway import ProviderPayment, ProviderRequestError

    class Bank:
        status = "Created"
        unavailable = False
        calls = 0

        def create_checkout(self, checkout, _user, _plan, _language):
            self.order_id = f"test-{checkout.id}"
            return {
                "provider": "tbc", "method_id": "tbc_checkout", "status": "available",
                "instruction_code": "redirect_to_bank", "contact_email": None,
                "redirect_url": f"https://tpay.tbcbank.ge/checkout/{self.order_id}",
                "provider_order_id": self.order_id, "provider_status": "Created",
                "expires_in_minutes": 12,
            }

        def get_payment(self, order_id):
            self.calls += 1
            assert order_id == self.order_id
            if self.unavailable:
                raise ProviderRequestError("test_provider_unavailable")
            return ProviderPayment(order_id, self.status, 4900, "GEL")

    bank = Bank()
    real_gateway = billing.get_gateway
    monkeypatch.setattr(
        billing, "get_gateway",
        lambda provider="manual": bank if provider == "tbc" else real_gateway(provider),
    )
    username = f"bank-{uuid4().hex[:12]}"
    register_and_login(client, username)
    response = client.post(
        "/api/v1/billing/checkout", headers={"Idempotency-Key": uuid4().hex},
        json={"plan": "pro", "provider": "tbc", **CHECKOUT_CONSENT},
    )
    assert response.status_code == 200
    checkout_id = response.json()["checkout"]["id"]
    return SimpleNamespace(bank=bank, id=checkout_id, username=username)


def _bank_callback(client, checkout, status):
    checkout.bank.status = status
    response = client.post(
        "/api/v1/billing/providers/tbc/callback",
        json={"PaymentId": checkout.bank.order_id},
    )
    assert response.status_code == 200
    return response.json()


def _make_current_user_admin(username):
    with TestingSessionLocal() as db:
        db.query(User).filter_by(username=username).one().role = "admin"
        db.commit()


@pytest.mark.parametrize("held_status", ["Returned", "PartialReturned", "WaitingConfirm"])
@pytest.mark.parametrize("later_status", ["Created", "Processing", "Failed", "Expired", "Succeeded"])
def test_payment_review_survives_later_bank_states(client, online_checkout, held_status, later_status):
    checkout = online_checkout
    assert _bank_callback(client, checkout, held_status)["checkout"]["status"] == "provider_review"
    assert _bank_callback(client, checkout, later_status)["checkout"]["status"] == "provider_review"
    # A success following an intermediate callback must not bypass the hold.
    assert _bank_callback(client, checkout, "Succeeded")["checkout"]["status"] == "provider_review"
    with TestingSessionLocal() as db:
        row = db.get(BillingCheckout, UUID(checkout.id))
        assert row.settled_payment_id is None
        assert db.query(Subscription).filter_by(user_id=row.user_id).count() == 0
        assert db.query(Payment).filter_by(provider_tx_id=checkout.bank.order_id).count() == 0


@pytest.mark.parametrize("later_status", ["Processing", "Failed", "Expired", "Returned", "PartialReturned"])
def test_settled_order_conflicts_preserve_payment_and_access(client, online_checkout, later_status):
    checkout = online_checkout
    # Observe a state before settlement too: replay protection must not hide a
    # conflicting reappearance of that state after the payment is settled.
    if later_status == "Processing":
        _bank_callback(client, checkout, "Processing")
    assert _bank_callback(client, checkout, "Succeeded")["checkout"]["status"] == "paid"
    with TestingSessionLocal() as db:
        row = db.get(BillingCheckout, UUID(checkout.id))
        payment_id = row.settled_payment_id
        period_end = db.query(Subscription).filter_by(user_id=row.user_id).one().period_end
    assert _bank_callback(client, checkout, later_status)["checkout"]["status"] == "provider_review"
    assert _bank_callback(client, checkout, "Succeeded")["checkout"]["status"] == "provider_review"
    with TestingSessionLocal() as db:
        row = db.get(BillingCheckout, UUID(checkout.id))
        assert row.settled_payment_id == payment_id
        sub = db.query(Subscription).filter_by(user_id=row.user_id).one()
        assert sub.period_end == period_end
        assert sub.status == "active"
        assert db.query(Payment).filter_by(provider_tx_id=checkout.bank.order_id).count() == 1


def test_delayed_success_after_local_expiry_still_settles_once(client, online_checkout):
    checkout = online_checkout
    with TestingSessionLocal() as db:
        row = db.get(BillingCheckout, UUID(checkout.id))
        row.expires_at = utc_now() - timedelta(minutes=5)
        row.status = "expired"
        db.commit()
    assert _bank_callback(client, checkout, "Succeeded")["checkout"]["status"] == "paid"
    assert _bank_callback(client, checkout, "Succeeded")["replayed"] is True
    with TestingSessionLocal() as db:
        assert db.query(Payment).filter_by(provider_tx_id=checkout.bank.order_id).count() == 1


def test_bank_outage_and_foreign_refresh_do_not_change_checkout(client, online_checkout):
    checkout = online_checkout
    checkout.bank.unavailable = True
    with TestingSessionLocal() as db:
        original_check = db.get(BillingCheckout, UUID(checkout.id)).provider_checked_at
    response = client.post(f"/api/v1/billing/checkout/{checkout.id}/refresh")
    assert response.status_code == 503
    with TestingSessionLocal() as db:
        row = db.get(BillingCheckout, UUID(checkout.id))
        assert row.status == "pending"
        assert row.provider_checked_at == original_check
        assert db.query(BillingProviderEvent).filter_by(checkout_id=row.id).count() == 0
    register_and_login(client, f"other-{uuid4().hex[:12]}")
    calls = checkout.bank.calls
    assert client.post(f"/api/v1/billing/checkout/{checkout.id}/refresh").status_code == 404
    assert checkout.bank.calls == calls
    assert client.post(
        "/api/v1/billing/providers/tbc/callback", json={"PaymentId": "unknown-order"},
    ).status_code == 200
    assert checkout.bank.calls == calls


def test_reconciliation_requires_admin_and_does_not_contact_bank(client, online_checkout):
    checkout = online_checkout
    detail_url = f"/api/v1/billing/admin/reconciliation/{checkout.id}"
    for url in ("/api/v1/billing/admin/reconciliation", detail_url):
        assert client.get(url).status_code == 403
    _make_current_user_admin(checkout.username)
    checkout.bank.unavailable = True
    assert client.get("/api/v1/billing/admin/reconciliation").status_code == 200
    detail = client.get(detail_url)
    assert detail.status_code == 200
    assert detail.json()["checkout"]["reason"] is None
    assert detail.json()["events"] == []
    assert checkout.bank.calls == 0
    assert client.get(f"/api/v1/billing/admin/reconciliation/{uuid4()}").status_code == 404
    for query in ("limit=0", "limit=101", "offset=-1", "offset=100001"):
        assert client.get(f"/api/v1/billing/admin/reconciliation?{query}").status_code == 422
    client.cookies.clear()
    for url in ("/api/v1/billing/admin/reconciliation", detail_url):
        assert client.get(url).status_code == 401


def test_reconciliation_queue_is_bounded_and_read_only(client, online_checkout):
    checkout = online_checkout
    _make_current_user_admin(checkout.username)
    created_ids = []
    with TestingSessionLocal() as db:
        owner = db.get(BillingCheckout, UUID(checkout.id)).user_id
        for index, (status, provider, provider_status) in enumerate([
            ("provider_unknown", "tbc", None),
            ("provider_review", "tbc", "PartialReturned"),
            ("pending", "tbc", "Created"),
            ("expired", "tbc", None),
            ("expired", "tbc", "Expired"),
            ("pending", "manual", None),
            ("failed", "tbc", "Failed"),
        ]):
            old = utc_now() - timedelta(days=4000, minutes=10-index)
            row = BillingCheckout(
                user_id=owner, plan="pro", amount_minor=4900, currency="GEL",
                provider=provider, status=status, provider_status=provider_status,
                idempotency_key=uuid4().hex, expires_at=old + timedelta(minutes=1),
                created_at=old, updated_at=old,
            )
            db.add(row)
            db.flush()
            created_ids.append(str(row.id))
        db.commit()
        before = [(row.id, row.status, row.updated_at) for row in db.query(BillingCheckout).all()]
        event_count = db.query(BillingProviderEvent).count()
        payment_count = db.query(Payment).count()
    first = client.get("/api/v1/billing/admin/reconciliation?limit=2").json()
    second = client.get(f"/api/v1/billing/admin/reconciliation?limit=2&offset={first['next_offset']}").json()
    items = first["items"] + second["items"]
    assert [item["id"] for item in items] == created_ids[:4]
    assert [item["reason"] for item in items] == [
        "provider_unknown", "provider_review", "payment_verification_overdue", "payment_verification_overdue",
    ]
    for item in items:
        assert "provider_redirect_url" not in item
        assert "email" not in item
        assert "terms_accepted_at" not in item
    assert client.get("/api/v1/billing/admin/reconciliation?offset=100000").json() == {
        "items": [], "next_offset": None,
    }
    with TestingSessionLocal() as db:
        assert [(row.id, row.status, row.updated_at) for row in db.query(BillingCheckout).all()] == before
        assert db.query(BillingProviderEvent).count() == event_count
        assert db.query(Payment).count() == payment_count
    assert checkout.bank.calls == 0


def test_reconciliation_detail_exposes_bounded_conflict_evidence(client, online_checkout):
    checkout = online_checkout
    _bank_callback(client, checkout, "PartialReturned")
    _bank_callback(client, checkout, "Processing")
    _make_current_user_admin(checkout.username)
    with TestingSessionLocal() as db:
        for index in range(51):
            db.add(BillingProviderEvent(
                checkout_id=UUID(checkout.id), provider="tbc",
                event_id=f"{checkout.id}:evidence-{index}", provider_status="PartialReturned",
                payload_sha256="a" * 64, processing_status="review",
                error_code="provider_state_requires_review",
                created_at=utc_now() - timedelta(days=1, minutes=index),
            ))
        db.commit()
    calls = checkout.bank.calls
    response = client.get(f"/api/v1/billing/admin/reconciliation/{checkout.id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["checkout"]["reason"] == "provider_review"
    assert payload["events_truncated"] is True
    assert len(payload["events"]) == 50
    assert payload["events"][0]["error_code"] == "checkout_requires_review"
    assert all(len(event["payload_sha256"]) == 64 for event in payload["events"])
    assert all("raw_webhook" not in event for event in payload["events"])
    assert checkout.bank.calls == calls


def test_paid_pro_access_and_sources_survive_password_recovery(client, online_checkout, monkeypatch):
    checkout = online_checkout
    assert client.get("/api/v1/query/conversations").status_code == 402
    assert _bank_callback(client, checkout, "Succeeded")["checkout"]["status"] == "paid"
    assert client.get("/api/v1/billing/subscription").json()["plan"] == "pro"
    monkeypatch.setattr(
        query_routes.rag_pipeline, "process_query",
        lambda **_kwargs: {
            "response": "Test answer with Article 166 source.",
            "sources": [{
                "document_id": None, "title": "Tax Code of Georgia",
                "document_type": "law", "url": "https://matsne.gov.ge/",
                "relevance": 0.99, "article_ref": "166",
            }],
            "retrieved_count": 1,
        },
    )
    answer = client.post("/api/v1/query", json={"query": "VAT rate", "language": "en"})
    assert answer.status_code == 200
    conversation_id = answer.json()["conversation_id"]
    before_recovery = client.get(f"/api/v1/query/conversations/{conversation_id}")
    assert before_recovery.status_code == 200
    sources = before_recovery.json()["messages"][1]["sources"]
    assert sources[0]["url"] == answer.json()["sources"][0]["url"]
    assert sources[0]["article_ref"] == answer.json()["sources"][0]["article_ref"]
    sent = []
    monkeypatch.setattr(settings, "EMAIL_DELIVERY_ENABLED", True)
    monkeypatch.setattr(auth, "send_auth_email", lambda *args: sent.append(args))
    recovery = client.post(
        "/api/v1/auth/forgot-password", json={"email": f"{checkout.username}@example.com"},
    )
    assert recovery.status_code == 200
    assert len(sent) == 1
    assert client.post(
        "/api/v1/auth/reset-password",
        json={"token": sent[0][2], "new_password": "recovered-safe-password-456"},
    ).status_code == 200
    assert client.get("/api/v1/billing/subscription").status_code == 401
    assert client.post(
        "/api/v1/auth/login",
        json={"username": checkout.username, "password": "recovered-safe-password-456"},
    ).status_code == 200
    assert client.get("/api/v1/billing/subscription").json()["plan"] == "pro"
    history = client.get(f"/api/v1/query/conversations/{conversation_id}")
    assert history.status_code == 200
    assert history.json()["messages"][1]["sources"] == sources
    assert _bank_callback(client, checkout, "Succeeded")["replayed"] is True


def _review_preview(client, checkout, verify=True):
    response = client.post(f"/api/v1/billing/admin/reconciliation/{checkout.id}/preview", params={"verify_provider": verify})
    assert response.status_code == 200, response.text
    return response.json()


def _review_body(preview, action="keep_review"):
    return {"action": action, "reason": "Compared the order with verified evidence.",
            "expected_state_sha256": preview["state_sha256"],
            "expected_provider_sha256": preview["provider_sha256"],
            "expected_access_effect": preview["actions"].get(action, "unchanged")}


def _review_apply(client, checkout, body, key=None):
    return client.post(f"/api/v1/billing/admin/reconciliation/{checkout.id}/decisions",
                       json=body, headers={"Idempotency-Key": key or uuid4().hex})


@pytest.fixture
def review_checkout(client, online_checkout):
    _bank_callback(client, online_checkout, "WaitingConfirm")
    _make_current_user_admin(online_checkout.username)
    return online_checkout


def test_operator_hold_works_offline_and_records_attribution(client, review_checkout):
    checkout = review_checkout
    checkout.bank.unavailable = True
    calls = checkout.bank.calls
    preview = _review_preview(client, checkout, False)
    assert preview["actions"] == {"keep_review": "unchanged"}
    response = _review_apply(client, checkout, _review_body(preview))
    assert response.status_code == 200
    decision = response.json()["decision"]
    assert decision["provider_evidence"] is None
    assert decision["before"]["subscription"] == decision["after"]["subscription"] is None
    with TestingSessionLocal() as db:
        assert decision["actor_id"] == str(db.query(User).filter_by(username=checkout.username).one().id)
    history = client.get(f"/api/v1/billing/admin/reconciliation/{checkout.id}/decisions").json()
    assert history["items"] == [decision]
    assert history["next_offset"] is None
    assert checkout.bank.calls == calls


def test_operator_success_grants_once_and_replays_without_bank(client, review_checkout):
    checkout = review_checkout
    checkout.bank.status = "Succeeded"
    preview = _review_preview(client, checkout)
    assert preview["actions"]["confirm_payment"] == "grant_period"
    body, key = _review_body(preview, "confirm_payment"), uuid4().hex
    first = _review_apply(client, checkout, body, key)
    assert first.status_code == 200, first.text
    decision = first.json()["decision"]
    assert decision["after"]["checkout"]["status"] == "paid"
    assert decision["after"]["subscription"]["plan"] == "pro"
    checkout.bank.unavailable = True
    second = _review_apply(client, checkout, body, key)
    assert second.json() == {"decision": decision, "replayed": True}
    assert _review_apply(client, checkout, {**body, "reason": "A different operator explanation."}, key).status_code == 409
    checkout.bank.unavailable = False
    assert _bank_callback(client, checkout, "Succeeded")["checkout"]["status"] == "paid"
    with TestingSessionLocal() as db:
        assert db.query(Payment).filter_by(provider_tx_id=checkout.bank.order_id).count() == 1
        assert db.query(BillingReviewDecision).filter_by(checkout_id=UUID(checkout.id)).count() == 1
        assert str(db.query(Subscription).filter_by(user_id=UUID(decision["after"]["checkout"]["user_id"])).one().period_end) == decision["after"]["subscription"]["period_end"]


def test_operator_releasing_settled_hold_does_not_extend_access(client, online_checkout):
    checkout = online_checkout
    _bank_callback(client, checkout, "Succeeded")
    _bank_callback(client, checkout, "Returned")
    _make_current_user_admin(checkout.username)
    checkout.bank.status = "Succeeded"
    preview = _review_preview(client, checkout)
    assert preview["actions"]["confirm_payment"] == "unchanged"
    response = _review_apply(client, checkout, _review_body(preview, "confirm_payment"))
    assert response.status_code == 200
    decision = response.json()["decision"]
    assert decision["before"]["subscription"] == decision["after"]["subscription"]
    assert decision["before"]["payment"] == decision["after"]["payment"]


@pytest.mark.parametrize("status", ["Failed", "Expired"])
def test_operator_confirms_no_charge_only_without_settlement(client, review_checkout, status):
    checkout = review_checkout
    checkout.bank.status = status
    preview = _review_preview(client, checkout)
    response = _review_apply(client, checkout, _review_body(preview, "confirm_no_charge"))
    assert response.status_code == 200
    assert response.json()["decision"]["after"]["checkout"]["status"] == status.lower()
    assert response.json()["decision"]["after"]["subscription"] is None


@pytest.mark.parametrize("status", ["Returned", "PartialReturned", "WaitingConfirm", "Processing"])
def test_operator_cannot_resolve_unsettled_or_refunded_bank_states(client, review_checkout, status):
    checkout = review_checkout
    checkout.bank.status = status
    preview = _review_preview(client, checkout)
    assert preview["actions"] == {"keep_review": "unchanged"}
    assert _review_apply(client, checkout, _review_body(preview, "confirm_payment")).status_code == 409


@pytest.mark.parametrize("changed", ["checkout", "events", "bank", "access_effect"])
def test_operator_stale_or_changed_evidence_is_atomic(client, review_checkout, changed):
    checkout = review_checkout
    checkout.bank.status = "Succeeded"
    preview = _review_preview(client, checkout)
    body = _review_body(preview, "confirm_payment")
    if changed == "bank":
        checkout.bank.status = "Failed"
    elif changed == "access_effect":
        body["expected_access_effect"] = "unchanged"
    else:
        with TestingSessionLocal() as db:
            if changed == "checkout":
                db.get(BillingCheckout, UUID(checkout.id)).updated_at = utc_now()
            else:
                db.query(BillingProviderEvent).filter_by(checkout_id=UUID(checkout.id)).one().error_code = "new_conflict"
            db.commit()
    response = _review_apply(client, checkout, body)
    assert response.status_code == 409, response.text
    with TestingSessionLocal() as db:
        assert db.query(BillingReviewDecision).filter_by(checkout_id=UUID(checkout.id)).count() == 0
        assert db.query(Payment).filter_by(provider_tx_id=checkout.bank.order_id).count() == 0
        assert db.get(BillingCheckout, UUID(checkout.id)).status == "provider_review"


def test_operator_bank_failure_does_not_write_decision(client, review_checkout):
    checkout = review_checkout
    checkout.bank.status = "Succeeded"
    body = _review_body(_review_preview(client, checkout), "confirm_payment")
    checkout.bank.unavailable = True
    assert _review_apply(client, checkout, body).status_code == 503
    with TestingSessionLocal() as db:
        assert db.query(BillingReviewDecision).filter_by(checkout_id=UUID(checkout.id)).count() == 0


@pytest.mark.parametrize("field,value", [("amount_minor", 4901), ("currency", "USD"), ("provider_order_id", "wrong-order")])
def test_operator_rejects_mismatched_bank_evidence(client, review_checkout, monkeypatch, field, value):
    from billing.gateway import ProviderPayment
    checkout = review_checkout
    values = {"provider_order_id": checkout.bank.order_id, "status": "Succeeded", "amount_minor": 4900, "currency": "GEL"}
    values[field] = value
    monkeypatch.setattr(checkout.bank, "get_payment", lambda _: ProviderPayment(**values))
    preview = _review_preview(client, checkout)
    assert preview["actions"] == {"keep_review": "unchanged"}
    assert _review_apply(client, checkout, _review_body(preview, "confirm_payment")).status_code == 409


def test_operator_missing_settlement_reference_cannot_grant_again(client, online_checkout):
    checkout = online_checkout
    _bank_callback(client, checkout, "Succeeded")
    with TestingSessionLocal() as db:
        row = db.get(BillingCheckout, UUID(checkout.id))
        row.status, row.settled_payment_id = "provider_review", None
        db.commit()
    _make_current_user_admin(checkout.username)
    assert _review_preview(client, checkout)["actions"] == {"keep_review": "unchanged"}


def test_operator_decisions_require_admin_and_reason(client, online_checkout):
    checkout = online_checkout
    root = f"/api/v1/billing/admin/reconciliation/{checkout.id}"
    assert client.post(root + "/preview").status_code == 403
    assert client.get(root + "/decisions").status_code == 403
    _bank_callback(client, checkout, "WaitingConfirm")
    _make_current_user_admin(checkout.username)
    body = _review_body(_review_preview(client, checkout, False))
    assert _review_apply(client, checkout, {**body, "reason": "   "}).status_code == 422
    with TestingSessionLocal() as db:
        db.query(User).filter_by(username=checkout.username).one().role = "user"
        db.commit()
    assert _review_apply(client, checkout, body).status_code == 403


@pytest.mark.parametrize("broken", ["consent", "other_plan", "settled_failed"])
def test_operator_unsafe_access_changes_stay_held(client, review_checkout, broken):
    checkout = review_checkout
    checkout.bank.status = "Succeeded"
    with TestingSessionLocal() as db:
        row = db.get(BillingCheckout, UUID(checkout.id))
        if broken == "consent":
            row.terms_accepted_at = None
        elif broken == "other_plan":
            db.add(Subscription(user_id=row.user_id, plan="business", status="active", period_end=utc_now() + timedelta(days=10)))
        else:
            row.status = "pending"
        db.commit()
    if broken == "settled_failed":
        _bank_callback(client, checkout, "Succeeded")
        _bank_callback(client, checkout, "Returned")
        checkout.bank.status = "Failed"
    preview = _review_preview(client, checkout)
    assert preview["actions"] == {"keep_review": "unchanged"}


def test_operator_preview_does_not_mutate_evidence(client, review_checkout):
    checkout = review_checkout
    with TestingSessionLocal() as db:
        before = billing.snapshot(db, db.get(BillingCheckout, UUID(checkout.id)))
    checkout.bank.status = "Succeeded"
    _review_preview(client, checkout)
    with TestingSessionLocal() as db:
        assert billing.snapshot(db, db.get(BillingCheckout, UUID(checkout.id))) == before
        assert db.query(BillingReviewDecision).filter_by(checkout_id=UUID(checkout.id)).count() == 0
