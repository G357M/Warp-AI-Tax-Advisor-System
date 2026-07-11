"""
Public analytics over extracted dispute-decision facts (decision_facts).

Aggregates help a client judge dispute strategy: how complaints are resolved
overall, per deciding body, per year, and per contested Tax Code article.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.database import get_db

router = APIRouter(prefix="/analytics", tags=["Analytics"])

AUTHORITY_BODIES = {"revenue_service_council", "mof_dispute_council", "city_court", "appeals_court", "supreme_court", "other"}
DISPUTE_TYPES = {"tax", "customs", "both", "other"}
OUTCOMES = {"satisfied", "partially_satisfied", "rejected", "unclear"}

# Fixed GEL buckets for the disputed-amount histogram.
AMOUNT_BUCKETS = [
    ("<1k", 0, 1_000),
    ("1k-10k", 1_000, 10_000),
    ("10k-100k", 10_000, 100_000),
    ("100k-1M", 100_000, 1_000_000),
    (">1M", 1_000_000, None),
]


def _decision_filters(
    article: Optional[str],
    body: Optional[str],
    outcome: Optional[str],
    year: Optional[int],
    dispute_type: Optional[str],
    has_amount: Optional[bool],
) -> tuple:
    """Shared WHERE clauses over decision_facts f for the drill-down filters."""
    if body and body not in AUTHORITY_BODIES:
        raise HTTPException(status_code=400, detail=f"Unknown body: {body}")
    if outcome and outcome not in OUTCOMES:
        raise HTTPException(status_code=400, detail=f"Unknown outcome: {outcome}")
    if dispute_type and dispute_type not in DISPUTE_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown dispute_type: {dispute_type}")

    # 'other' bodies are reference material (CJEU translations, municipal
    # resolutions), not Georgian dispute instances — excluded from public
    # stats unless explicitly requested via body=other.
    clauses, params = ["1=1"], {}
    if body:
        clauses.append("f.authority_body = :body")
        params["body"] = body
    else:
        clauses.append("f.authority_body IS DISTINCT FROM 'other'")
    if article:
        clauses.append("f.contested_articles::jsonb ? :article")
        params["article"] = article.strip()
    if outcome:
        clauses.append("f.outcome = :outcome")
        params["outcome"] = outcome
    if year:
        clauses.append("extract(year FROM f.decision_date)::int = :year")
        params["year"] = year
    if dispute_type:
        clauses.append("f.dispute_type = :dispute_type")
        params["dispute_type"] = dispute_type
    if has_amount:
        clauses.append("f.amount_gel IS NOT NULL")
    return " AND ".join(clauses), params

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


@router.get("/decisions/list")
def decision_list(
    article: Optional[str] = Query(default=None, max_length=10),
    body: Optional[str] = Query(default=None, max_length=40),
    outcome: Optional[str] = Query(default=None, max_length=30),
    year: Optional[int] = Query(default=None, ge=1990, le=2100),
    dispute_type: Optional[str] = Query(default=None, max_length=20),
    has_amount: Optional[bool] = Query(default=None),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """Individual dispute decisions behind any aggregate (drill-down list)."""
    where, params = _decision_filters(article, body, outcome, year, dispute_type, has_amount)

    total = db.execute(text(f"SELECT count(*) FROM decision_facts f WHERE {where}"), params).scalar()
    rows = db.execute(text(f"""
        SELECT f.id::text AS facts_id, f.document_id::text, d.title,
               f.decision_number, f.decision_date, f.authority_body, f.dispute_type,
               f.contested_articles, f.amount_gel, f.outcome, f.in_favor, d.source_url
        FROM decision_facts f
        JOIN documents d ON d.id = f.document_id
        WHERE {where}
        ORDER BY f.decision_date DESC NULLS LAST, d.created_at DESC
        LIMIT :limit OFFSET :offset
    """), {**params, "limit": limit, "offset": offset}).all()

    return {
        "total": total,
        "items": [
            {
                "facts_id": r.facts_id,
                "document_id": r.document_id,
                "title": r.title,
                "decision_number": r.decision_number,
                "decision_date": r.decision_date.isoformat() if r.decision_date else None,
                "authority_body": r.authority_body,
                "dispute_type": r.dispute_type,
                "contested_articles": r.contested_articles or [],
                "amount_gel": r.amount_gel,
                "outcome": r.outcome,
                "in_favor": r.in_favor,
                "source_url": r.source_url,
            }
            for r in rows
        ],
    }


@router.get("/decisions/amounts")
def decision_amounts(
    article: Optional[str] = Query(default=None, max_length=10),
    body: Optional[str] = Query(default=None, max_length=40),
    year: Optional[int] = Query(default=None, ge=1990, le=2100),
    db: Session = Depends(get_db),
):
    """Disputed-amount statistics (amount_gel is stated in a minority of decisions —
    every figure ships with its n and coverage share)."""
    where, params = _decision_filters(article, body, None, year, None, None)

    coverage = db.execute(text(f"""
        SELECT count(*) AS total, count(f.amount_gel) AS with_amount
        FROM decision_facts f WHERE {where}
    """), params).one()

    amount_where = f"{where} AND f.amount_gel IS NOT NULL"
    overall = db.execute(text(f"""
        SELECT sum(f.amount_gel) AS sum, avg(f.amount_gel) AS avg,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY f.amount_gel) AS median,
               percentile_cont(0.9) WITHIN GROUP (ORDER BY f.amount_gel) AS p90
        FROM decision_facts f WHERE {amount_where}
    """), params).one()

    by_year = db.execute(text(f"""
        SELECT extract(year FROM f.decision_date)::int AS year, count(*) AS n,
               sum(f.amount_gel) AS sum, avg(f.amount_gel) AS avg,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY f.amount_gel) AS median
        FROM decision_facts f WHERE {amount_where} AND f.decision_date IS NOT NULL
        GROUP BY 1 ORDER BY 1
    """), params).all()

    by_body = db.execute(text(f"""
        SELECT f.authority_body AS body, count(*) AS n,
               sum(f.amount_gel) AS sum, avg(f.amount_gel) AS avg,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY f.amount_gel) AS median
        FROM decision_facts f WHERE {amount_where}
        GROUP BY 1 ORDER BY 2 DESC
    """), params).all()

    bucket_case = " ".join(
        f"WHEN f.amount_gel >= {lo} AND f.amount_gel < {hi} THEN '{label}'"
        if hi is not None else f"WHEN f.amount_gel >= {lo} THEN '{label}'"
        for label, lo, hi in AMOUNT_BUCKETS
    )
    bucket_counts = dict(db.execute(text(f"""
        SELECT CASE {bucket_case} END AS bucket, count(*)
        FROM decision_facts f WHERE {amount_where}
        GROUP BY 1
    """), params).all())

    def money(value):
        return round(float(value), 2) if value is not None else None

    return {
        "coverage": {
            "total": coverage.total,
            "with_amount": coverage.with_amount,
            "share": round(coverage.with_amount / coverage.total, 3) if coverage.total else None,
        },
        "overall": {
            "sum": money(overall.sum),
            "avg": money(overall.avg),
            "median": money(overall.median),
            "p90": money(overall.p90),
        },
        "by_year": [
            {"year": r.year, "n": r.n, "sum": money(r.sum), "avg": money(r.avg), "median": money(r.median)}
            for r in by_year
        ],
        "by_body": [
            {"body": r.body, "n": r.n, "sum": money(r.sum), "avg": money(r.avg), "median": money(r.median)}
            for r in by_body
        ],
        "buckets": [
            {"label": label, "count": bucket_counts.get(label, 0)}
            for label, _, _ in AMOUNT_BUCKETS
        ],
    }


@router.get("/decisions/articles")
def decision_articles(
    min_count: int = Query(default=5, ge=1, le=100),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Contested Tax Code articles: outcome split, relief rate, amounts and
    per-instance presence for each article."""
    body_columns = ", ".join(
        f"count(*) FILTER (WHERE f.authority_body = '{b}') AS {b}"
        for b in sorted(AUTHORITY_BODIES)
    )
    rows = db.execute(text(f"""
        SELECT a.value AS article, {OUTCOME_COLUMNS},
               count(f.amount_gel) AS amount_n,
               sum(f.amount_gel) AS amount_sum,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY f.amount_gel) AS amount_median,
               {body_columns}
        FROM decision_facts f, jsonb_array_elements_text(f.contested_articles::jsonb) AS a(value)
        WHERE f.authority_body IS DISTINCT FROM 'other'
        GROUP BY 1 HAVING count(*) >= :min_count
        ORDER BY 2 DESC LIMIT :limit
    """), {"min_count": min_count, "limit": limit}).all()

    return {
        "items": [
            {
                "article": r.article,
                **_outcome_row(r),
                "amount": {
                    "n": r.amount_n,
                    "sum": round(float(r.amount_sum), 2) if r.amount_sum is not None else None,
                    "median": round(float(r.amount_median), 2) if r.amount_median is not None else None,
                },
                "by_body": {b: getattr(r, b) for b in sorted(AUTHORITY_BODIES)},
            }
            for r in rows
        ],
    }


