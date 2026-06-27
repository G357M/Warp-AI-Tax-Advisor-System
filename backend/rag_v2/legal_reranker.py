from __future__ import annotations

from typing import Any, Dict, List
from .models import ParsedQuery, QuestionClassification, CandidateDocument
from .rerank_policy import score_weights
from .specificity_scorer import specificity_score


AUTHORITY_WEIGHTS = {
    "law": 0.22,
    "regulation": 0.16,
    "guideline": 0.18,
    "court_decision": 0.18,
    "news": 0.08,
    None: 0.0,
}


CHANNEL_TYPE_COMPONENTS = {
    "exact_doc_resolver": (0.08, 0.0, 0.0, 0.0),
    "citation_resolver": (0.07, 0.0, 0.0, 0.0),
    "article_resolver": (0.08, 0.0, 0.0, 0.0),
    "point_resolver": (0.08, 0.0, 0.0, 0.0),
    "metadata_search": (0.0, 0.0, 0.07, 0.0),
    "bm25_search": (0.0, 0.06, 0.0, 0.0),
    "semantic_search": (0.0, 0.0, 0.0, 0.06),
}


def _class_fit(question_class: str, doc_type: str | None) -> float:
    if question_class == "canonical_law_lookup":
        return 0.28 if doc_type == "law" else 0.14 if doc_type == "regulation" else 0.0
    if question_class == "practical_tax_guidance":
        return 0.28 if doc_type == "guideline" else 0.18 if doc_type == "law" else 0.12 if doc_type == "regulation" else 0.0
    if question_class == "local_regulation_lookup":
        return 0.30 if doc_type == "regulation" else 0.12 if doc_type == "law" else 0.0
    if question_class == "dispute_practice":
        return 0.32 if doc_type == "court_decision" else 0.0
    if question_class == "named_document_lookup":
        return 0.35
    if question_class == "amendment_tracking":
        return 0.22 if doc_type == "law" else 0.10
    return 0.0


def _subject_match(parsed: ParsedQuery, candidate: CandidateDocument) -> float:
    hay = (candidate.title + " " + (candidate.why or "")).lower()
    if parsed.subject == "individual" and any(token in hay for token in ["ფიზიკური", "individual", "физичес"]):
        return 0.15
    if parsed.subject == "legal_entity" and any(token in hay for token in ["company", "юридичес", "компан"]):
        return 0.15
    return 0.0


def _goal_match(parsed: ParsedQuery, candidate: CandidateDocument) -> float:
    hay = (candidate.title + " " + (candidate.why or "")).lower()
    if parsed.goal == "document_summary":
        return 0.20 if candidate.channel in {"exact_doc_resolver", "citation_resolver"} else 0.0
    if parsed.goal == "calculation_rule" and any(token in hay for token in ["property", "ქონების", "имуще", "calculate", "guidance"]):
        return 0.14
    if parsed.goal == "dispute_outcome" and candidate.document_type == "court_decision":
        return 0.18
    if parsed.goal == "rate_lookup" and candidate.document_type in {"law", "regulation"}:
        return 0.12
    return 0.0


def _freshness_score(candidate: CandidateDocument) -> float:
    metadata = candidate.metadata or {}
    if metadata.get("is_current") is True:
        return 0.04
    if metadata.get("recency_bucket") == "recent":
        return 0.03
    if metadata.get("recency_bucket") == "stale":
        return -0.02
    return 0.0


def _channel_support(candidate: CandidateDocument) -> Dict[str, float]:
    metadata = candidate.metadata or {}
    retrieval_scores = dict(metadata.get("retrieval_scores", {}))
    lexical = 0.0
    semantic = 0.0
    metadata_support = 0.0
    exactness = 0.0

    for channel_name, score in retrieval_scores.items():
        exact_base, lexical_base, metadata_base, semantic_base = CHANNEL_TYPE_COMPONENTS.get(channel_name, (0.0, 0.0, 0.0, 0.0))
        capped = min(max(float(score), 0.0), 1.0)
        exactness = max(exactness, exact_base * capped)
        lexical = max(lexical, lexical_base * capped)
        metadata_support = max(metadata_support, metadata_base * capped)
        semantic = max(semantic, semantic_base * capped)

    if candidate.channel in {"exact_doc_resolver", "citation_resolver", "article_resolver", "point_resolver"}:
        exactness = max(exactness, 0.06)

    return {
        "exactness": exactness,
        "lexical_support": lexical,
        "metadata_support": metadata_support,
        "semantic_support": semantic,
    }


def rerank_candidates(
    parsed: ParsedQuery,
    classification: QuestionClassification,
    candidates: List[CandidateDocument],
) -> Dict[str, Any]:
    weights = score_weights(classification.question_class)
    ranked = []
    rejected = []

    for candidate in candidates:
        authority = AUTHORITY_WEIGHTS.get(candidate.document_type, 0.0)
        class_fit = _class_fit(classification.question_class, candidate.document_type)
        subject_match = _subject_match(parsed, candidate)
        goal_match = _goal_match(parsed, candidate)
        specificity = specificity_score(parsed, candidate)
        merged_channels = candidate.metadata.get("merged_channels", []) if candidate.metadata else []
        merge_bonus = min(len(merged_channels), 4) * 0.03 if merged_channels else 0.0
        channel_support = _channel_support(candidate)
        freshness = _freshness_score(candidate)

        weighted_components = {
            "class_fit": class_fit * weights["class_fit"],
            "authority": authority * weights["authority"],
            "subject_match": subject_match * weights["subject_match"],
            "goal_match": goal_match * weights["goal_match"],
            "specificity": specificity * weights["specificity"],
            "exactness": channel_support["exactness"] * weights["exactness"],
            "lexical_support": channel_support["lexical_support"] * weights["lexical_support"],
            "semantic_support": channel_support["semantic_support"] * weights["semantic_support"],
            "metadata_support": channel_support["metadata_support"] * weights["metadata_support"],
            "freshness": freshness * weights["freshness"],
            "merge_bonus": merge_bonus * weights["merge_bonus"],
        }
        final_score = sum(weighted_components.values())

        ranked.append({
            "document_id": candidate.document_id,
            "title": candidate.title,
            "document_type": candidate.document_type,
            "source_url": candidate.source_url,
            "channel": candidate.channel,
            "final_score": round(final_score, 4),
            "score_breakdown": {k: round(v, 4) for k, v in weighted_components.items()},
            "why_selected": [candidate.why] if candidate.why else [],
            "merged_channels": merged_channels,
            "metadata": candidate.metadata,
        })

    ranked.sort(key=lambda x: x["final_score"], reverse=True)

    filtered_ranked = []
    for item in ranked:
        if classification.question_class == "canonical_law_lookup" and item["document_type"] == "court_decision":
            rejected.append({
                "document_id": item["document_id"],
                "title": item["title"],
                "reason": "court decisions excluded for canonical law lookup",
            })
            continue
        if classification.question_class == "dispute_practice" and item["document_type"] != "court_decision":
            rejected.append({
                "document_id": item["document_id"],
                "title": item["title"],
                "reason": "non-dispute source excluded for dispute-practice query",
            })
            continue
        filtered_ranked.append(item)

    return {
        "top_ranked_documents": filtered_ranked[:10],
        "rejected_candidates": rejected,
        "policy_weights": weights,
    }
