"""Admin corpus page on real PostgreSQL: per-type gaps, Tbilisi weeks, queues."""
import os
from datetime import date, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from api.routes.admin_corpus import router
from core.admin_corpus import corpus
from core.config import settings
from core.database import Base, engine
from core.security import require_admin
from models import Document, DocumentChunk
from models.document import DecisionFacts, LawAmendment

pytestmark = pytest.mark.skipif(os.getenv("BILLING_PROVIDER_POSTGRES_TESTS") != "1",
                                reason="requires dedicated PostgreSQL")

NOW = datetime(2026, 10, 12, 10, 0)  # Monday 14:00 in Tbilisi


@pytest.fixture
def db():
    schema = "admin_corpus_test_" + uuid4().hex
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    # public stays on the path so the pgvector type resolves for document_chunks.
    local = create_engine(settings.DATABASE_URL, connect_args={"options": f"-csearch_path={schema},public"},
                          execution_options={"schema_translate_map": {None: schema}})
    Base.metadata.create_all(local, tables=[m.__table__ for m in (Document, DocumentChunk, DecisionFacts, LawAmendment)])
    session = sessionmaker(bind=local, autoflush=False)()
    yield session
    session.close()
    local.dispose()
    # The identifier is generated here, never supplied by an environment/user.
    with engine.begin() as conn:
        conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


def _doc(db, doc_type, created_at, published=date(2026, 1, 1), chunks=1, title="t"):
    doc = Document(title=title, document_type=doc_type, source_url="https://example.test/" + uuid4().hex,
                   date_published=published, created_at=created_at, updated_at=created_at)
    db.add(doc)
    db.flush()
    db.add_all([DocumentChunk(document_id=doc.id, chunk_index=i, content="c", created_at=created_at)
                for i in range(chunks)])
    return doc


def test_totals_by_type_and_gaps(db):
    _doc(db, "law", NOW - timedelta(days=2), chunks=3)
    _doc(db, "law", NOW - timedelta(days=40), published=None, chunks=0)
    _doc(db, "court_decision", NOW - timedelta(days=10))
    db.commit()
    result = corpus(db, NOW)
    assert result["totals"] == {"documents": 3, "chunks": 4, "added_7d": 1, "added_30d": 2,
                                "last_ingest": (NOW - timedelta(days=2)).isoformat()}
    assert result["by_type"] == [
        {"document_type": "law", "documents": 2, "added_30d": 1, "without_date": 1, "without_chunks": 1},
        {"document_type": "court_decision", "documents": 1, "added_30d": 1, "without_date": 0, "without_chunks": 0},
    ]


def test_weekly_uses_tbilisi_weeks(db):
    _doc(db, "law", datetime(2026, 10, 11, 21, 0))   # Mon 01:00 Tbilisi -> current week
    _doc(db, "law", datetime(2026, 10, 11, 19, 59))  # Sun 23:59 Tbilisi -> previous week
    _doc(db, "law", datetime(2026, 7, 26, 12, 0))    # before the 12-week window
    db.commit()
    weekly = corpus(db, NOW)["weekly"]
    assert len(weekly) == 12 and weekly[0]["week_start"] == "2026-07-27"
    assert weekly[-1] == {"week_start": "2026-10-12", "added": 1, "partial": True}
    assert weekly[-2] == {"week_start": "2026-10-05", "added": 1, "partial": False}
    assert sum(w["added"] for w in weekly) == 2


def test_pending_queues(db):
    decided = _doc(db, "court_decision", NOW)
    _doc(db, "court_decision", NOW)
    _doc(db, "law", NOW, title="საგადასახადო კოდექსში ცვლილებების შეტანის შესახებ")
    db.add(DecisionFacts(document_id=decided.id))
    db.commit()
    assert corpus(db, NOW)["pending"] == {"decision_facts": 1, "law_amendments": 1}


def test_empty_corpus(db):
    result = corpus(db, NOW)
    assert result["totals"] == {"documents": 0, "chunks": 0, "added_7d": 0, "added_30d": 0, "last_ingest": None}
    assert result["by_type"] == [] and all(w["added"] == 0 for w in result["weekly"])


def test_router_requires_admin():
    assert any(d.dependency is require_admin for d in router.dependencies)
