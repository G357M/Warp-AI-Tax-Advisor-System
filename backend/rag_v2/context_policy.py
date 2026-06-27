from __future__ import annotations

from typing import Dict, List


ALLOWED_SUPPORT_TYPES = {
    "canonical_law_lookup": {"law", "regulation"},
    "practical_tax_guidance": {"guideline", "law", "regulation"},
    "local_regulation_lookup": {"regulation", "law"},
    "dispute_practice": {"court_decision"},
    "named_document_lookup": {"guideline", "law", "regulation", "court_decision"},
    "amendment_tracking": {"law", "regulation"},
}


def filter_supporting_sources(question_class: str, top_ranked_documents: List[Dict[str, object]]) -> Dict[str, List[Dict[str, object]]]:
    allowed = ALLOWED_SUPPORT_TYPES.get(question_class, set())
    kept: List[Dict[str, object]] = []
    excluded: List[Dict[str, object]] = []

    for item in top_ranked_documents:
        if item.get("document_type") in allowed:
            kept.append(item)
        else:
            excluded.append({
                "document_id": item.get("document_id"),
                "title": item.get("title"),
                "reason": f"support source type {item.get('document_type')} excluded for {question_class}",
            })

    return {
        "kept": kept,
        "excluded": excluded,
    }
