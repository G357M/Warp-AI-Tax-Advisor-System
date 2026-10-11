"""Answer quality: schema, ratings, admin feed/review/reveal/summary on real PostgreSQL."""
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
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
