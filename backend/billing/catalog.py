"""Authoritative subscription catalog shared by billing API contracts.

Money is stored in integer minor units.  Public copy is localized by the
frontend; the backend exposes stable feature codes rather than marketing text.
"""
from dataclasses import asdict, dataclass
from typing import Optional


@dataclass(frozen=True)
class PlanDefinition:
    id: str
    name: str
    price_minor: int
    currency: str
    billing_period: Optional[str]
    daily_questions: Optional[int]
    history_enabled: bool
    feature_codes: tuple[str, ...]
    highlighted: bool = False
    pricing_preliminary: bool = True

    def public_dict(self) -> dict:
        payload = asdict(self)
        payload["feature_codes"] = list(self.feature_codes)
        return payload


PLAN_CATALOG_VERSION = "2026-09-07"

PLAN_CATALOG: dict[str, PlanDefinition] = {
    "free": PlanDefinition(
        id="free",
        name="Free",
        price_minor=0,
        currency="GEL",
        billing_period=None,
        daily_questions=5,
        history_enabled=False,
        feature_codes=(
            "daily_questions_5",
            "precise_sources",
            "no_chat_history",
        ),
    ),
    "pro": PlanDefinition(
        id="pro",
        name="Pro",
        price_minor=4_900,
        currency="GEL",
        billing_period="month",
        daily_questions=None,
        history_enabled=True,
        feature_codes=(
            "unlimited_questions",
            "chat_history",
            "dispute_statistics",
            "law_change_timeline",
        ),
        highlighted=True,
    ),
    "business": PlanDefinition(
        id="business",
        name="Business",
        price_minor=14_900,
        currency="GEL",
        billing_period="month",
        daily_questions=None,
        history_enabled=True,
        feature_codes=(
            "everything_in_pro",
            "company_invoice",
            "priority_support",
        ),
    ),
}

PLAN_ORDER = {"free": 0, "pro": 1, "business": 2}


def get_plan(plan_id: str) -> PlanDefinition:
    """Return one catalog plan or raise a stable lookup error."""
    try:
        return PLAN_CATALOG[plan_id]
    except KeyError as exc:
        raise ValueError(f"Unknown billing plan: {plan_id}") from exc


def public_catalog() -> dict:
    return {
        "version": PLAN_CATALOG_VERSION,
        "currency_minor_unit": 2,
        "plans": [plan.public_dict() for plan in PLAN_CATALOG.values()],
    }
