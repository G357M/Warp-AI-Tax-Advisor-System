"""Admin trends on real PostgreSQL: Tbilisi buckets, admin exclusion, previous window."""
import os
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from core.admin_trends import trends
from core.config import settings
from core.database import Base, engine
from models import Conversation, Message, Payment, Subscription, User
from models.answer_quality import AnswerRating
from scripts.add_admin_audit_log import apply_schema as apply_audit_schema
from scripts.add_answer_quality import apply_schema

pytestmark = pytest.mark.skipif(os.getenv("BILLING_PROVIDER_POSTGRES_TESTS") != "1",
                                reason="requires dedicated PostgreSQL")

NOW = datetime(2026, 10, 12, 10, 0)  # 14:00 in Tbilisi
GROUNDED = {"status": "grounded", "has_precise_citation": True, "source_count": 2}
NO_CITATION = {"status": "grounded", "has_precise_citation": False, "source_count": 1}


@pytest.fixture
def database():
    schema = "admin_trends_test_" + uuid4().hex
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    local = create_engine(settings.DATABASE_URL, connect_args={"options": f"-csearch_path={schema},public"},
                          execution_options={"schema_translate_map": {None: schema}})
    Base.metadata.create_all(local, tables=[m.__table__ for m in (User, Conversation, Message, Subscription, Payment)])
    with local.begin() as conn:
        conn.execute(text("ALTER TABLE messages DROP COLUMN IF EXISTS evidence"))
        conn.execute(text("ALTER TABLE messages DROP COLUMN IF EXISTS processing_ms"))
        apply_audit_schema(conn)
        apply_schema(conn)
    yield sessionmaker(bind=local, autoflush=False)
    local.dispose()
    # The identifier is generated here, never supplied by an environment/user.
    with engine.begin() as conn:
        conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


def _user(db, name, created_at, role="user"):
    user = User(email=f"{name}@example.test", username=name, password_hash="x", role=role, created_at=created_at)
    db.add(user)
    db.flush()
    return user


def _dialog(db, user, created_at, evidence=None, processing_ms=None):
    conv = Conversation(user_id=user.id, created_at=created_at, updated_at=created_at)
    db.add(conv)
    db.flush()
    answer = Message(conversation_id=conv.id, role="assistant", content="a", sources=[], evidence=evidence,
                     processing_ms=processing_ms, created_at=created_at)
    db.add_all([Message(conversation_id=conv.id, role="user", content="q", created_at=created_at), answer])
    db.flush()
    return answer


def _payment(db, user, amount, created_at, status="succeeded"):
    sub = db.query(Subscription).filter_by(user_id=user.id).one_or_none()
    if sub is None:
        sub = Subscription(user_id=user.id, plan="pro", status="active")
        db.add(sub)
        db.flush()
    db.add(Payment(subscription_id=sub.id, amount_gel=amount / 100, amount_minor=amount, provider="bog",
                   status=status, created_at=created_at))


@pytest.fixture
def seeded(database):
    with database() as db:
        nino = _user(db, "nino", datetime(2026, 10, 11, 21, 0))    # 01:00 on 12 Oct in Tbilisi
        levan = _user(db, "levan", datetime(2026, 10, 11, 19, 0))  # 23:00 on 11 Oct in Tbilisi
        old = _user(db, "old", datetime(2026, 9, 1, 8, 0))
        boss = _user(db, "boss", datetime(2026, 10, 12, 8, 0), role="admin")
        a1 = _dialog(db, nino, datetime(2026, 10, 12, 5, 0), GROUNDED, 1000)
        a2 = _dialog(db, nino, datetime(2026, 10, 12, 5, 0), NO_CITATION, 3000)
        _dialog(db, levan, datetime(2026, 10, 11, 10, 0))
        boss_answer = _dialog(db, boss, datetime(2026, 10, 12, 6, 0), GROUNDED, 9000)
        db.add_all([
            AnswerRating(message_id=a1.id, user_id=nino.id, value=1, created_at=datetime(2026, 10, 12, 7, 0)),
            AnswerRating(message_id=a2.id, user_id=nino.id, value=-1, created_at=datetime(2026, 10, 12, 7, 0)),
            AnswerRating(message_id=boss_answer.id, user_id=boss.id, value=1, created_at=datetime(2026, 10, 12, 7, 0)),
        ])
        _payment(db, nino, 4900, datetime(2026, 10, 12, 6, 0))
        _payment(db, nino, 4900, datetime(2026, 10, 12, 6, 0), status="failed")
        _payment(db, old, 2900, datetime(2026, 9, 2, 8, 0))
        _payment(db, boss, 9900, datetime(2026, 10, 12, 6, 0))
        db.commit()
    return database


def _metrics(bucket):
    return {k: v for k, v in bucket.items() if k not in ("start", "partial")}


def test_day_buckets_follow_tbilisi_time_and_skip_admins(seeded):
    with seeded() as db:
        data = trends(db, "30d", NOW)
    assert data["bucket"] == "day" and data["timezone"] == "Asia/Tbilisi" and len(data["buckets"]) == 30
    assert [b["partial"] for b in data["buckets"]] == [False] * 29 + [True]
    today, yesterday = data["buckets"][-1], data["buckets"][-2]
    assert today["start"] == "2026-10-12" and yesterday["start"] == "2026-10-11"
    assert _metrics(today) == {
        "signups": 1, "askers": 1, "questions": 2, "payments": 1, "revenue_minor": 4900, "up": 1, "down": 1,
        "answers": 2, "answers_with_evidence": 2, "flagged": 1, "median_processing_ms": 2000}
    assert _metrics(yesterday) == {
        "signups": 1, "askers": 1, "questions": 1, "payments": 0, "revenue_minor": 0, "up": 0, "down": 0,
        "answers": 1, "answers_with_evidence": 0, "flagged": 0, "median_processing_ms": None}
    assert data["quality_since"] == "2026-10-12" and data["median_processing_ms"] == 2000


def test_totals_compare_with_previous_window(seeded):
    with seeded() as db:
        data = trends(db, "30d", NOW)
    assert data["totals"]["current"] == {
        "signups": 2, "askers": 2, "questions": 3, "payments": 1, "revenue_minor": 4900, "up": 1, "down": 1}
    assert data["totals"]["previous"] == {
        "signups": 1, "askers": 0, "questions": 0, "payments": 1, "revenue_minor": 2900, "up": 0, "down": 0}


def test_month_buckets(seeded):
    with seeded() as db:
        data = trends(db, "12m", NOW)
    assert data["bucket"] == "month" and len(data["buckets"]) == 12
    assert data["buckets"][-1]["start"] == "2026-10-01" and data["buckets"][-2]["start"] == "2026-09-01"
    assert data["buckets"][-2]["revenue_minor"] == 2900 and data["buckets"][-2]["signups"] == 1
    assert data["totals"]["current"]["revenue_minor"] == 7800 and data["totals"]["current"]["signups"] == 3


def test_empty_database_returns_zeros_and_nulls(database):
    with database() as db:
        data = trends(db, "90d", NOW)
    assert len(data["buckets"]) == 13 and data["quality_since"] is None and data["median_processing_ms"] is None
    assert all(b["median_processing_ms"] is None for b in data["buckets"])
    assert all(v == 0 for b in data["buckets"] for k, v in _metrics(b).items() if k != "median_processing_ms")
    assert set(data["totals"]["current"].values()) == {0} and set(data["totals"]["previous"].values()) == {0}
