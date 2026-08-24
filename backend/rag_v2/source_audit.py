from __future__ import annotations

import re
from typing import Any, Dict
from .models import ParsedQuery, QuestionClassification


def _extract_dispute_ref_from_title(title: str) -> str:
    match = re.search(r"№\s*([0-9]+/[0-9]+/[0-9]{4})", title or "")
    return match.group(1).strip() if match else ""


def audit_sources(parsed: ParsedQuery, classification: QuestionClassification, reranking: Dict[str, Any]) -> Dict[str, Any]:
    ranked = reranking.get("top_ranked_documents", [])
    primary = ranked[0] if ranked else None

    checks = {
        "has_primary_source": primary is not None,
        "question_class_consistency": True,
        "source_type_consistency": True,
        "subject_consistency": True,
        "named_document_directness": True,
        "no_dispute_noise": True,
        "current_source_consistency": True,
    }
    warnings = []

    if classification.question_class == "named_document_lookup":
        if not primary or primary.get("channel") not in {"exact_doc_resolver", "citation_resolver"}:
            checks["named_document_directness"] = False
            checks["question_class_consistency"] = False
            warnings.append("named document query did not resolve through a direct document resolution channel")

    if classification.question_class == "canonical_law_lookup":
        if primary and primary.get("document_type") == "court_decision":
            checks["source_type_consistency"] = False
            checks["no_dispute_noise"] = False
            warnings.append("canonical law question surfaced dispute practice as primary source")

    if classification.question_class == "dispute_practice":
        if primary and primary.get("document_type") != "court_decision":
            checks["source_type_consistency"] = False
            checks["question_class_consistency"] = False
            warnings.append("dispute question did not surface court decision as primary source")
        requested_ref = (parsed.decision_ref or parsed.document_ref or "").strip()
        resolved_ref = _extract_dispute_ref_from_title(primary.get("title") or "") if primary else ""
        if requested_ref and resolved_ref != requested_ref:
            checks["question_class_consistency"] = False
            checks["named_document_directness"] = False
            warnings.append("dispute query resolved without an exact dispute reference match")

    if classification.question_class == "practical_tax_guidance":
        if primary and primary.get("document_type") == "court_decision":
            checks["source_type_consistency"] = False
            checks["no_dispute_noise"] = False
            warnings.append("practical guidance question surfaced dispute material as primary source")

    if classification.question_class in {
        "canonical_law_lookup",
        "practical_tax_guidance",
        "local_regulation_lookup",
        "amendment_tracking",
    }:
        metadata = primary.get("metadata", {}) if primary else {}
        if primary and metadata.get("is_current") is False:
            checks["current_source_consistency"] = False
            warnings.append("primary legal source is not marked current")

    if classification.question_class == "local_regulation_lookup":
        if primary and primary.get("document_type") != "regulation":
            checks["source_type_consistency"] = False
            checks["question_class_consistency"] = False
            warnings.append("local regulation query did not surface a regulation as primary source")

    if classification.question_class == "amendment_tracking":
        metadata = primary.get("metadata", {}) if primary else {}
        if primary and primary.get("document_type") not in {"law", "regulation"}:
            checks["source_type_consistency"] = False
            checks["question_class_consistency"] = False
            warnings.append("amendment-tracking query did not surface law/regulation as primary source")
        elif primary and metadata.get("is_current") is False:
            checks["source_type_consistency"] = False

    passed = all(checks.values())

    return {
        "passed": passed,
        "checks": checks,
        "warnings": warnings,
    }
