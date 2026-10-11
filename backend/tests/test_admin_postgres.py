"""Admin journal, journaled mutations and admin read APIs on real PostgreSQL."""
import os
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from api.routes import admin as admin_routes
from api.routes import admin_users
from core.config import settings
from core.database import Base, engine
from core.time_utils import utc_now
from models import (AdminAuditLog, BillingCheckout, Conversation, Document, Feedback, Message,
                    Payment, Subscription, User)
from models.document import DecisionFacts, LawAmendment
from scripts.add_admin_audit_log import apply_schema, contract_sha256

pytestmark = pytest.mark.skipif(os.getenv("BILLING_PROVIDER_POSTGRES_TESTS") != "1",
                                reason="requires dedicated PostgreSQL")

TABLES = [User, Subscription, Payment, BillingCheckout, Feedback, Document, DecisionFacts,
          LawAmendment, Conversation, Message]


@pytest.fixture
def database():
    schema = "admin_audit_test_" + uuid4().hex
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    # public stays on the path so the pgvector type resolves for documents.
    # schema_translate_map forces every ORM table into the schema even when a
    # same-named table is visible in public (has_table follows the search_path).
    local = create_engine(settings.DATABASE_URL, connect_args={"options": f"-csearch_path={schema},public"},
                          execution_options={"schema_translate_map": {None: schema}})
    Base.metadata.create_all(local, tables=[m.__table__ for m in TABLES])
    with local.begin() as conn:
        assert apply_schema(conn) == apply_schema(conn)
    sessions = sessionmaker(bind=local, autoflush=False)
    with sessions() as db:
        admin = User(email=f"{uuid4()}@example.test", username="admin-" + uuid4().hex[:8], password_hash="x", role="admin")
        user = User(email=f"{uuid4()}@example.test", username="user-" + uuid4().hex[:8], password_hash="x", role="user")
        db.add_all([admin, user])
        db.commit()
        ids = SimpleNamespace(admin_id=admin.id, user_id=user.id)
    yield sessions, ids
    local.dispose()
    # The identifier is generated here, never supplied by an environment/user.
    with engine.begin() as conn:
        conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


def test_contract_is_pinned_in_deploy_script():
    deploy = Path(__file__).resolve().parents[2] / "scripts" / "deploy_production.sh"
    assert f'ADMIN_AUDIT_SCHEMA_CONTRACT_SHA256="{contract_sha256()}"' in deploy.read_text(encoding="utf-8")


def test_journal_rejects_update_delete_and_truncate(database):
    sessions, ids = database
    with sessions() as db:
        db.add(AdminAuditLog(actor_id=ids.admin_id, action="user.role_changed", target_type="user",
                             target_id=str(ids.user_id), before={"role": "user"}, after={"role": "admin"}))
        db.commit()
    for sql in ("UPDATE admin_audit_log SET reason = 'x'", "DELETE FROM admin_audit_log",
                "TRUNCATE admin_audit_log"):
        with sessions() as db:
            with pytest.raises(DBAPIError, match="admin audit log is append-only"):
                db.execute(text(sql))
            db.rollback()
    with sessions() as db:
        assert db.query(AdminAuditLog).count() == 1


def _entries(sessions):
    with sessions() as db:
        return db.query(AdminAuditLog).order_by(AdminAuditLog.created_at).all()


def test_journal_failure_rolls_back_feedback_status(database, monkeypatch):
    sessions, ids = database
    with sessions() as db:
        item = Feedback(user_id=ids.user_id, message="Broken link", page="/laws")
        db.add(item)
        db.commit()
        feedback_id = item.id

    def broken(*_args, **_kwargs):
        raise RuntimeError("journal unavailable")

    monkeypatch.setattr(admin_routes, "record_admin_action", broken)
    with sessions() as db:
        body = admin_routes.FeedbackStatusUpdate(status="fixed", reason="link repaired")
        with pytest.raises(RuntimeError):
            admin_routes.update_feedback_status(feedback_id, body, db.get(User, ids.admin_id), db)
        db.rollback()
    with sessions() as db:
        assert db.get(Feedback, feedback_id).status == "new"
    assert _entries(sessions) == []


def test_journal_failure_rolls_back_activation(database, monkeypatch):
    from api.routes import billing as billing_routes
    sessions, ids = database
    with sessions() as db:
        checkout = _checkout(ids.user_id)
        db.add(checkout)
        db.commit()
        checkout_id = checkout.id

    def broken(*_args, **_kwargs):
        raise RuntimeError("journal unavailable")

    monkeypatch.setattr(billing_routes, "record_admin_action", broken)
    with sessions() as db:
        body = billing_routes.ActivateRequest(checkout_id=checkout_id, reason="paid by transfer")
        with pytest.raises(RuntimeError):
            billing_routes.activate_subscription(body, db.get(User, ids.admin_id), db)
        db.rollback()
    with sessions() as db:
        assert db.get(BillingCheckout, checkout_id).status == "pending"
        assert db.query(Subscription).filter_by(user_id=ids.user_id).count() == 0
        assert db.query(Payment).count() == 0
    assert _entries(sessions) == []


