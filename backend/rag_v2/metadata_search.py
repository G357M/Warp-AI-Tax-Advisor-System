from __future__ import annotations

from typing import Dict, List

from .fixtures_metadata import DOCUMENT_FIXTURES
from .models import ParsedQuery, CandidateDocument
from .faq_tax_matrix import (
    CANONICAL_RATE_ARTICLES,
    match_tax_faq_entry_for_parsed,
)
from .official_provisions import load_official_provision_registries


CANONICAL_GOAL_ARTICLES = {
    "residency_status": "34",
    "penalty_rate": "272",
    "exemption_status": "172",
}


def _score_fixture(parsed: ParsedQuery, doc: Dict[str, object]) -> tuple[float, List[str]]:
    score = 0.0
    why: List[str] = []

    topics = set(doc.get("topics", []))
    subjects = set(doc.get("subjects", []))
    goals = set(doc.get("goals", []))
    localities = set(doc.get("localities", []))
    authority_rank = float(doc.get("authority_rank", 0.0))

    if parsed.topic and parsed.topic in topics:
        score += 0.35
        why.append(f"topic matched: {parsed.topic}")

    if parsed.subject and parsed.subject in subjects:
        score += 0.20
        why.append(f"subject matched: {parsed.subject}")

    if parsed.goal and parsed.goal in goals:
        score += 0.25
        why.append(f"goal matched: {parsed.goal}")

    if parsed.locality and parsed.locality in localities:
        score += 0.22
        why.append(f"locality matched: {parsed.locality}")

    score += authority_rank * 0.20
    if authority_rank:
        why.append(f"authority rank contributed: {authority_rank:.2f}")

    return round(score, 4), why


def search_metadata(parsed: ParsedQuery, limit: int = 5) -> List[CandidateDocument]:
    scored: List[CandidateDocument] = []
    contract = match_tax_faq_entry_for_parsed(parsed)
    contract_registry = next(
        (
            registry
            for registry in load_official_provision_registries()
            if contract is not None and registry["registry_id"] == contract.registry_id
        ),
        None,
    )

    for doc in DOCUMENT_FIXTURES:
        if (
            contract is not None
            and "საგადასახადო კოდექსში ცვლილების შეტანის შესახებ" in str(doc.get("title", ""))
        ):
            continue

        score, why_parts = _score_fixture(parsed, doc)
        doc_topics = set(doc.get("topics", []))
        doc_goals = set(doc.get("goals", []))
        has_topic_match = bool(parsed.topic and parsed.topic in doc_topics)
        has_goal_match = bool(parsed.goal and parsed.goal in doc_goals)
        has_canonical_goal_match = bool(
            parsed.goal in CANONICAL_GOAL_ARTICLES
            and str(doc.get("title")) == "საქართველოს საგადასახადო კოდექსი."
        )
        has_contract_match = bool(
            contract is not None
            and contract_registry is not None
            and str(doc.get("source_url")) == contract_registry["infohub_source_url"]
        )
        if has_contract_match:
            score = max(score, 0.99)
            why_parts.append(
                f"legal-answer contract provision matched: {contract.article_ref}"
            )

        if not (
            has_topic_match
            or has_goal_match
            or has_canonical_goal_match
            or has_contract_match
        ):
            continue
        if score <= 0:
            continue

        metadata = {
            "topics": list(doc.get("topics", [])),
            "subjects": list(doc.get("subjects", [])),
            "goals": list(doc.get("goals", [])),
            "localities": list(doc.get("localities", [])),
            "authority_rank": doc.get("authority_rank"),
            "is_current": doc.get("is_current"),
            "recency_bucket": doc.get("recency_bucket"),
        }
        if has_contract_match:
            article_ref = contract.article_ref
            metadata.update(
                {"article_ref": article_ref, "section_label": f"მუხლი {article_ref}"}
            )
        elif (
            parsed.topic in CANONICAL_RATE_ARTICLES
            and parsed.goal == "rate_lookup"
            and str(doc.get("title")) == "საქართველოს საგადასახადო კოდექსი."
        ):
            article_ref = CANONICAL_RATE_ARTICLES[parsed.topic]
            metadata.update({"article_ref": article_ref, "section_label": f"მუხლი {article_ref}"})
        elif (
            parsed.goal in CANONICAL_GOAL_ARTICLES
            and str(doc.get("title")) == "საქართველოს საგადასახადო კოდექსი."
        ):
            article_ref = CANONICAL_GOAL_ARTICLES[parsed.goal]
            metadata.update(
                {"article_ref": article_ref, "section_label": f"მუხლი {article_ref}"}
            )
        elif (
            parsed.goal == "small_business_eligibility"
            and str(doc.get("title")) == "საქართველოს საგადასახადო კოდექსი."
        ):
            metadata.update({"article_ref": "88", "section_label": "მუხლი 88"})

        scored.append(
            CandidateDocument(
                channel="metadata_search",
                document_id=str(doc["document_id"]),
                title=str(doc["title"]),
                document_type=str(doc["document_type"]),
                source_url=str(doc["source_url"]),
                channel_score=score,
                why="; ".join(why_parts),
                metadata=metadata,
            )
        )

    scored.sort(key=lambda x: x.channel_score, reverse=True)
    return scored[:limit]
