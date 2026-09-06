"""Payment-provider capabilities behind one stable billing interface.

Only the manual invoice provider is executable today.  Automated providers are
listed explicitly as unavailable until merchant onboarding and a verified
adapter are complete; credentials can therefore never activate unfinished code.
"""
from typing import Any, Dict

from billing.catalog import PlanDefinition
from core.config import settings


class ManualGateway:
    name = "manual"

    def create_checkout(self, user, plan: PlanDefinition) -> Dict[str, Any]:
        del user, plan
        return {
            "provider": self.name,
            "method_id": "manual_invoice",
            "status": "available",
            "instruction_code": "contact_for_invoice",
            "contact_email": settings.BILLING_CONTACT_EMAIL,
        }


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
            "status": "requires_merchant_activation",
            "recurring": True,
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
    raise ValueError(f"Payment provider is not available: {provider}")
