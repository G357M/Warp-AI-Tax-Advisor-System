"""Answer quality: schema, ratings, admin feed/review/reveal/summary on real PostgreSQL."""
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from core.config import settings
from core.database import Base, engine
from core.time_utils import utc_now
from models import AdminAuditLog, Conversation, Message, User
from models.answer_quality import AnswerRating, AnswerReview
from scripts.add_admin_audit_log import apply_schema as apply_audit_schema
from scripts.add_answer_quality import apply_schema, contract_sha256

pytestmark = pytest.mark.skipif(os.getenv("BILLING_PROVIDER_POSTGRES_TESTS") != "1",
                                reason="requires dedicated PostgreSQL")

TABLES = [User, Conversation, Message]


@pytest.fixture
def database():
    schema = "answer_quality_test_" + uuid4().hex
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    local = create_engine(settings.DATABASE_URL, connect_args={"options": f"-csearch_path={schema},public"},
                          execution_options={"schema_translate_map": {None: schema}})
    # messages is created by the ORM WITHOUT the new columns first, so the script's
    # ALTER path is exercised exactly as on production.
    Base.metadata.create_all(local, tables=[m.__table__ for m in TABLES])
    with local.begin() as conn:
        conn.execute(text("ALTER TABLE messages DROP COLUMN IF EXISTS evidence"))
        conn.execute(text("ALTER TABLE messages DROP COLUMN IF EXISTS processing_ms"))
        apply_audit_schema(conn)
        first = apply_schema(conn)
        assert apply_schema(conn) == first
    sessions = sessionmaker(bind=local, autoflush=False)
    with sessions() as db:
        admin = User(email="boss@example.test", username="boss", password_hash="x", role="admin")
        user = User(email="nino@example.test", username="nino", password_hash="x")
        other = User(email="levan@example.test", username="levan", password_hash="x")
        db.add_all([admin, user, other])
        db.commit()
        ids = SimpleNamespace(admin_id=admin.id, user_id=user.id, other_id=other.id)
    yield sessions, ids
    local.dispose()
    # The identifier is generated here, never supplied by an environment/user.
    with engine.begin() as conn:
        conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


def _dialog(db, user_id, question="What is the VAT rate?", answer="18%", evidence=None,
            processing_ms=1200, created_at=None):
    created = created_at or utc_now()
    conv = Conversation(user_id=user_id, created_at=created, updated_at=created)
    db.add(conv)
    db.flush()
    q = Message(conversation_id=conv.id, role="user", content=question, created_at=created)
    a = Message(id=uuid4(), conversation_id=conv.id, role="assistant", content=answer, sources=[],
                evidence=evidence, processing_ms=processing_ms, created_at=created)
    db.add_all([q, a])
    db.flush()
    return conv, q, a


def test_contract_is_pinned_in_deploy_script():
    deploy = Path(__file__).resolve().parents[2] / "scripts" / "deploy_production.sh"
    assert f'ANSWER_QUALITY_SCHEMA_CONTRACT_SHA256="{contract_sha256()}"' in deploy.read_text(encoding="utf-8")


def test_new_columns_store_evidence(database):
    sessions, ids = database
    with sessions() as db:
        _, _, a = _dialog(db, ids.user_id, evidence={"status": "grounded", "has_precise_citation": True})
        db.commit()
        message_id = a.id
    with sessions() as db:
        stored = db.get(Message, message_id)
        assert stored.evidence["status"] == "grounded" and stored.processing_ms == 1200


def test_one_rating_per_message_and_value_check(database):
    sessions, ids = database
    with sessions() as db:
        _, _, a = _dialog(db, ids.user_id)
        db.add(AnswerRating(message_id=a.id, user_id=ids.user_id, value=1))
        db.commit()
        message_id = a.id
    with sessions() as db:
        db.add(AnswerRating(message_id=message_id, user_id=ids.user_id, value=-1))
        with pytest.raises(DBAPIError):
            db.commit()
        db.rollback()
    with sessions() as db:
        db.execute(text("DELETE FROM answer_ratings"))
        db.commit()
        db.add(AnswerRating(message_id=message_id, user_id=ids.user_id, value=5))
        with pytest.raises(DBAPIError):
            db.commit()