@router.get("/decisions/chains")
def decision_chains(
    article: Optional[str] = Query(default=None, max_length=10),
    db: Session = Depends(get_db),
):
    """Appeal-chain statistics over linked decisions (same case followed across
    instances). Links exist only where the reference match was unambiguous —
    see scripts/link_decision_chains.py."""
    params = {}
    article_clause = ""
    if article:
        article_clause = """
            AND (lo.contested_articles::jsonb ? :article
                 OR hi.contested_articles::jsonb ? :article)
        """
        params["article"] = article.strip()

    rows = db.execute(text(f"""
        SELECT l.from_facts_id::text AS hi_id, l.to_facts_id::text AS lo_id,
               hi.authority_body AS hi_body, lo.authority_body AS lo_body,
               hi.in_favor AS hi_favor, lo.in_favor AS lo_favor
        FROM decision_links l
        JOIN decision_facts hi ON hi.id = l.from_facts_id
        JOIN decision_facts lo ON lo.id = l.to_facts_id
        WHERE 1=1 {article_clause}
    """), params).all()

    transitions = {}
    for r in rows:
        key = (r.lo_body, r.hi_body)
        agg = transitions.setdefault(key, {"count": 0, "outcome_changed": 0,
                                           "flipped_to_taxpayer": 0, "flipped_to_authority": 0})
        agg["count"] += 1
        if r.lo_favor and r.hi_favor and r.lo_favor != r.hi_favor:
            agg["outcome_changed"] += 1
            if r.hi_favor == "taxpayer":
                agg["flipped_to_taxpayer"] += 1
            elif r.hi_favor == "authority":
                agg["flipped_to_authority"] += 1

    # Chains = connected components over the link edges (counts are small).
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    node_body = {}
    for r in rows:
        node_body[r.hi_id] = r.hi_body
        node_body[r.lo_id] = r.lo_body
        ra, rb = find(r.hi_id), find(r.lo_id)
        if ra != rb:
            parent[ra] = rb

    components = {}
    court_bodies = {"city_court", "appeals_court", "supreme_court"}
    for node, body in node_body.items():
        root = find(node)
        comp = components.setdefault(root, {"court": False, "supreme": False})
        if body in court_bodies:
            comp["court"] = True
        if body == "supreme_court":
            comp["supreme"] = True

    return {
        "article": article,
        "links_total": len(rows),
        "transitions": [
            {"from": lo, "to": hi, **agg}
            for (lo, hi), agg in sorted(transitions.items(), key=lambda kv: -kv[1]["count"])
        ],
        "chains": {
            "total": len(components),
            "reached_court": sum(1 for c in components.values() if c["court"]),
            "reached_supreme": sum(1 for c in components.values() if c["supreme"]),
        },
    }


@router.get("/decisions")
def decision_statistics(
    article: Optional[str] = Query(default=None, max_length=10, description="Tax Code article number, e.g. 275"),
    db: Session = Depends(get_db),
):
    """Aggregated outcomes of tax/customs dispute decisions in the corpus.

    Facts with authority_body='other' (CJEU translations, municipal
    resolutions — reference material, not Georgian dispute instances) are
    excluded from all public aggregates.
    """
    params = {}
    article_join = ""
    where = "WHERE f.authority_body IS DISTINCT FROM 'other'"
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
            WHERE f.authority_body IS DISTINCT FROM 'other'
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
