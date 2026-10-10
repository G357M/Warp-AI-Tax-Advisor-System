"""Admin journal, journaled mutations and admin read APIs on real PostgreSQL."""
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
    local = create_engine(settings.DATABASE_URL, connect_args={"options": f"-csearch_path={schema},public"})
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
