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

    if parsed.topic in CANONICAL_RATE_ARTICLES and parsed.goal == "rate_lookup":
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
        if rows:
            candidates = [
                _candidate_from_row(row, parsed, "db canonical tax code rate lookup", 0.99)
                for row in rows
            ]
            article_ref = CANONICAL_RATE_ARTICLES[parsed.topic]
            for item in candidates:
                item.metadata = {
                    **(item.metadata or {}),
                    "article_ref": article_ref,
                    "section_label": f"მუხლი {article_ref}",
                }
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
