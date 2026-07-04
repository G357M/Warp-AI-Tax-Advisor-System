"""
Public analytics over extracted dispute-decision facts (decision_facts).

Aggregates help a client judge dispute strategy: how complaints are resolved
overall, per deciding body, per year, and per contested Tax Code article.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.database import get_db

router = APIRouter(prefix="/analytics", tags=["Analytics"])

OUTCOME_COLUMNS = """
    count(*) AS total,
    count(*) FILTER (WHERE outcome = 'satisfied') AS satisfied,
    count(*) FILTER (WHERE outcome = 'partially_satisfied') AS partially_satisfied,
    count(*) FILTER (WHERE outcome = 'rejected') AS rejected,
    count(*) FILTER (WHERE outcome = 'unclear') AS unclear
"""


def _outcome_row(row) -> dict:
    total = row.total or 0
    favorable = (row.satisfied or 0) + (row.partially_satisfied or 0)
    return {
        "total": total,
        "satisfied": row.satisfied or 0,
        "partially_satisfied": row.partially_satisfied or 0,
        "rejected": row.rejected or 0,
        "unclear": row.unclear or 0,
        # any relief for the taxpayer (full or partial satisfaction)
        "taxpayer_relief_rate": round(favorable / total, 3) if total else None,
    }


@router.get("/decisions")
def decision_statistics(
    article: Optional[str] = Query(default=None, max_length=10, description="Tax Code article number, e.g. 275"),
    db: Session = Depends(get_db),
):
    """Aggregated outcomes of tax/customs dispute decisions in the corpus."""
    params = {}
    article_join = ""
    where = "WHERE 1=1"
    if article:
        article_clause = "AND f.contested_articles::jsonb ? :article"
        params["article"] = article.strip()
    else:
        article_clause = ""

    overall = db.execute(text(f"""
        SELECT {OUTCOME_COLUMNS} FROM decision_facts f {where} {article_clause}
    """), params).one()

    by_year = db.execute(text(f"""
        SELECT extract(year FROM f.decision_date)::int AS year, {OUTCOME_COLUMNS}
        FROM decision_facts f {where} {article_clause} AND f.decision_date IS NOT NULL
        GROUP BY 1 ORDER BY 1
    """), params).all()

    by_body = db.execute(text(f"""
        SELECT f.authority_body AS body, {OUTCOME_COLUMNS}
        FROM decision_facts f {where} {article_clause}
        GROUP BY 1 ORDER BY 2 DESC
    """), params).all()

    by_dispute_type = db.execute(text(f"""
        SELECT f.dispute_type, {OUTCOME_COLUMNS}
        FROM decision_facts f {where} {article_clause}
        GROUP BY 1 ORDER BY 2 DESC
    """), params).all()

    top_articles = []
    if not article:
        top_articles = db.execute(text(f"""
            SELECT a.value AS article, {OUTCOME_COLUMNS}
            FROM decision_facts f, jsonb_array_elements_text(f.contested_articles::jsonb) AS a(value)
            GROUP BY 1 HAVING count(*) >= 5 ORDER BY 2 DESC LIMIT 20
        """)).all()

    coverage = db.execute(text("""
        SELECT
            (SELECT count(*) FROM documents WHERE document_type = 'court_decision'
               AND (metadata->>'kind') IS DISTINCT FROM 'digest') AS decisions_in_corpus,
            (SELECT count(*) FROM decision_facts) AS decisions_extracted,
            (SELECT count(*) FROM documents) AS documents_total
    """)).one()

    return {
        "article": article,
        "coverage": {
            "decisions_in_corpus": coverage.decisions_in_corpus,
            "decisions_extracted": coverage.decisions_extracted,
            "documents_total": coverage.documents_total,
        },
        "overall": _outcome_row(overall),
        "by_year": [{"year": r.year, **_outcome_row(r)} for r in by_year],
        "by_body": [{"body": r.body, **_outcome_row(r)} for r in by_body],
        "by_dispute_type": [{"dispute_type": r.dispute_type, **_outcome_row(r)} for r in by_dispute_type],
        "top_articles": [{"article": r.article, **_outcome_row(r)} for r in top_articles],
    }
