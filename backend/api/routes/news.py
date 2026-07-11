"""
Public news feed: infohub.rs.ge publications broken into subcategories.

Scope is deliberately species-based, not ``document_type='news'`` only:
``infer_document_type`` reclassifies many LegislativeNews items into
guideline/law/regulation for RAG-lane purposes, but they still belong on the
public news feed. Subcategories live in ``documents.subtype`` (rule-based at
ingest + LLM backfill, see scripts/classify_news_subtypes.py); unclassified
rows read as 'general'.
"""
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.database import get_db
from scraper.normalize import NEWS_SUBTYPES

router = APIRouter(prefix="/news", tags=["News"])

NEWS_SCOPE_SQL = "((metadata->>'species') = 'LegislativeNews' OR document_type = 'news')"

_GEORGIAN_RE = re.compile(r"[Ⴀ-ჿ]")
_pg_trgm_available: Optional[bool] = None


def _has_pg_trgm(db: Session) -> bool:
    global _pg_trgm_available
    if _pg_trgm_available is None:
        try:
            _pg_trgm_available = bool(db.execute(text(
                "SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'"
            )).scalar())
        except Exception:
            _pg_trgm_available = False
    return _pg_trgm_available


def _build_search_clauses(db: Session, search: str, params: dict) -> tuple:
    """Cross-lingual title/number search (П5). Returns (exact, fuzzy_or_None).

    The corpus titles are Georgian; a RU/EN query is translated once
    (Redis-cached, deterministic — see rag/llm.py) and both forms are matched
    by substring. The fuzzy word_similarity clause is a RESCUE used only when
    the exact clause finds nothing — always OR-ing it in dilutes good queries
    (common stems like დაბეგვრ appear in hundreds of titles).
    """
    query = search.strip()
    params["search"] = f"%{query}%"
    exact = ["title ILIKE :search", "document_number ILIKE :search"]

    query_ka = None
    if not _GEORGIAN_RE.search(query):
        try:
            from rag.llm import llm_client
            translated = llm_client.translate_to_georgian(query)
            if translated and translated.strip() and translated.strip() != query:
                query_ka = translated.strip()
        except Exception:
            query_ka = None
    if query_ka:
        # Match every word of the translation (crudely stemmed: drop the last
        # letter of longer words so დაბეგვრა also hits დაბეგვრის), not the
        # whole phrase as one substring — a lossy translation of a keyword
        # query ('double taxation' -> 'დაბეგვრა') would otherwise match half
        # the corpus. Longest 3 words carry the meaning; if AND turns out too
        # strict the zero-results fuzzy rescue below still fires.
        words = sorted(re.split(r"\s+", query_ka), key=len, reverse=True)
        stems = [w[:-1] if len(w) >= 5 else w for w in words if len(w) >= 3][:3]
        if stems:
            ka_parts = []
            for i, stem in enumerate(stems):
                params[f"ka_w{i}"] = f"%{stem}%"
                ka_parts.append(f"title ILIKE :ka_w{i}")
            exact.append("(" + " AND ".join(ka_parts) + ")")

    fuzzy = None
    if _has_pg_trgm(db):
        params["sim_probe"] = query_ka or query
        fuzzy = "word_similarity(:sim_probe, title) > 0.5"

    return "(" + " OR ".join(exact) + ")", fuzzy


@router.get("")
def list_news(
    subtype: Optional[str] = Query(default=None, max_length=50),
    search: Optional[str] = Query(default=None, max_length=200),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """News items, optionally filtered by subcategory and title search."""
    if subtype and subtype not in NEWS_SUBTYPES:
        raise HTTPException(status_code=400, detail=f"Unknown subtype: {subtype}")

    def subtype_counts(where_sql: str, where_params: dict) -> dict:
        # Per-subtype counts respect the search but ignore the subtype filter
        # so the category chips stay populated while one of them is active.
        return dict(db.execute(text(f"""
            SELECT coalesce(subtype, 'general'), count(*)
            FROM documents WHERE {where_sql}
            GROUP BY 1
        """), where_params).all())

    clauses, params = [NEWS_SCOPE_SQL], {}
    fuzzy_clause = None
    if search:
        exact_clause, fuzzy_clause = _build_search_clauses(db, search, params)
        clauses.append(exact_clause)
    scope_where = " AND ".join(clauses)

    counts = subtype_counts(scope_where, params)
    total = sum(counts.values())

    # Fuzzy rescue: exact/substring search found nothing — retry with
    # trigram word similarity (typos, Georgian word-form endings).
    if search and total == 0 and fuzzy_clause:
        scope_where = " AND ".join([NEWS_SCOPE_SQL, f"({fuzzy_clause})"])
        counts = subtype_counts(scope_where, params)
        total = sum(counts.values())

    where = scope_where
    if subtype:
        where += " AND coalesce(subtype, 'general') = :subtype"
        params["subtype"] = subtype

    rows = db.execute(text(f"""
        SELECT id::text, title, coalesce(subtype, 'general') AS subtype,
               document_number, date_published, source_url
        FROM documents WHERE {where}
        ORDER BY date_published DESC NULLS LAST, created_at DESC
        LIMIT :limit OFFSET :offset
    """), {**params, "limit": limit, "offset": offset}).all()

    filtered_total = counts.get(subtype, 0) if subtype else total
    return {
        "total": filtered_total,
        "counts": {s: counts.get(s, 0) for s in sorted(NEWS_SUBTYPES)},
        "items": [
            {
                "id": r.id,
                "title": r.title,
                "subtype": r.subtype,
                "document_number": r.document_number,
                "date_published": r.date_published.isoformat() if r.date_published else None,
                "source_url": r.source_url,
            }
            for r in rows
        ],
    }
