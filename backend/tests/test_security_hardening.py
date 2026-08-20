"""Focused regression tests for the production security boundary."""

import asyncio
import json
import time
from pathlib import Path
from types import SimpleNamespace

from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

from api.routes import auth as auth_routes
from api.schemas import UserLogin
from core.rate_limit import get_client_ip, rate_limit_middleware, rate_limiter
from core.security import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)


def _request(*, headers=None, client=("203.0.113.20", 12345)) -> Request:
    raw_headers = [
        (name.lower().encode("latin-1"), value.encode("latin-1"))
        for name, value in (headers or {}).items()
    ]
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/public/stats",
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
