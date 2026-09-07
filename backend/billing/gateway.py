"""Payment-provider adapters behind one fail-closed billing interface.

The manual invoice provider is always executable. TBC Checkout becomes
available only when the explicit feature flag and every merchant credential are
present. Provider callbacks are never treated as proof of payment: callers
must retrieve and validate the authoritative payment state from TBC.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from threading import Lock
from time import monotonic
from typing import Any, Dict, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
import re

import httpx

from billing.catalog import PlanDefinition
from core.config import settings


TBC_PAYMENT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
TBC_KNOWN_STATUSES = frozenset(
    {
        "Created",
        "Processing",
        "Succeeded",
        "Failed",
        "Expired",
        "WaitingConfirm",
        "CancelPaymentProcessing",
        "PaymentCompletionProcessing",
        "Returned",
        "PartialReturned",
    }
)


class GatewayUnavailable(RuntimeError):
    """Raised when an explicitly requested provider is not safely configured."""


class ProviderRequestError(RuntimeError):
    """Provider request failed or returned a response outside its contract."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ProviderCheckout:
    provider_order_id: str
    provider_status: str
    redirect_url: str
    expires_in_minutes: int


@dataclass(frozen=True)
class ProviderPayment:
    provider_order_id: str
    status: str
    amount_minor: int
    currency: str


def _secret_value(value: Any) -> str:
    if value is None:
        return ""
    getter = getattr(value, "get_secret_value", None)
    return getter() if getter else str(value)


def tbc_checkout_ready() -> bool:
    return bool(
        settings.BILLING_TBC_ENABLED
        and _secret_value(settings.TBC_API_KEY)
        and _secret_value(settings.TBC_CLIENT_ID)
        and _secret_value(settings.TBC_CLIENT_SECRET)
    )


def _minor_from_provider_amount(value: Any) -> int:
    try:
        raw_amount = Decimal(str(value))
        amount = raw_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ProviderRequestError("invalid_provider_amount") from exc
    if not amount.is_finite() or amount < 0 or raw_amount != amount:
        raise ProviderRequestError("invalid_provider_amount")
    return int(amount * 100)


def _provider_amount_from_minor(amount_minor: int) -> float:
    if amount_minor < 0:
        raise ProviderRequestError("invalid_checkout_amount")
    return float((Decimal(amount_minor) / Decimal(100)).quantize(Decimal("0.01")))


def _checkout_return_url(checkout_id: Any) -> str:
    parsed = urlparse(settings.TBC_RETURN_URL)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["checkout_id"] = str(checkout_id)
    return urlunparse(parsed._replace(query=urlencode(query)))


class ManualGateway:
    name = "manual"

    def create_checkout(self, _checkout, _user, _plan: PlanDefinition, _language: str) -> Dict[str, Any]:
        return {
            "provider": self.name,
            "method_id": "manual_invoice",
            "status": "available",
            "instruction_code": "contact_for_invoice",
            "contact_email": settings.BILLING_CONTACT_EMAIL,
            "redirect_url": None,
        }


