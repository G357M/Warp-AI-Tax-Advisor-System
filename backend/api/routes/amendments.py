"""
Public law-change tracking API over law_amendments.

Powers the /laws timeline: which amendment was adopted, when it entered into
force, which articles it touched and what the norm looked like before/after.
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.database import get_db

router = APIRouter(prefix="/amendments", tags=["Amendments"])


@router.get("/laws")
def amended_laws(db: Session = Depends(get_db)):
    """Laws in the corpus that have tracked amendments."""
    rows = db.execute(text("""
        SELECT a.target_law_doc_id::text AS law_id,
               COALESCE(TRIM(BOTH ' .' FROM d.title), a.target_law_title) AS title,
               count(*) AS amendments,
               max(a.adoption_date) AS last_adoption
        FROM law_amendments a
        LEFT JOIN documents d ON d.id = a.target_law_doc_id
        WHERE a.target_law_doc_id IS NOT NULL
        GROUP BY 1, 2
        ORDER BY 3 DESC
    """)).all()
    unresolved = db.execute(text(
        "SELECT count(*) FROM law_amendments WHERE target_law_doc_id IS NULL"
    )).scalar()
    return {
        "laws": [
            {
                "law_id": r.law_id,
                "title": r.title,
                "amendments": r.amendments,
                "last_adoption": r.last_adoption.isoformat() if r.last_adoption else None,
            }
            for r in rows
        ],
        "unresolved_amendments": unresolved,
    }


@router.get("/timeline")
def amendment_timeline(
    law_id: UUID,
    article: Optional[str] = Query(default=None, max_length=10),
    lang: str = Query(default="ru", pattern="^(ru|ka|en)$"),
    db: Session = Depends(get_db),
):
    """Chronology of amendments for one law (optionally filtered by article)."""
    law = db.execute(text(
        "SELECT TRIM(BOTH ' .' FROM title) AS title FROM documents WHERE id = :law_id"
    ), {"law_id": str(law_id)}).first()
    if not law:
        raise HTTPException(status_code=404, detail="Law not found")

    rows = db.execute(text("""
        SELECT a.id::text, a.adoption_date, a.effective_date, a.status,
               a.affected_articles, d.title AS act_title, d.document_number,
               d.source_url, a.articles_i18n
        FROM law_amendments a
        JOIN documents d ON d.id = a.amendment_doc_id
        WHERE a.target_law_doc_id = :law_id
        ORDER BY a.adoption_date DESC NULLS LAST
    """), {"law_id": str(law_id)}).all()

    items = []
    for r in rows:
        articles = r.affected_articles or []
        if article:
            if not any(str(a.get("article")) == article for a in articles):
                continue
        if lang != "ru" and r.articles_i18n:
            translated = (r.articles_i18n or {}).get(lang)
            if isinstance(translated, list) and len(translated) == len(articles):
                articles = [
                    {
                        **a,
                        "summary_ru": t.get("summary") or a.get("summary_ru"),
                        "old_norm": t.get("old_norm") if t.get("old_norm") is not None else a.get("old_norm"),
                        "new_norm": t.get("new_norm") if t.get("new_norm") is not None else a.get("new_norm"),
                    }
                    for a, t in zip(articles, translated)
                ]
        items.append({
            "id": r[0],
            "adoption_date": r.adoption_date.isoformat() if r.adoption_date else None,
            "effective_date": r.effective_date.isoformat() if r.effective_date else None,
            "status": r.status,
            "articles": articles,
            "act_title": r.act_title,
            "document_number": r.document_number,
            "source_url": r.source_url,
        })
    return {"law_id": str(law_id), "law_title": law.title, "article": article, "timeline": items}
