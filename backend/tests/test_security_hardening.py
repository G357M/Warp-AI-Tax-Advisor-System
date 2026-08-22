"""Focused regression tests for the production security boundary."""

import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import jwt
import pytest
from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

from api.routes import auth as auth_routes
from api.schemas import UserLogin
from core.rate_limit import get_client_ip, rate_limit_middleware, rate_limiter
from core.security import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_token,
    verify_password,
)
from core.config import Settings, settings


def _request(
    *,
    headers=None,
    client=("203.0.113.20", 12345),
    path="/api/v1/public/stats",
) -> Request:
    raw_headers = [
        (name.lower().encode("latin-1"), value.encode("latin-1"))
        for name, value in (headers or {}).items()
    ]
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": raw_headers,
            "client": client,
            "scheme": "https",
            "server": ("tax-advisor.ge", 443),
            "query_string": b"",
        }
    )


def test_bcrypt_hashes_remain_compatible_without_passlib():
    password = "safe-password-123"
    password_hash = hash_password(password)

    assert password_hash.startswith("$2b$")
    assert verify_password(password, password_hash) is True
    assert verify_password("wrong-password", password_hash) is False


def test_client_ip_uses_validated_real_ip_and_ignores_forwarded_chain():
    request = _request(
        headers={
            "X-Real-IP": "198.51.100.42",
            "X-Forwarded-For": "192.0.2.99, 198.51.100.42",
        }
    )

    assert get_client_ip(request) == "198.51.100.42"


def test_client_ip_rejects_invalid_proxy_header():
    request = _request(
        headers={
            "X-Real-IP": "not-an-ip",
            "X-Forwarded-For": "192.0.2.99",
        }
    )

    assert get_client_ip(request) == "203.0.113.20"


def test_rate_limit_rejects_before_endpoint_execution(monkeypatch):
    async def blocked(**_kwargs):
        return False, {
            "limit": 10,
            "remaining": 0,
            "reset": int(time.time()) + 30,
        }

    endpoint_called = False

    async def call_next(_request):
        nonlocal endpoint_called
        endpoint_called = True
        return PlainTextResponse("expensive response")

    monkeypatch.setattr(rate_limiter, "check_rate_limit", blocked)
    response = asyncio.run(rate_limit_middleware(_request(), call_next, "10/minute"))

    assert response.status_code == 429
    assert endpoint_called is False
    assert json.loads(response.body)["detail"] == "Rate limit exceeded. Please try again later."
    assert int(response.headers["Retry-After"]) >= 0


def test_allowed_response_receives_rate_limit_headers(monkeypatch):
    reset = int(time.time()) + 30

    async def allowed(**_kwargs):
        return True, {"limit": 10, "remaining": 9, "reset": reset}

    async def call_next(_request):
        return PlainTextResponse("ok")

    monkeypatch.setattr(rate_limiter, "check_rate_limit", allowed)
    response = asyncio.run(rate_limit_middleware(_request(), call_next, "10/minute"))

    assert response.status_code == 200
    assert response.headers["X-RateLimit-Limit"] == "10"
    assert response.headers["X-RateLimit-Remaining"] == "9"
    assert response.headers["X-RateLimit-Reset"] == str(reset)


def test_recovery_endpoints_use_dedicated_hourly_rate_limit(monkeypatch):
    observed = {}

    async def allowed(**kwargs):
        observed.update(kwargs)
        return True, {}

    async def call_next(_request):
        return PlainTextResponse("ok")

    monkeypatch.setattr(rate_limiter, "check_rate_limit", allowed)
    monkeypatch.setattr(settings, "RATE_LIMIT_AUTH_RECOVERY", "10/hour")
    response = asyncio.run(
        rate_limit_middleware(
            _request(path="/api/v1/auth/forgot-password"),
            call_next,
        )
    )

    assert response.status_code == 200
    assert observed["max_requests"] == 10
    assert observed["window_seconds"] == 3600


def test_scraper_router_requires_admin_dependency():
    route_source = (
        Path(__file__).parents[1] / "api" / "routes" / "scraper.py"
    ).read_text(encoding="utf-8")

    assert "dependencies=[Depends(require_admin)]" in route_source


def test_http_only_session_cookie_authenticates_without_bearer_header():
    user = SimpleNamespace(username="cookie-user", is_active=True)

    class FakeQuery:
        def filter(self, *_args):
            return self

        def first(self):
            return user

    class FakeDb:
        def query(self, *_args):
            return FakeQuery()

    token = create_access_token({"sub": user.username, "role": "user"})
    request = _request(headers={"Cookie": f"ta_session={token}"})

    assert get_current_user(request=request, credentials=None, db=FakeDb()) is user


