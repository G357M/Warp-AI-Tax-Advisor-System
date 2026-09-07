"""Deterministic TBC adapter contract tests with no external requests."""
import json
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from billing.catalog import get_plan
from billing.gateway import ProviderRequestError, TBCGateway, _minor_from_provider_amount
from core.config import settings


def _enable_tbc(monkeypatch) -> None:
    monkeypatch.setattr(settings, "BILLING_TBC_ENABLED", True)
    monkeypatch.setattr(settings, "TBC_API_BASE_URL", "https://api.tbcbank.ge")
    monkeypatch.setattr(settings, "TBC_API_KEY", SecretStr("developer-api-key"))
    monkeypatch.setattr(settings, "TBC_CLIENT_ID", SecretStr("merchant-id"))
    monkeypatch.setattr(settings, "TBC_CLIENT_SECRET", SecretStr("merchant-secret"))
    monkeypatch.setattr(settings, "TBC_RETURN_URL", "https://tax-advisor.ge/account?payment_return=tbc")
    monkeypatch.setattr(
        settings,
        "TBC_CALLBACK_URL",
        "https://tax-advisor.ge/api/v1/billing/providers/tbc/callback",
    )
    monkeypatch.setattr(settings, "TBC_HTTP_TIMEOUT_SECONDS", 12)
    monkeypatch.setattr(settings, "TBC_CHECKOUT_EXPIRATION_MINUTES", 12)
    TBCGateway._cached_token = None
    TBCGateway._cached_token_until = 0


def test_provider_amount_requires_exact_minor_units():
    assert _minor_from_provider_amount("49.00") == 4900
    with pytest.raises(ProviderRequestError, match="invalid_provider_amount"):
        _minor_from_provider_amount("49.001")


def test_tbc_adapter_creates_and_verifies_a_server_priced_payment(monkeypatch):
    _enable_tbc(monkeypatch)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/v1/tpay/access-token":
            assert request.headers["apikey"] == "developer-api-key"
            assert b"client_id=merchant-id" in request.read()
            assert b"client_secret=merchant-secret" in request.content
            return httpx.Response(
                200,
                json={"access_token": "bank-token", "token_type": "bearer", "expires_in": 3600},
            )
        if request.method == "POST" and request.url.path == "/v1/tpay/payments":
            assert request.headers["authorization"] == "Bearer bank-token"
            body = json.loads(request.read())
            assert body["amount"] == {"currency": "GEL", "total": 49.0}
            assert body["preAuth"] is False
            assert body["language"] == "KA"
            assert body["merchantPaymentId"] == checkout_id
            assert body["returnurl"] == (
                f"https://tax-advisor.ge/account?payment_return=tbc&checkout_id={checkout_id}"
            )
            return httpx.Response(
                200,
                json={
                    "payId": "tpay-contract-001",
                    "status": "Created",
                    "currency": "GEL",
                    "amount": 49,
                    "links": [
                        {
                            "uri": "https://tpay.tbcbank.ge/checkout/tpay-contract-001",
                            "method": "REDIRECT",
                            "rel": "approval_url",
                        }
                    ],
                },
            )
        if request.method == "GET" and request.url.path.endswith("/tpay-contract-001"):
            return httpx.Response(
                200,
                json={
                    "payId": "tpay-contract-001",
                    "status": "Succeeded",
                    "currency": "GEL",
                    "amount": "49.00",
                },
            )
        raise AssertionError(f"unexpected TBC request: {request.method} {request.url}")

    checkout_uuid = uuid4()
    checkout_id = str(checkout_uuid)
    checkout = SimpleNamespace(
        id=checkout_uuid,
        amount_minor=4900,
        currency="GEL",
    )
    gateway = TBCGateway(transport=httpx.MockTransport(handler))

    created = gateway.create_checkout(checkout, None, get_plan("pro"), "ka")
    payment = gateway.get_payment("tpay-contract-001")

    assert created["provider_order_id"] == "tpay-contract-001"
    assert created["redirect_url"].startswith("https://tpay.tbcbank.ge/")
    assert payment.status == "Succeeded"
    assert payment.amount_minor == 4900
    assert len([request for request in requests if request.url.path.endswith("access-token")]) == 1


def test_tbc_adapter_rejects_an_untrusted_redirect_host(monkeypatch):
    _enable_tbc(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/tpay/access-token":
            return httpx.Response(
                200,
                json={"access_token": "bank-token", "token_type": "Bearer", "expires_in": 3600},
            )
        return httpx.Response(
            200,
            json={
                "payId": "tpay-contract-002",
                "status": "Created",
                "currency": "GEL",
                "amount": 49,
                "links": [
                    {
                        "uri": "https://lookalike.example/checkout/tpay-contract-002",
                        "method": "REDIRECT",
                        "rel": "approval_url",
                    }
                ],
            },
        )

    gateway = TBCGateway(transport=httpx.MockTransport(handler))
    checkout = SimpleNamespace(id=uuid4(), amount_minor=4900, currency="GEL")

    with pytest.raises(ProviderRequestError, match="tbc_untrusted_approval_url"):
        gateway.create_checkout(checkout, None, get_plan("pro"), "en")


def test_tbc_adapter_rejects_a_custom_port_on_the_approval_host(monkeypatch):
    _enable_tbc(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/tpay/access-token":
            return httpx.Response(
                200,
                json={"access_token": "bank-token", "token_type": "Bearer", "expires_in": 3600},
            )
        return httpx.Response(
            200,
            json={
                "payId": "tpay-contract-003",
                "status": "Created",
                "currency": "GEL",
                "amount": 49,
                "links": [
                    {
                        "uri": "https://tpay.tbcbank.ge:444/checkout/tpay-contract-003",
                        "method": "REDIRECT",
                        "rel": "approval_url",
                    }
                ],
            },
        )

    gateway = TBCGateway(transport=httpx.MockTransport(handler))
    checkout = SimpleNamespace(id=uuid4(), amount_minor=4900, currency="GEL")

    with pytest.raises(ProviderRequestError, match="tbc_untrusted_approval_url"):
        gateway.create_checkout(checkout, None, get_plan("pro"), "en")
