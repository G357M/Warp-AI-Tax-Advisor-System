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


# News subcategories shown on the public /news page. Classification is
# rule-based here (title + original infohub type string kept in metadata);
# documents no rule matches stay NULL and are resolved by the LLM fallback in
# scripts/classify_news_subtypes.py (anything it can't place becomes 'general').
NEWS_SUBTYPES = {
    "treaty",              # double-taxation avoidance & other interstate agreements
    "loss_norms",          # industry loss-norm instructions
    "dispute_decisions",   # dispute council / court decision publications
    "cjeu_practice",       # EU Court of Justice (CJEU) decision translations
    "guidance",            # methodological / situational / procedural guides
    "legislation",         # laws, bills, code amendments
    "orders_resolutions",  # minister orders, government resolutions
    "general",             # everything else (LLM fallback catch-all)
}


def classify_news_subtype(title: str, metadata: Dict[str, Any]) -> Optional[str]:
    """Rule-based news subcategory; None when no rule fires (LLM decides later).

    Rules are ordered: loss norms are approved by orders and dispute decisions
    reference laws, so the specific buckets must win before the generic ones.
    """
    title = title or ""
    lowered_title = title.lower()
    meta_type = str(metadata.get("type") or "").lower()
    base_type = str(metadata.get("baseType") or "").lower()
    species = str(metadata.get("species") or "").lower()
    combined = f"{lowered_title} {meta_type}"

    # Situational-guide announcements carry the guide TOPIC as their type
    # ("0301 - უიმედო ვალი (სასამართლოს გადაწყვეტილება...)") — topic wording
    # can contain anything, so decide by the numbered-type shape / baseType
    # BEFORE any keyword rule (guide N 0301 was landing in dispute_decisions).
    if re.match(r"^\d{4}\b", meta_type) or "სახელმძღვანელო" in base_type or "მეთოდური მითითებ" in base_type:
        return "guidance"
    # CJEU decision translations get their own shelf; must precede the
    # dispute rule (the type string ends with "გადაწყვეტილება" too).
    if "მართლმსაჯულების სასამართლო" in combined or "cjeu" in combined:
        return "cjeu_practice"

    # Interstate / intergovernmental agreements (double-taxation treaties).
    if "სახელმწიფოთაშორისი" in meta_type or "მთავრობათაშორისი" in meta_type:
        return "treaty"
    if "ორმაგი დაბეგვრ" in combined:
        return "treaty"
    # "საგადასახადო შეთანხმება" is the domestic taxpayer–Revenue-Service
    # agreement (TC art. 289), not an international treaty — exclude it.
    if (
        ("შეთანხმებ" in combined or "ხელშეკრულებ" in combined)
        and ("დაბეგვრ" in combined or "გადასახად" in combined)
        and "საგადასახადო შეთანხმებ" not in combined
    ):
        return "treaty"
    # Industry loss norms — must precede orders_resolutions (norms are
    # approved by orders: "ბრძანება ... დანაკარგების ნორმების დამტკიცების შესახებ").
    if "დანაკარგ" in combined:
        return "loss_norms"
    if "ნორმ" in combined and "ინსტრუქცი" in combined:
        return "loss_norms"
    # Dispute-decision publications.
    if "გადაწყვეტილ" in meta_type:
        return "dispute_decisions"
    if "დავების გადაწყვეტილ" in combined or "საჯარო გადაწყვეტილ" in combined:
        return "dispute_decisions"
    # Guidance content.
    if any(
        token in combined
        for token in ("მეთოდური მითითებ", "სიტუაციური სახელმძღვანელო", "პროცედურული სახელმძღვანელო")
    ):
        return "guidance"
    if re.search(r"N ?[0-9]{3,5}\s*$", title):
        return "guidance"
    # Subordinate normative acts read as orders, not primary legislation.
    if "კანონქვემდებარე" in combined:
        return "orders_resolutions"
    # Primary legislation: bills, code/law amendments, laws.
    if species == "bill" or "კანონპროექტ" in combined:
        return "legislation"
    if any(
        token in combined
        for token in ("კანონში ცვლილებ", "კოდექსში ცვლილებ", "საკანონმდებლო", "პარლამენტ")
    ):
        return "legislation"
    if "კონსტიტუცი" in meta_type or "კანონი" in meta_type or "საქართველოს კანონი" in lowered_title:
        return "legislation"
    # Minister orders and government resolutions.
    if "ბრძანებ" in combined or "დადგენილებ" in combined:
        return "orders_resolutions"
    return None


def parse_receipt_date(value: Any) -> Optional[date]:
    """Parse InfoHub's ``receiptDate`` (ISO ``2026-06-26T00:00:00``) into a date."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        return None
