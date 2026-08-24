from __future__ import annotations

import re
from typing import Dict, List, Optional

from .models import ParsedQuery, CandidateDocument
from .metadata_search import search_metadata
from .db_utils import db_available, run_query
from .faq_tax_matrix import CANONICAL_RATE_ARTICLES, CANONICAL_TAX_CODE_SOURCE_URL


METADATA_SEARCH_BASE_SQL = """
SELECT id::text AS document_id, title, document_type, source_url
FROM documents
{where_clause}
ORDER BY updated_at DESC NULLS LAST
LIMIT %s
"""

LOCALITY_TITLE_STEMS: Dict[str, List[str]] = {
    "dmanisi": ["დმანის"],
    "tbilisi": ["თბილის"],
    "gurjaani": ["გურჯაან"],
}

TOPIC_TITLE_STEMS: Dict[str, List[str]] = {
    "property_tax": ["ქონების", "ადგილობრივი"],
    "vat": ["დღგ", "დამატებული ღირებულების", "საგადასახადო კოდექს"],
    "tax": ["საგადასახადო კოდექს"],
    "excise": ["აქციზ"],
    "customs": ["საბაჟო"],
}

AMENDMENT_TITLE_STEMS = ["საგადასახადო კოდექსში ცვლილების შეტანის შესახებ", "ცვლილების შეტანის შესახებ"]
CANONICAL_TAX_CODE_TITLE_STEMS = ["საგადასახადო კოდექსი"]

# Registration-threshold questions point at the registration article, not the
# rate article (vat -> 166 is the 18% rate; the 100k threshold lives in 165).
# A pointer, not a curated answer: the text still comes from the law chunk.
CANONICAL_THRESHOLD_ARTICLES: Dict[str, str] = {"vat": "165"}
CANONICAL_GOAL_ARTICLES: Dict[str, str] = {
    "residency_status": "34",
    "penalty_rate": "272",
    "exemption_status": "172",
}
THRESHOLD_QUERY_TOKENS = (
    "регистр", "оборот", "порог", "registr", "threshold", "turnover", "რეგისტრ", "ბრუნვ",
)

# Canonical pointers for the former guard topics (П3): unambiguous query
# tokens -> the article that answers the question. title_stem=None means the
# Tax Code; the funded pension rests on its own law (base act, amendment acts
# excluded by the NOT ILIKE in the lookup). Article targets verified against
# the live texts 2026-07-11: 97 distributed-profit object, 172 VAT exemption
# with credit (tour operators), 202 property tax rates, pension law art. 3
# (the 2% contributions).
GUARD_TOPIC_POINTERS = [
    (("эстонск", "estonian", "ესტონ"), None, "97"),
    (("туропер", "tour oper", "ტუროპერ"), None, "172"),
    (("налог на имущество", "имуществ", "property tax", "ქონების გადასახად"), None, "202"),
    (("пенси", "pension", "საპენსიო", "პენსი"), "დაგროვებითი პენსიის შესახებ", "3"),
]

CANONICAL_LAW_BY_TITLE_SQL = """
SELECT id::text AS document_id, title, document_type, source_url
FROM documents
WHERE document_type ILIKE %s AND title ILIKE %s AND title NOT ILIKE %s
ORDER BY updated_at DESC NULLS LAST
LIMIT %s
"""


def _extract_year(raw_query: str) -> Optional[str]:
    match = re.search(r"\b(20\d{2})\b", raw_query or "")
    return match.group(1) if match else None


def _candidate_from_row(row: dict, parsed: ParsedQuery, why: str, score: float) -> CandidateDocument:
    locality_stems = LOCALITY_TITLE_STEMS.get(parsed.locality or "", [])
    title = row.get("title") or ""
    matched_localities = [parsed.locality] if parsed.locality and any(stem in title for stem in locality_stems) else []
    metadata = {
        "topics": [parsed.topic] if parsed.topic else [],
        "subjects": [parsed.subject] if parsed.subject else [],
        "goals": [parsed.goal] if parsed.goal else [],
        "localities": matched_localities,
        "authority_rank": 0.9 if row.get("document_type") == "regulation" else 0.75,
        "is_current": True,
    }
    return CandidateDocument(
        channel="metadata_search",
        document_id=row.get("document_id"),
        title=row.get("title") or "",
        document_type=row.get("document_type"),
        source_url=row.get("source_url"),
        channel_score=score,
        why=why,
        metadata=metadata,
    )


