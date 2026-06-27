from __future__ import annotations

from typing import List

from .models import ParsedQuery, CandidateDocument
from .citation_resolver import resolve_citations
from .exact_doc_resolver import resolve_exact_documents
from .article_resolver import resolve_article
from .point_resolver import resolve_point
from .db_utils import db_available, run_query


EXACT_BY_DOC_NUMBER_SQL = """
SELECT id::text AS document_id, title, document_type, source_url, document_number
FROM documents
WHERE document_number = %s
ORDER BY updated_at DESC NULLS LAST
LIMIT 10
"""

EXACT_BY_SOURCE_OR_TITLE_SQL = """
SELECT id::text AS document_id, title, document_type, source_url, document_number
FROM documents
WHERE source_url ILIKE %s OR title ILIKE %s
ORDER BY updated_at DESC NULLS LAST
LIMIT 10
"""


def _rows_to_candidates(rows, channel: str, why_prefix: str, score: float) -> List[CandidateDocument]:
    return [
        CandidateDocument(
            channel=channel,
            document_id=row.get("document_id"),
            title=row.get("title") or "",
            document_type=row.get("document_type"),
            source_url=row.get("source_url"),
            channel_score=score,
            why=f"{why_prefix}: {row.get('document_number') or row.get('title')}",
            metadata={
                "document_number": row.get("document_number"),
            },
        )
        for row in rows
    ]


def resolve_exact_from_backend(parsed: ParsedQuery) -> List[CandidateDocument]:
    if not db_available():
        return resolve_exact_documents(parsed)

    if parsed.document_ref:
        rows = run_query(EXACT_BY_DOC_NUMBER_SQL, [parsed.document_ref])
        if rows:
            return _rows_to_candidates(rows, "exact_doc_resolver", "db exact document_number match", 0.995)

    rows = run_query(
        EXACT_BY_SOURCE_OR_TITLE_SQL,
        [f"%{parsed.normalized_query}%", f"%{parsed.normalized_query}%"],
    )
    if rows:
        return _rows_to_candidates(rows, "exact_doc_resolver", "db exact title/source match", 0.94)

    return resolve_exact_documents(parsed)


def resolve_citation_from_backend(parsed: ParsedQuery) -> List[CandidateDocument]:
    if not db_available():
        return resolve_citations(parsed)

    if parsed.document_ref:
        rows = run_query(EXACT_BY_DOC_NUMBER_SQL, [parsed.document_ref])
        if rows:
            return _rows_to_candidates(rows, "citation_resolver", "db citation document_number match", 0.99)

    return resolve_citations(parsed)


def resolve_article_from_backend(parsed: ParsedQuery) -> List[CandidateDocument]:
    return resolve_article(parsed)


def resolve_point_from_backend(parsed: ParsedQuery) -> List[CandidateDocument]:
    return resolve_point(parsed)