class TBCGateway:
    """Minimal TBC E-Commerce adapter with bounded HTTP and strict parsing."""

    name = "tbc"
    _token_lock = Lock()
    _cached_token: Optional[str] = None
    _cached_token_until: float = 0

    def __init__(self, *, transport: httpx.BaseTransport | None = None):
        if not tbc_checkout_ready():
            raise GatewayUnavailable("tbc_checkout_not_configured")
        self._transport = transport

    @property
    def _base_url(self) -> str:
        return settings.TBC_API_BASE_URL.rstrip("/")

    def _request_json(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            with httpx.Client(
                base_url=self._base_url,
                timeout=settings.TBC_HTTP_TIMEOUT_SECONDS,
                follow_redirects=False,
                transport=self._transport,
            ) as client:
                response = client.request(method, path, **kwargs)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderRequestError("tbc_request_failed") from exc
        if not isinstance(payload, dict):
            raise ProviderRequestError("tbc_invalid_response")
        return payload

    def _access_token(self) -> str:
        now = monotonic()
        gateway_type = type(self)
        with gateway_type._token_lock:
            if gateway_type._cached_token and gateway_type._cached_token_until > now + 30:
                return gateway_type._cached_token
            payload = self._request_json(
                "POST",
                "/v1/tpay/access-token",
                headers={
                    "apikey": _secret_value(settings.TBC_API_KEY),
                    "Accept": "application/json",
                },
                data={
                    "client_id": _secret_value(settings.TBC_CLIENT_ID),
                    "client_secret": _secret_value(settings.TBC_CLIENT_SECRET),
                },
            )
            token = payload.get("access_token")
            token_type = payload.get("token_type")
            expires_in = payload.get("expires_in")
            if (
                not isinstance(token, str)
                or not token
                or not isinstance(token_type, str)
                or token_type.lower() != "bearer"
            ):
                raise ProviderRequestError("tbc_invalid_access_token")
            if not isinstance(expires_in, int) or not 60 <= expires_in <= 172_800:
                raise ProviderRequestError("tbc_invalid_access_token_expiry")
            gateway_type._cached_token = token
            gateway_type._cached_token_until = now + expires_in
            return token

    def _authorized_headers(self) -> dict[str, str]:
        return {
            "apikey": _secret_value(settings.TBC_API_KEY),
            "Authorization": f"Bearer {self._access_token()}",
            "Accept": "application/json",
        }

    @staticmethod
    def _validate_payment_id(value: Any) -> str:
        if not isinstance(value, str) or not TBC_PAYMENT_ID_RE.fullmatch(value):
            raise ProviderRequestError("tbc_invalid_payment_id")
        return value

    @staticmethod
    def _approval_url(payload: dict[str, Any]) -> str:
        links = payload.get("links")
        if not isinstance(links, list):
            raise ProviderRequestError("tbc_missing_approval_url")
        for link in links:
            if not isinstance(link, dict) or link.get("rel") != "approval_url":
                continue
            uri = link.get("uri")
            method = str(link.get("method", "")).upper()
            if not isinstance(uri, str) or method != "REDIRECT":
                break
            parsed = urlparse(uri)
            if (
                parsed.scheme != "https"
                or parsed.hostname != "tpay.tbcbank.ge"
                or parsed.port not in {None, 443}
                or parsed.username
                or parsed.password
            ):
                raise ProviderRequestError("tbc_untrusted_approval_url")
            return uri
        raise ProviderRequestError("tbc_missing_approval_url")

    def create_checkout(self, checkout, _user, plan: PlanDefinition, language: str) -> Dict[str, Any]:
        bank_language = "KA" if language == "ka" else "EN"
        expiration_minutes = settings.TBC_CHECKOUT_EXPIRATION_MINUTES
        payload = self._request_json(
            "POST",
            "/v1/tpay/payments",
            headers={**self._authorized_headers(), "Content-Type": "application/json"},
            json={
                "amount": {
                    "currency": checkout.currency,
                    "total": _provider_amount_from_minor(checkout.amount_minor),
                },
                "returnurl": _checkout_return_url(checkout.id),
                "callbackUrl": settings.TBC_CALLBACK_URL,
                "expirationMinutes": expiration_minutes,
                "preAuth": False,
                "language": bank_language,
                "merchantPaymentId": str(checkout.id),
                "description": f"Tax Advisor {plan.name}"[:30],
            },
        )
        payment_id = self._validate_payment_id(payload.get("payId"))
        status = payload.get("status")
        if status != "Created":
            raise ProviderRequestError("tbc_unexpected_create_status")
        if payload.get("currency") != checkout.currency:
            raise ProviderRequestError("tbc_create_currency_mismatch")
        if _minor_from_provider_amount(payload.get("amount")) != checkout.amount_minor:
            raise ProviderRequestError("tbc_create_amount_mismatch")
        result = ProviderCheckout(
            provider_order_id=payment_id,
            provider_status=status,
            redirect_url=self._approval_url(payload),
            expires_in_minutes=expiration_minutes,
        )
        return {
            "provider": self.name,
            "method_id": "tbc_checkout",
            "status": "available",
            "instruction_code": "redirect_to_bank",
            "contact_email": None,
            "redirect_url": result.redirect_url,
            "provider_order_id": result.provider_order_id,
            "provider_status": result.provider_status,
            "expires_in_minutes": result.expires_in_minutes,
        }

    def get_payment(self, provider_order_id: str) -> ProviderPayment:
        payment_id = self._validate_payment_id(provider_order_id)
        payload = self._request_json(
            "GET",
            f"/v1/tpay/payments/{payment_id}",
            headers=self._authorized_headers(),
        )
        response_payment_id = self._validate_payment_id(payload.get("payId"))
        if response_payment_id != payment_id:
            raise ProviderRequestError("tbc_payment_id_mismatch")
        status = payload.get("status")
        if status not in TBC_KNOWN_STATUSES:
            raise ProviderRequestError("tbc_unknown_payment_status")
        currency = payload.get("currency")
        if not isinstance(currency, str) or currency not in {"GEL", "USD", "EUR"}:
            raise ProviderRequestError("tbc_invalid_currency")
        return ProviderPayment(
            provider_order_id=payment_id,
            status=status,
            amount_minor=_minor_from_provider_amount(payload.get("amount")),
            currency=currency,
        )


def payment_methods(*, include_contact: bool = False) -> list[dict[str, Any]]:
    """Return honest provider readiness without exposing configuration."""
    return [
        {
            "id": "manual_invoice",
            "provider": "manual",
            "status": "available",
            "recurring": False,
            "contact_email": settings.BILLING_CONTACT_EMAIL if include_contact else None,
        },
        {
            "id": "tbc_checkout",
            "provider": "tbc",
            "status": "available" if tbc_checkout_ready() else "requires_merchant_activation",
            "recurring": False,
            "contact_email": None,
        },
        {
            "id": "bog_checkout",
            "provider": "bog",
            "status": "requires_merchant_activation",
            "recurring": True,
            "contact_email": None,
        },
    ]


def get_gateway(provider: str = "manual"):
    if provider == "manual":
        return ManualGateway()
    if provider == "tbc":
        return TBCGateway()
    raise GatewayUnavailable(f"payment_provider_not_available:{provider}")