def test_reviews_reject_update_delete_truncate_but_cascade(database):
    sessions, ids = database
    with sessions() as db:
        conv, _, a = _dialog(db, ids.user_id)
        db.add(AnswerReview(message_id=a.id, reviewer_id=ids.admin_id, verdict="wrong",
                            reasons=["wrong_citation"], note="cites 168"))
        db.commit()
        conv_id = conv.id
    for sql in ("UPDATE answer_reviews SET note = 'x'", "DELETE FROM answer_reviews",
                "TRUNCATE answer_reviews"):
        with sessions() as db:
            with pytest.raises(DBAPIError, match="answer reviews are append-only"):
                db.execute(text(sql))
            db.rollback()
    with sessions() as db:
        db.execute(text("DELETE FROM conversations WHERE id = :id"), {"id": conv_id})
        db.commit()
        assert db.query(AnswerReview).count() == 0


from datetime import timedelta

from api.routes import admin_quality as routes
from core import admin_quality as core_quality


def _list(sessions, **kwargs):
    params = {"period": "all", "rating": None, "verdict": None, "flags": [], "q": None, "limit": 50, "offset": 0}
    params.update(kwargs)
    with sessions() as db:
        return routes.list_answers(db=db, **params)


GROUNDED = {"status": "grounded", "has_precise_citation": True, "source_count": 2}


def test_pseudonym_is_stable_and_opaque():
    uid = uuid4()
    p = core_quality.pseudonym(uid)
    assert p == core_quality.pseudonym(uid) and p.startswith("U-") and len(p) == 8
    assert str(uid)[:6].upper() not in p and core_quality.pseudonym(uuid4()) != p


def test_feed_pairs_question_and_hides_identity(database):
    sessions, ids = database
    with sessions() as db:
        _dialog(db, ids.user_id, question="Ставка НДС?", answer="18%", evidence=GROUNDED)
        db.commit()
    page = _list(sessions)
    [row] = page["items"]
    assert page["total"] == 1 and row["question"] == "Ставка НДС?" and row["answer"] == "18%"
    assert row["pseudonym"] == core_quality.pseudonym(ids.user_id)
    dumped = str(page)
    assert "nino" not in dumped and str(ids.user_id) not in dumped


def test_feed_flags_and_old_answers(database):
    sessions, ids = database
    with sessions() as db:
        _dialog(db, ids.user_id, question="ok", evidence=GROUNDED, processing_ms=30000)
        _dialog(db, ids.user_id, question="slow", evidence=GROUNDED, processing_ms=30001)
        _dialog(db, ids.user_id, question="nocite", evidence={"status": "grounded", "has_precise_citation": False,
                                                               "source_count": 1})
        _dialog(db, ids.user_id, question="partial", evidence={"status": "partial", "has_precise_citation": False,
                                                                "source_count": 0})
        _dialog(db, ids.user_id, question="old", evidence=None, processing_ms=None)
        db.commit()
    q = lambda **kw: sorted(r["question"] for r in _list(sessions, **kw)["items"])  # noqa: E731
    assert q(flags=["slow"]) == ["slow"]
    assert q(flags=["no_precise_citation"]) == ["nocite", "partial"]
    assert q(flags=["not_grounded"]) == ["partial"]
    assert q(flags=["no_sources"]) == ["partial"]
    assert q(flags=["no_evidence"]) == ["old"]
    assert q(flags=["no_precise_citation", "no_sources"]) == ["partial"]
    rows = {r["question"]: r for r in _list(sessions)["items"]}
    assert rows["old"]["flags"] == ["no_evidence"] and rows["ok"]["flags"] == []