def test_feedback_status_change_is_journaled_once(database):
    sessions, ids = database
    with sessions() as db:
        item = Feedback(user_id=ids.user_id, message="Broken link", page="/laws")
        db.add(item)
        db.commit()
        feedback_id = item.id
    body = admin_routes.FeedbackStatusUpdate(status="fixed", reason="link repaired")
    for _ in range(2):
        with sessions() as db:
            admin_routes.update_feedback_status(feedback_id, body, db.get(User, ids.admin_id), db)
    [entry] = _entries(sessions)
    assert entry.action == "feedback.status_changed" and entry.target_id == str(feedback_id)
    assert entry.before == {"status": "new"} and entry.after == {"status": "fixed"}


def _audit(sessions, **kwargs):
    params = {"action": None, "actor_id": None, "limit": 50, "offset": 0}
    params.update(kwargs)
    with sessions() as db:
        return admin_routes.list_audit(db=db, **params)


def test_audit_listing_filters_and_paginates(database):
    sessions, ids = database
    with sessions() as db:
        actor = db.get(User, ids.admin_id)
        admin_users.update_user_role(ids.user_id, admin_users.RoleUpdate(role="admin", reason="promote"), actor, db)
        admin_users.update_user_role(ids.user_id, admin_users.RoleUpdate(role="user", reason="demote"), actor, db)
        item = Feedback(user_id=ids.user_id, message="x")
        db.add(item)
        db.commit()
        admin_routes.update_feedback_status(item.id, admin_routes.FeedbackStatusUpdate(status="fixed"), actor, db)
    everything = _audit(sessions)
    assert everything["total"] == 3
    assert everything["items"][0]["action"] == "feedback.status_changed"  # newest first
    assert everything["items"][0]["actor"]["username"].startswith("admin-")
    roles = _audit(sessions, action="user.role_changed")
    assert roles["total"] == 2 and {i["after"]["role"] for i in roles["items"]} == {"admin", "user"}
    page = _audit(sessions, limit=1, offset=1)
    assert page["total"] == 3 and len(page["items"]) == 1
    assert _audit(sessions, actor_id=ids.user_id)["total"] == 0


def _checkout(user_id, **fields):
    values = dict(user_id=user_id, plan="pro", months=1, amount_minor=4900, currency="GEL",
                  provider="manual", status="pending", idempotency_key=uuid4().hex,
                  expires_at=utc_now() + timedelta(hours=1), terms_version="2026-09-08",
                  terms_accepted_at=utc_now(), immediate_service_requested_at=utc_now())
    values.update(fields)
    return BillingCheckout(**values)


def test_stats_attention_counts_match_lists(database):
    from api.routes import billing as billing_routes
    sessions, ids = database
    with sessions() as db:
        db.add_all([
            Feedback(user_id=ids.user_id, message="new one"),
            Feedback(user_id=ids.user_id, message="done", status="fixed"),
            _checkout(ids.user_id),  # manual, pending, live
            _checkout(ids.user_id, expires_at=utc_now() - timedelta(hours=1)),  # manual, expired
            _checkout(ids.user_id, provider="tbc", status="provider_review", provider_order_id=uuid4().hex),
            _checkout(ids.user_id, provider="tbc", status="provider_unknown", provider_order_id=uuid4().hex),
        ])
        db.commit()
        stats = admin_routes.system_stats(db)
        listed = billing_routes.reconciliation_queue(limit=100, offset=0, admin=db.get(User, ids.admin_id), db=db)
    assert stats["feedback"] == {"new": 1}
    assert stats["billing"]["manual_pending"] == 1
    assert stats["billing"]["reconciliation_open"] == len(listed["items"]) == 2
    assert stats["attention"] == {"ingest_stale": True}  # no documents at all


def test_missing_feedback_is_coded_404(database):
    sessions, ids = database
    with sessions() as db:
        with pytest.raises(HTTPException) as exc:
            admin_routes.update_feedback_status(uuid4(), admin_routes.FeedbackStatusUpdate(status="fixed"),
                                                db.get(User, ids.admin_id), db)
    assert exc.value.detail == {"code": "feedback_not_found", "message": "Feedback not found"}
