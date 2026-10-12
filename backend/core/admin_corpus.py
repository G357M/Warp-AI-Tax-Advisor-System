"""Admin Corpus page: what the document base holds and how it grows (read-only)."""
from datetime import datetime, timedelta

from sqlalchemy import exists, func, select, text
from sqlalchemy.orm import Session

from core.admin_trends import TBILISI_OFFSET, tbilisi_midnight_utc, window_of
from models import Document, DocumentChunk

WEEKS = 12

# Same queue definitions the nightly extractors work through.
_PENDING = text("""
    SELECT
      (SELECT count(*) FROM documents d LEFT JOIN decision_facts f ON f.document_id = d.id
         WHERE d.document_type='court_decision' AND f.id IS NULL
           AND (d.metadata->>'kind') IS DISTINCT FROM 'digest') AS decision_facts,
      (SELECT count(*) FROM documents d LEFT JOIN law_amendments a ON a.amendment_doc_id = d.id
         WHERE d.document_type='law' AND d.title ILIKE '%ცვლილებ%' AND a.id IS NULL) AS law_amendments
""")


def _by_type(db: Session, since_30d: datetime) -> list:
    has_chunks = exists().where(DocumentChunk.document_id == Document.id)
    total = func.count(Document.id)
    rows = db.execute(
        select(Document.document_type, total.label("documents"),
               total.filter(Document.created_at >= since_30d).label("added_30d"),
               total.filter(Document.date_published.is_(None)).label("without_date"),
               total.filter(~has_chunks).label("without_chunks"))
        .group_by(Document.document_type)
        .order_by(total.desc(), Document.document_type)
    ).mappings().all()
    return [dict(r) for r in rows]


def _weekly(db: Session, now: datetime) -> list:
    w = window_of("week", WEEKS, now)
    key = func.date_trunc("week", Document.created_at + TBILISI_OFFSET).label("week")
    rows = db.execute(
        select(key, func.count(Document.id).label("added"))
        .where(Document.created_at >= tbilisi_midnight_utc(w.starts[0]),
               Document.created_at < tbilisi_midnight_utc(w.end))
        .group_by(key)
    ).all()
    counts = {r.week.date(): r.added for r in rows}
    return [{"week_start": s.isoformat(), "added": counts.get(s, 0), "partial": s == w.starts[-1]}
            for s in w.starts]


def corpus(db: Session, now: datetime) -> dict:
    by_type = _by_type(db, now - timedelta(days=30))
    added_7d = db.execute(select(func.count(Document.id)).where(Document.created_at >= now - timedelta(days=7))).scalar()
    last_ingest = db.execute(select(func.max(Document.created_at))).scalar()
    pending = db.execute(_PENDING).one()
    return {
        "totals": {
            "documents": sum(r["documents"] for r in by_type),
            "chunks": db.execute(select(func.count(DocumentChunk.id))).scalar(),
            "added_7d": added_7d,
            "added_30d": sum(r["added_30d"] for r in by_type),
            "last_ingest": last_ingest.isoformat() if last_ingest else None,
        },
        "by_type": by_type,
        "weekly": _weekly(db, now),
        "pending": {"decision_facts": pending.decision_facts, "law_amendments": pending.law_amendments},
    }
