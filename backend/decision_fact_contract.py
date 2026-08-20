"""Deterministic normalization contract for extracted dispute-decision facts.

The LLM payload is never trusted as database-ready data. This module stays
dependency-light so its safety rules can run in CI without an LLM SDK or a
database connection.
"""

from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any


EXTRACTION_VERSION = 2
MAX_ARTICLE_REFS = 20
MAX_PRIOR_REFS = 10
MAX_OUTPUT_TOKENS = 1600

AUTHORITY_BODIES = {
    "revenue_service_council",
    "mof_dispute_council",
    "city_court",
    "appeals_court",
    "supreme_court",
    "other",
}
DISPUTE_TYPES = {"tax", "customs", "both", "other"}
OUTCOMES = {"satisfied", "partially_satisfied", "rejected", "unclear"}
IN_FAVOR = {"taxpayer", "authority", "partial", "unclear"}


def llm_options(*, model: str, api_key: str) -> dict[str, Any]:
    """Dependency-free ChatOpenAI options shared by runtime and CI."""
    return {
        "model": model,
        "temperature": 0,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "openai_api_key": api_key,
        "model_kwargs": {"response_format": {"type": "json_object"}},
    }


def parse_date(value: Any):
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def normalize_reference_number(value: Any) -> str:
    """Comparable decision reference without display punctuation or spaces."""
    text = str(value or "").strip()
    text = re.sub(r"^[№N#\s]+", "", text, flags=re.IGNORECASE)
    return re.sub(r"[^0-9/\-]", "", text)


def clean_amount(value: Any):
    """A disputed GEL amount must be finite and strictly positive."""
    try:
        amount = float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    if amount is None or not math.isfinite(amount) or amount <= 0:
        return None
    return amount


def clean_article_refs(value: Any, *, limit: int = MAX_ARTICLE_REFS) -> list[str]:
    """Trim and deduplicate references without rewriting legal numbering.

    Georgian legislation contains inserted/superscript articles (for example
    ``98²``). Their spelling is preserved for expert review instead of being
    forced into a lossy numeric format.
    """
    if not isinstance(value, list):
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in value:
        article = str(item or "").strip()
        if not article or article in seen:
            continue
        seen.add(article)
        cleaned.append(article)
        if len(cleaned) >= limit:
            break
    return cleaned


def clean_prior_refs(
    value: Any,
    *,
    own_decision_number: Any = None,
    limit: int = MAX_PRIOR_REFS,
) -> list[dict[str, Any]]:
    """Normalize lower-instance references and reject self-references."""
    if not isinstance(value, list):
        return []
    own_number = normalize_reference_number(own_decision_number)
    cleaned: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        number = str(item.get("number") or "").strip()
        normalized_number = normalize_reference_number(number)
        if not number or (own_number and normalized_number == own_number):
            continue
        body = str(item.get("body") or "").strip()
        ref_date = parse_date(item.get("date"))
        cleaned.append(
            {
                "number": number,
                "body": body if body in AUTHORITY_BODIES else None,
                "date": ref_date.isoformat() if ref_date else None,
            }
        )
        if len(cleaned) >= limit:
            break
    return cleaned


def normalize(payload: dict[str, Any]) -> dict[str, Any]:
    """Convert an untrusted extraction payload into database-safe fields."""

    def pick(value: Any, allowed: set[str], default: str = "unclear") -> str:
        normalized = str(value or "").strip()
        return normalized if normalized in allowed else default

    decision_number = str(payload.get("decision_number") or "").strip() or None
    prior_refs = clean_prior_refs(
        payload.get("prior_decisions"), own_decision_number=decision_number
    )
    return {
        "case_number": str(payload.get("case_number") or "").strip() or None,
        "prior_refs": prior_refs,
        "prior_body": prior_refs[0]["body"] if prior_refs else None,
        "authority_body": pick(payload.get("authority_body"), AUTHORITY_BODIES, "other"),
        "decision_number": decision_number,
        "decision_date": parse_date(payload.get("decision_date")),
        "dispute_type": pick(payload.get("dispute_type"), DISPUTE_TYPES, "other"),
        "contested_articles": clean_article_refs(payload.get("contested_articles")),
        "amount_gel": clean_amount(payload.get("amount_gel")),
        "outcome": pick(payload.get("outcome"), OUTCOMES),
        "in_favor": pick(payload.get("in_favor"), IN_FAVOR),
    }