def test_previous_jwt_key_is_accepted_only_during_rotation_window(monkeypatch):
    current_key = "current-test-key-with-at-least-32-characters"
    previous_key = "previous-test-key-with-at-least-32-characters"
    token = jwt.encode(
        {
            "sub": "legacy-session",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
        },
        previous_key,
        algorithm="HS256",
    )

    monkeypatch.setattr(settings, "JWT_SECRET_KEY", current_key)
    monkeypatch.setattr(settings, "JWT_PREVIOUS_SECRET_KEYS", previous_key)
    monkeypatch.setattr(
        settings,
        "JWT_PREVIOUS_SECRET_ACCEPT_UNTIL",
        (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
    )
    assert verify_token(token)["sub"] == "legacy-session"

    monkeypatch.setattr(
        settings,
        "JWT_PREVIOUS_SECRET_ACCEPT_UNTIL",
        (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
    )
    assert verify_token(token) is None


def test_jwt_primary_key_requires_256_bits_of_material():
    with pytest.raises(ValidationError, match="at least 32 UTF-8 bytes"):
        Settings(
            _env_file=None,
            SECRET_KEY="test-application-secret-with-at-least-32-characters",
            JWT_SECRET_KEY="too-short",
            DATABASE_URL="sqlite://",
            REDIS_URL="redis://localhost:6379/15",
        )


def test_email_delivery_requires_password_for_authenticated_smtp():
    with pytest.raises(ValidationError, match="SMTP_PASSWORD"):
        Settings(
            _env_file=None,
            SECRET_KEY="test-application-secret-with-at-least-32-characters",
            JWT_SECRET_KEY="test-jwt-secret-with-at-least-32-characters",
            DATABASE_URL="postgresql://test:test@localhost:5432/test",
            REDIS_URL="redis://localhost:6379/15",
            EMAIL_DELIVERY_ENABLED=True,
            SMTP_HOST="smtp.example.com",
            SMTP_FROM="Tax Advisor <noreply@example.com>",
            SMTP_USER="smtp-user",
            SMTP_PASSWORD=None,
        )


def test_new_tokens_are_signed_only_with_current_jwt_key(monkeypatch):
    current_key = "current-test-key-with-at-least-32-characters"
    previous_key = "previous-test-key-with-at-least-32-characters"
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", current_key)
    monkeypatch.setattr(settings, "JWT_PREVIOUS_SECRET_KEYS", previous_key)
    monkeypatch.setattr(
        settings,
        "JWT_PREVIOUS_SECRET_ACCEPT_UNTIL",
        (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
    )

    token = create_access_token({"sub": "new-session"})

    assert jwt.decode(token, current_key, algorithms=["HS256"])["sub"] == "new-session"
    try:
        jwt.decode(token, previous_key, algorithms=["HS256"])
    except jwt.InvalidSignatureError:
        pass
    else:
        raise AssertionError("new token unexpectedly used the previous JWT key")


def test_login_sets_http_only_same_site_session_cookie(monkeypatch):
    user = SimpleNamespace(
        username="cookie-user",
        role="user",
        is_active=True,
        password_hash="unused",
        last_login=None,
    )

    class FakeQuery:
        def filter(self, *_args):
            return self

        def first(self):
            return user

    class FakeDb:
        def query(self, *_args):
            return FakeQuery()

        def commit(self):
            return None

    monkeypatch.setattr(auth_routes, "verify_password", lambda *_args: True)
    monkeypatch.setattr(auth_routes.settings, "ENVIRONMENT", "production")
    response = Response()

    auth_routes.login(
        UserLogin(username=user.username, password="valid-password"),
        response,
        FakeDb(),
    )

    cookie = response.headers["set-cookie"].lower()
    assert cookie.startswith("ta_session=")
    assert "httponly" in cookie
    assert "secure" in cookie
    assert "samesite=lax" in cookie
    assert "path=/" in cookie


def test_session_version_rejects_token_after_password_reset():
    user = SimpleNamespace(username="versioned-user", is_active=True, session_version=2)

    class FakeQuery:
        def filter(self, *_args):
            return self

        def first(self):
            return user

    class FakeDb:
        def query(self, *_args):
            return FakeQuery()

    stale = create_access_token({"sub": user.username, "sv": 1})
    request = _request(headers={"Cookie": f"ta_session={stale}"})

    with pytest.raises(Exception) as exc_info:
        get_current_user(request=request, credentials=None, db=FakeDb())
    assert getattr(exc_info.value, "status_code", None) == 401