def search_metadata_from_backend(parsed: ParsedQuery, limit: int = 5) -> List[CandidateDocument]:
    if not db_available():
        return search_metadata(parsed, limit=limit)

    if parsed.locality and parsed.topic == "property_tax":
        locality_stems = LOCALITY_TITLE_STEMS.get(parsed.locality, [])
        topic_stems = TOPIC_TITLE_STEMS.get(parsed.topic, [])
        if not locality_stems:
            return []
        clauses = ["document_type ILIKE %s"]
        params: List[object] = ["%regulation%"]

        if locality_stems:
            clauses.append("(" + " OR ".join(["title ILIKE %s" for _ in locality_stems]) + ")")
            params.extend([f"%{stem}%" for stem in locality_stems])
        if topic_stems:
            clauses.append("(" + " OR ".join(["title ILIKE %s" for _ in topic_stems]) + ")")
            params.extend([f"%{stem}%" for stem in topic_stems])

        sql = METADATA_SEARCH_BASE_SQL.format(where_clause=f"WHERE {' AND '.join(clauses)}")
        rows = run_query(sql, [*params, limit])
        if rows:
            return [
                _candidate_from_row(row, parsed, "db local regulation lookup match", 0.96)
                for row in rows
            ]
        return []

    def _canonical_tax_code_candidates(article_ref: str, why: str) -> List[CandidateDocument]:
        clauses = [
            "document_type ILIKE %s",
            "(source_url = %s OR TRIM(BOTH '.' FROM title) = %s)",
        ]
        params = [
            "%law%",
            CANONICAL_TAX_CODE_SOURCE_URL,
            "საქართველოს საგადასახადო კოდექსი",
        ]
        sql = METADATA_SEARCH_BASE_SQL.format(where_clause=f"WHERE {' AND '.join(clauses)}")
        rows = run_query(sql, [*params, limit])
        candidates = [_candidate_from_row(row, parsed, why, 0.99) for row in rows or []]
        for item in candidates:
            item.metadata = {
                **(item.metadata or {}),
                "article_ref": article_ref,
                "section_label": f"მუხლი {article_ref}",
            }
        return candidates

    # Threshold/registration questions win over the rate mapping: they share
    # the topic (vat) but need the registration article, not the rate one.
    normalized = str(getattr(parsed, "normalized_query", "") or "").lower()
    if parsed.topic in CANONICAL_THRESHOLD_ARTICLES and any(t in normalized for t in THRESHOLD_QUERY_TOKENS):
        candidates = _canonical_tax_code_candidates(
            CANONICAL_THRESHOLD_ARTICLES[parsed.topic], "db canonical tax code threshold lookup"
        )
        if candidates:
            return candidates

    if parsed.goal in CANONICAL_GOAL_ARTICLES:
        candidates = _canonical_tax_code_candidates(
            CANONICAL_GOAL_ARTICLES[parsed.goal],
            "db canonical practical-tax article lookup",
        )
        if candidates:
            return candidates

    # A generic appeal question needs the statutory procedure, not a sample
    # dispute outcome. Article 299 is the canonical entry point (30-day term,
    # electronic filing and effect of the appeal); live runtime supplements it
    # with article 297 for the two-stage Revenue Service / Dispute Council path.
    if parsed.goal == "appeal_procedure":
        candidates = _canonical_tax_code_candidates(
            "299", "db canonical tax appeal procedure lookup"
        )
        if candidates:
            return candidates

    # Article 88 answers who may receive small-business status. Article 90
    # supplies the 1% rate, but eligibility is the controlling rule for an LLC.
    if parsed.goal == "small_business_eligibility":
        candidates = _canonical_tax_code_candidates(
            "88", "db canonical small-business eligibility lookup"
        )
        if candidates:
            return candidates

    # Former guard topics: token-matched pointer to the answering article.
    for tokens, title_stem, article_ref in GUARD_TOPIC_POINTERS:
        if not any(t in normalized for t in tokens):
            continue
        if title_stem is None:
            candidates = _canonical_tax_code_candidates(
                article_ref, "db canonical guard-topic article lookup"
            )
        else:
            rows = run_query(
                CANONICAL_LAW_BY_TITLE_SQL,
                ["%law%", f"%{title_stem}%", "%ცვლილებ%", limit],
            )
            candidates = [
                _candidate_from_row(row, parsed, "db canonical law-by-title article lookup", 0.99)
                for row in rows or []
            ]
            for item in candidates:
                item.metadata = {
                    **(item.metadata or {}),
                    "article_ref": article_ref,
                    "section_label": f"მუხლი {article_ref}",
                }
        if candidates:
            return candidates
        break

    if parsed.topic in CANONICAL_RATE_ARTICLES and parsed.goal == "rate_lookup":
        candidates = _canonical_tax_code_candidates(
            CANONICAL_RATE_ARTICLES[parsed.topic], "db canonical tax code rate lookup"
        )
        if candidates:
            return candidates

    if parsed.goal == "amendment_tracking":
        year = _extract_year(parsed.raw_query)
        title_stems = AMENDMENT_TITLE_STEMS
        clauses = ["document_type ILIKE %s", "title ILIKE %s"]
        params: List[object] = ["%law%", "%საგადასახადო კოდექს%"]
        clauses.append("(" + " OR ".join(["title ILIKE %s" for _ in title_stems]) + ")")
        params.extend([f"%{stem}%" for stem in title_stems])
        if year:
            clauses.append("title ILIKE %s")
            params.append(f"%{year}%")

        sql = METADATA_SEARCH_BASE_SQL.format(where_clause=f"WHERE {' AND '.join(clauses)}")
        rows = run_query(sql, [*params, limit])
        if rows:
            score = 0.95 if year else 0.9
            return [
                _candidate_from_row(row, parsed, "db amendment lookup match", score)
                for row in rows
            ]

    title_probe = f"%{parsed.topic.replace('_', ' ')}%" if parsed.topic else None
    doc_type_probe = None
    if parsed.goal == "dispute_outcome":
        doc_type_probe = "%court%"
    elif parsed.goal == "document_summary":
        doc_type_probe = "%guideline%"
    elif parsed.article_ref or parsed.point_ref:
        doc_type_probe = "%law%"

    clauses = []
    params = []
    if title_probe:
        clauses.append("title ILIKE %s")
        params.append(title_probe)
    if doc_type_probe:
        clauses.append("document_type ILIKE %s")
        params.append(doc_type_probe)

    if not clauses:
        return search_metadata(parsed, limit=limit)

    sql = METADATA_SEARCH_BASE_SQL.format(where_clause=f"WHERE ({' OR '.join(clauses)})")
    params.append(limit)

    rows = run_query(sql, params)
    if not rows:
        return search_metadata(parsed, limit=limit)

    return [
        _candidate_from_row(row, parsed, "db metadata lookup match", 0.75)
        for row in rows
    ]
