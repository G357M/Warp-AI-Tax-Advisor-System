"""Normalization helpers shared by the nightly API scraper and backfill scripts.

``infer_document_type`` mirrors the canonical taxonomy of the bulk corpus
pipeline (corpus-tools/export_pipeline/infohub_exporter.py) so that documents
ingested nightly land in the same buckets the RAG lanes filter on
(law | regulation | court_decision | guideline | bill | news).
"""
import re
from datetime import date, datetime
from typing import Any, Dict, Optional


def infer_document_type(title: str, metadata: Dict[str, Any]) -> str:
    lowered = " ".join(
        [
            title or "",
            str(metadata.get("description", "")),
            str(metadata.get("type", "")),
            str(metadata.get("baseType", "")),
            str(metadata.get("species", "")),
        ]
    ).lower()
    if "კანონპროექტ" in lowered or "bill" in lowered or "species=bill" in lowered:
        return "bill"
    if any(
        token in lowered
        for token in [
            "ფინანსთა სამინისტროს დავების გადაწყვეტილება",
            "შემოსავლების სამსახურის დავების გადაწყვეტილება",
            "დავების გადაწყვეტილ",
        ]
    ):
        return "court_decision"
    if any(
        token in lowered
        for token in [
            "საკანონმდებლო აქტში ცვლილება",
            "კოდექსში ცვლილების შეტანის შესახებ",
            "კანონში ცვლილების შეტანის შესახებ",
            "კანონში ცვლილების შეტანის თაობაზე",
            "კონსტიტუციურ კანონში ცვლილების",
        ]
    ):
        return "law"
    if any(token in lowered for token in ["კანონქვემდებარე ნორმატიული აქტი", "დადგენილება", "დადგენილებაში ცვლილება", "ბრძანებ", "მინისტრის", "მთავრობის"]):
        return "regulation"
    if any(token in lowered for token in ["დავების გადაწყვეტილ", "გადაწყვეტილ", "decision"]):
        return "court_decision"
    if "ბრძანებ" in lowered or "order" in lowered:
        return "regulation"
    if "კანონი" in lowered or "law" in lowered:
        return "law"
    if "რეგულ" in lowered or "regulation" in lowered:
        return "regulation"
    # Situational guides ("სიტუაციური სახელმძღვანელო"): titled as a tax topic
    # plus the guide number, e.g. "…დღგ-ით დაბეგვრა N 1190".
    if re.search(r"N ?[0-9]{3,5}\s*$", title or ""):
        return "guideline"
    # Methodical instructions and the situational-guides registry are guidance
    # content even when posted through LegislativeNews.
    if "მეთოდური მითითებ" in lowered or "სიტუაციური სახელმძღვანელო" in lowered:
        return "guideline"
    if "legislativenews" in lowered or "news" in lowered or "სიახლე" in lowered:
        return "news"
    return "guideline"


def parse_receipt_date(value: Any) -> Optional[date]:
    """Parse InfoHub's ``receiptDate`` (ISO ``2026-06-26T00:00:00``) into a date."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        return None