def test_feed_rating_verdict_period_and_search(database):
    sessions, ids = database
    with sessions() as db:
        _, _, up = _dialog(db, ids.user_id, question="liked 100%")
        _, _, down = _dialog(db, ids.user_id, question="disliked")
        _dialog(db, ids.user_id, question="ancient", created_at=utc_now() - timedelta(days=40))
        db.add_all([AnswerRating(message_id=up.id, user_id=ids.user_id, value=1),
                    AnswerRating(message_id=down.id, user_id=ids.user_id, value=-1)])
        db.flush()
        db.add(AnswerReview(message_id=down.id, reviewer_id=ids.admin_id, verdict="partial", reasons=[]))
        db.add(AnswerReview(message_id=down.id, reviewer_id=ids.admin_id, verdict="wrong", reasons=["fabricated"],
                            created_at=utc_now() + timedelta(seconds=1)))
        db.commit()
    names = lambda **kw: sorted(r["question"] for r in _list(sessions, **kw)["items"])  # noqa: E731
    assert names(rating="up") == ["liked 100%"]
    assert names(rating="down") == ["disliked"]
    assert names(rating="none") == ["ancient"]
    assert names(verdict="wrong") == ["disliked"] and names(verdict="partial") == []
    assert names(verdict="unreviewed") == ["ancient", "liked 100%"]
    assert names(period="30d") == ["disliked", "liked 100%"]
    assert names(q="100%") == ["liked 100%"] and names(q="LIKED 1") == ["liked 100%"]


def test_detail_has_dialog_rating_reviews_and_neighbors(database):
    sessions, ids = database
    now = utc_now()
    with sessions() as db:
        _, _, a1 = _dialog(db, ids.user_id, question="first", created_at=now - timedelta(minutes=3))
        _, _, a2 = _dialog(db, ids.user_id, question="second", evidence=GROUNDED, created_at=now - timedelta(minutes=2))
        _, _, a3 = _dialog(db, ids.user_id, question="third", created_at=now - timedelta(minutes=1))
        db.add(AnswerRating(message_id=a2.id, user_id=ids.user_id, value=-1, comment="wrong"))
        db.commit()
        a1_id, a2_id, a3_id = a1.id, a2.id, a3.id
    with sessions() as db:
        detail = routes.get_answer(a2_id, period="all", rating=None, verdict=None, flags=[], q=None, db=db)
    assert detail["message"]["evidence"]["status"] == "grounded"
    assert [m["role"] for m in detail["conversation"]["messages"]] == ["user", "assistant"]
    assert detail["rating"]["comment"] == "wrong" and detail["reviews"] == []
    assert detail["neighbors"] == {"prev_id": str(a3_id), "next_id": str(a1_id)}
    with sessions() as db:
        only_down = routes.get_answer(a2_id, period="all", rating="down", verdict=None, flags=[], q=None, db=db)
    assert only_down["neighbors"] == {"prev_id": None, "next_id": None}
    with sessions() as db:
        with pytest.raises(HTTPException) as exc:
            routes.get_answer(uuid4(), period="all", rating=None, verdict=None, flags=[], q=None, db=db)
    assert exc.value.detail["code"] == "message_not_found"


def test_summary(database):
    sessions, ids = database
    with sessions() as db:
        _, _, a = _dialog(db, ids.user_id, evidence=GROUNDED, processing_ms=1000)
        _, _, b = _dialog(db, ids.user_id, evidence={"status": "partial", "has_precise_citation": False}, processing_ms=3000)
        _dialog(db, ids.user_id, evidence=None, processing_ms=None)
        db.add_all([AnswerRating(message_id=a.id, user_id=ids.user_id, value=1),
                    AnswerRating(message_id=b.id, user_id=ids.user_id, value=-1)])
        db.flush()
        db.add(AnswerReview(message_id=a.id, reviewer_id=ids.admin_id, verdict="correct", reasons=[]))
        db.commit()
    with sessions() as db:
        s = routes.get_summary(period="7d", db=db)
    assert s["answers"] == 3 and s["rated"] == 2 and s["down"] == 1 and s["down_share"] == 0.5
    assert s["reviewed"] == 1 and s["verdicts"] == {"correct": 1, "partial": 0, "wrong": 0}
    assert s["no_precise_citation_share"] == 0.5 and s["median_processing_ms"] == 2000
    assert s["down_unreviewed"] == 1


def test_summary_empty_period_returns_nulls(database):
    sessions, _ = database
    with sessions() as db:
        s = routes.get_summary(period="7d", db=db)
    assert s["answers"] == 0 and s["down_share"] is None and s["median_processing_ms"] is None
