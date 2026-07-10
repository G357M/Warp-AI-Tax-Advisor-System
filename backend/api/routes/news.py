"""
Public news feed: infohub.rs.ge publications broken into subcategories.

Scope is deliberately species-based, not ``document_type='news'`` only:
``infer_document_type`` reclassifies many LegislativeNews items into
guideline/law/regulation for RAG-lane purposes, but they still belong on the
public news feed. Subcategories live in ``documents.subtype`` (rule-based at
ingest + LLM backfill, see scripts/classify_news_subtypes.py); unclassified
rows read as 'general'.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.database import get_db
from scraper.normalize import NEWS_SUBTYPES

router = APIRouter(prefix="/news", tags=["News"])

NEWS_SCOPE_SQL = "((metadata->>'species') = 'LegislativeNews' OR document_type = 'news')"


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

    clauses, params = [NEWS_SCOPE_SQL], {}
    if search:
        clauses.append("title ILIKE :search")
        params["search"] = f"%{search.strip()}%"
    scope_where = " AND ".join(clauses)

    # Per-subtype counts respect the search but ignore the subtype filter so
    # the category chips stay populated while one of them is active.
    counts = dict(db.execute(text(f"""
        SELECT coalesce(subtype, 'general'), count(*)
        FROM documents WHERE {scope_where}
        GROUP BY 1
    """), params).all())
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
