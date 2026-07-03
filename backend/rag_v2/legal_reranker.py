from __future__ import annotations

import math
import re
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


# --- Same-document chunk tie-break (Phase B, attempt 4) ---
#
# Phase A found: a large source document (e.g. the Tax Code) often discusses one
# topic across many chunks that are semantically similar but functionally
# different (definition vs. exception vs. repealed clause vs. procedure) --
# cosine similarity alone can't reliably tell those apart, and previously
# candidate_merger.py silently collapsed all same-document chunks down to one
# before the reranker ever saw more than one (fixed separately, see
# candidate_merger.py's chunk-aware key).
#
# Attempts 1-3 tried folding a chunk-content-aware bonus into the MAIN additive
# score. Even a small always-on bonus was enough to flip decisive, already-
# correct cross-channel comparisons (semantic_search losing to metadata_search's
# smarter _fetch_doc_chunks fallback in live_runtime.py) -- confirmed via 10x
# multi-trial testing as a severe regression on 4 previously-solid questions
# (pit_rate/pit_rate_en/profit_rate_en/vat_rate_more all dropped from ~100% to
# 0-20% pass rate). See infohub-rag-generation-fidelity memory for the full
# postmortem.
#
# Fix: these signals now ONLY reorder candidates that are already direct
# same-document `semantic_search` competitors, as a pass AFTER the main score
# and sort. A candidate can never leapfrog one outside its own group -- the
# set of ranked-list slots a group occupies is fixed by the baseline score
# first, and only the order WITHIN those slots is decided by chunk content.
_GEORGIAN_TOKEN_RE = re.compile(r"[Ⴀ-ჿ]{4,}")
_GEORGIAN_STOPWORDS = {
    "და", "არის", "იყო", "თუ", "ან", "ეს", "ის", "რომ", "უნდა", "შეიძლება",
    "იმ", "მისი", "მას", "მათ", "მისთვის", "მისგან", "შესახებ", "მიხედვით",
    "საფუძველზე", "წლის", "წელს", "პირის", "შემთხვევაში", "საქართველოს",
    "კოდექსის", "მუხლის", "გათვალისწინებული", "წესით", "შესაბამისად",
}
_REPEALED_MARKERS = ("ამოღებულია", "ძალადაკარგულია", "ძალაშია")
_DEFINITION_QUERY_MARKERS = (
    "что такое", "что представляет собой", "что значит", "что понимается",
    "what is", "what does", "definition of",
    "რა არის", "რას ნიშნავს", "რას წარმოადგენს",
)


def _georgian_tokens(text: str) -> set:
    tokens = _GEORGIAN_TOKEN_RE.findall(text or "")
    return {t for t in tokens if t not in _GEORGIAN_STOPWORDS}


def _is_definitional_first_point(parsed: ParsedQuery, chunk_content: str) -> bool:
    query_text = ((parsed.raw_query or "") + " " + (parsed.normalized_query or "")).lower()
    if not any(marker in query_text for marker in _DEFINITION_QUERY_MARKERS):
        return False
    match = re.match(r"^\s*(\d+)\.", chunk_content or "")
    return bool(match and match.group(1) == "1")


def _tie_break_score(parsed: ParsedQuery, chunk_content: str, query_text_ka: str, term_doc_freq: Dict[str, int], n_group: int) -> float:
    """Chunk-content relevance, scored ONLY relative to a document's own competing
    chunks (term_doc_freq/n_group cover just that group, not the whole candidate
    pool) -- local IDF so generic tax vocabulary shared by most of the group's
    chunks doesn't drown out the few genuinely distinguishing terms.
    """
    query_tokens = _georgian_tokens(query_text_ka)
    chunk_tokens = _georgian_tokens(chunk_content)
    overlap = 0.0
    if query_tokens and chunk_tokens:
        shared = query_tokens & chunk_tokens

        def idf(term: str) -> float:
            df = term_doc_freq.get(term, 1)
            return math.log((n_group + 1) / (df + 1))

        denom = sum(idf(t) for t in query_tokens)
        if denom > 0:
            overlap = sum(idf(t) for t in shared) / denom

    repealed = -0.5 if any(marker in (chunk_content or "")[:80] for marker in _REPEALED_MARKERS) else 0.0
    definitional = 0.3 if _is_definitional_first_point(parsed, chunk_content) else 0.0
    return overlap + repealed + definitional


def _tie_break_same_document_chunks(parsed: ParsedQuery, ranked: List[Dict[str, Any]]) -> None:
    """Reorders same-document semantic_search competitors in place, within the
    exact list slots they already occupy after the baseline score+sort -- never
    lets a group member move past a candidate outside the group.
    """
    groups: Dict[str, List[int]] = {}
    for idx, item in enumerate(ranked):
        if item.get("channel") != "semantic_search" or not item.get("document_id"):
            continue
        groups.setdefault(item["document_id"], []).append(idx)

    for indices in groups.values():
        if len(indices) < 2:
            continue
        members = [ranked[i] for i in indices]

        term_doc_freq: Dict[str, int] = {}
        for member in members:
            content = (member.get("metadata") or {}).get("chunk_content", "")
            for token in _georgian_tokens(content):
                term_doc_freq[token] = term_doc_freq.get(token, 0) + 1
        n_group = len(members)

        def sort_key(item: Dict[str, Any]) -> float:
            metadata = item.get("metadata") or {}
            return _tie_break_score(
                parsed,
                metadata.get("chunk_content", ""),
                metadata.get("query_text_ka", ""),
                term_doc_freq,
                n_group,
            )

        members_sorted = sorted(members, key=sort_key, reverse=True)
        for slot_idx, member in zip(indices, members_sorted):
            member["tie_break_reordered"] = True
            ranked[slot_idx] = member


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
    _tie_break_same_document_chunks(parsed, ranked)

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
