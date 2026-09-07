"""Current API integration tests using an isolated in-memory database."""

from datetime import timedelta
from types import ModuleType, SimpleNamespace
import sys
from uuid import UUID

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
    Conversation,
    Message,
    Payment,
    Subscription,
    User,
)

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
    assert payload["version"] == "2026-09-07"
    assert payload["currency_minor_unit"] == 2
    assert {plan["id"]: plan["price_minor"] for plan in payload["plans"]} == {
        "free": 0,
        "pro": 4900,
        "business": 14900,
    }
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
        json={"plan": "pro", "provider": "manual"},
    )

    assert created.status_code == 200
    payload = created.json()
    assert payload["replayed"] is False
    assert payload["checkout"]["amount_minor"] == 4900
    assert payload["checkout"]["currency"] == "GEL"
    assert payload["checkout"]["status"] == "pending"
    assert payload["payment_method"]["instruction_code"] == "contact_for_invoice"

    replay = client.post(
        "/api/v1/billing/checkout",
        headers=headers,
        json={"plan": "pro", "provider": "manual"},
    )
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert replay.json()["checkout"]["id"] == payload["checkout"]["id"]

    conflict = client.post(
        "/api/v1/billing/checkout",
        headers=headers,
        json={"plan": "business", "provider": "manual"},
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


def test_admin_checkout_settlement_is_idempotent(client):
    customer_username = "settlement-customer"
    register_and_login(client, customer_username)
    checkout_response = client.post(
        "/api/v1/billing/checkout",
        headers={"Idempotency-Key": "settlement-customer-pro-001"},
        json={"plan": "pro"},
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
        json={"plan": "pro", "provider": "tbc", "language": "ka"},
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
        json={"plan": "pro", "provider": "tbc", "language": "ka"},
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
