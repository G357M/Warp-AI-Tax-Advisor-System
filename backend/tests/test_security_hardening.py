"""Focused regression tests for the production security boundary."""

import asyncio
import json
import time
from pathlib import Path

from starlette.requests import Request
from starlette.responses import PlainTextResponse

from core.rate_limit import get_client_ip, rate_limit_middleware, rate_limiter


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
