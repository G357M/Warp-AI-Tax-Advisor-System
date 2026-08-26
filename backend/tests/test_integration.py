"""Current API integration tests using an isolated in-memory database."""

from datetime import timedelta
from types import ModuleType, SimpleNamespace
import sys

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
from models import AuthActionToken, Conversation, Message, Payment, Subscription, User

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
