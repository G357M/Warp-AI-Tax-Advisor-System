# Admin Stage 1 — Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `/admin` one site-consistent visual system with RU/KA/EN copy, an append-only journal of administrator actions, an attention-first Dashboard and an honest read-only Config page.

**Architecture:** Backend adds `admin_audit_log` (installed by a SHA-pinned additive schema script, append-only via trigger), a `record_admin_action` helper called inside the same transaction as each admin mutation, and three read endpoints (`/admin/audit`, extended `/admin/stats`, `/admin/config`). Frontend replaces inline styles with one CSS module on `globals.css` tokens, a small component kit in `components/admin/`, and a typed RU/KA/EN dictionary.

**Tech Stack:** FastAPI, SQLAlchemy 2, PostgreSQL 15 + pgvector, pytest; Next.js 16 / React 19, CSS Modules, Radix Dialog, Playwright 1.62.

**Spec:** `docs/superpowers/specs/2026-10-11-admin-stage1-foundation-design.md`

## Global Constraints

- One role: `admin`. No new roles, no permission matrix.
- No new UI libraries; reuse `components/ui/Dialog.tsx` (`GlassDialog`) and `@radix-ui/react-icons`.
- Every page under `frontend/app/admin/**` and every file in `frontend/components/admin/**`: no `style={{…}}` except objects whose only keys are CSS custom properties (`'--w'`, `'--c'`).
- Colours only from `globals.css` tokens (`--background`, `--foreground`, `--muted`, `--muted-foreground`, `--primary`, `--secondary`, `--success`, `--error`, `--error-foreground`, `--error-border`, `--border`, `--input`, `--ring`, `--radius`) plus warning `#d97706` and the validated outcome palette `#059669 / #d97706 / #3b82f6` on Analytics.
- All admin copy in RU/KA/EN; Georgian strings reviewed with the `georgian-writing-style` skill before the task's commit.
- `before`/`after` in the journal never contain passwords, hashes, tokens or secrets — only the fields named in this plan.
- `reason` ≤ 1000 characters, optional.
- `/admin/config` never returns a secret value; secrets appear only as booleans.
- `/admin/billing` behaviour is unchanged; only colours change.
- All shell commands are prefixed with `rtk` (user rule). Backend tests run from `backend/` with the CI placeholder env:
  `DATABASE_URL=postgresql://test:test@localhost:5432/test REDIS_URL=redis://localhost:6379/0 SECRET_KEY=test-secret JWT_SECRET_KEY=test-jwt`.
- PostgreSQL tests are gated by `BILLING_PROVIDER_POSTGRES_TESTS=1` and need a pgvector PostgreSQL at `DATABASE_URL` (CI job `temporal-postgres`; locally: `docker run --rm -d -p 5432:5432 -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test -e POSTGRES_DB=test pgvector/pgvector:pg15` then `CREATE EXTENSION vector`).

## Review Focus

1. **No-op mutation** (role set to the value it already has; feedback set to its current status; activation replay) — expected: success response, no journal row. Tests in Task 2.
2. **Admin demotes themselves** — expected: existing 400, no journal row. Test in Task 2.
3. **Reason with only whitespace or > 1000 chars** — expected: stored as `NULL` / truncated to 1000, request accepted (API max_length rejects > 1000 at the schema; helper truncates defensively). Tests in Tasks 1 and 2.
4. **Dashboard count vs. Payments list drift** — expected: `billing.reconciliation_open` equals the full reconciliation list length. Test in Task 3.
5. **Narrow phone (390 px) with long emails / Georgian labels** — expected: no horizontal page scroll on any admin page. Test in Task 8.

---

## File Structure

Backend
- Create `backend/models/admin_audit.py` — `AdminAuditLog` ORM model.
- Modify `backend/models/__init__.py` — export it.
- Create `backend/core/admin_audit.py` — `record_admin_action`, action/target constants.
- Create `backend/scripts/add_admin_audit_log.py` — pinned DDL + audit.
- Create `backend/billing/reconciliation.py` — `reconciliation_queue_filter()` shared by list and counter.
- Create `backend/core/public_config.py` — whitelisted config view.
- Modify `backend/api/routes/admin.py` — journal role/feedback changes; `/audit`, `/config`; extend `/stats`.
- Modify `backend/api/routes/billing.py` — use shared filter; journal activation; `reason`.
- Modify `scripts/deploy_production.sh` — install step.
- Modify `.github/workflows/ci.yml` — new test files.
- Tests: `backend/tests/test_admin_audit.py`, `backend/tests/test_public_config.py`, `backend/tests/test_admin_postgres.py`, modify `backend/tests/test_integration.py`.

Frontend
- Rewrite `frontend/app/admin/admin.module.css` — the whole admin style system.
- Create `frontend/lib/admin-i18n.ts` — RU/KA/EN copy, locale, date helpers.
- Create `frontend/components/admin/{PageHeader,StatTile,Badge,AdminState,Pagination,DataTable,ConfirmDialog}.tsx`.
- Rewrite `frontend/app/admin/layout.tsx`, `page.tsx`, `settings/page.tsx`, `users/page.tsx`, `feedback/page.tsx`, `documents/page.tsx`, `scraper/page.tsx`, `analytics/page.tsx`; create `frontend/app/admin/audit/page.tsx`.
- Modify `frontend/app/admin/billing/reconciliation.module.css`, `frontend/app/admin/billing/DESIGN.md`.
- Create `frontend/scripts/check-admin-inline-styles.mjs`; modify `frontend/package.json`.
- Create `frontend/e2e/admin.spec.ts`; modify `frontend/playwright.config.ts`.

---

### Task 1: Append-only admin audit journal (schema, model, helper)

**Files:**
- Create: `backend/models/admin_audit.py`
- Modify: `backend/models/__init__.py`
- Create: `backend/core/admin_audit.py`
- Create: `backend/scripts/add_admin_audit_log.py`
- Modify: `scripts/deploy_production.sh` (after the billing review journal step, ~line 109)
- Modify: `.github/workflows/ci.yml` (backend test list ~line 94; postgres list ~line 247)
- Test: `backend/tests/test_admin_audit.py`, `backend/tests/test_admin_postgres.py`

**Interfaces:**
- Produces:
  - `models.AdminAuditLog` (columns `id, actor_id, action, target_type, target_id, before, after, reason, created_at`).
  - `core.admin_audit.ADMIN_ACTIONS: frozenset[str]` = `{"user.role_changed", "subscription.activated", "feedback.status_changed"}`.
  - `core.admin_audit.TARGET_TYPES: frozenset[str]` = `{"user", "checkout", "feedback"}`.
  - `core.admin_audit.record_admin_action(db, *, actor, action: str, target_type: str, target_id, before: dict | None = None, after: dict | None = None, reason: str | None = None) -> AdminAuditLog` — adds and flushes, never commits.
  - `scripts.add_admin_audit_log.apply_schema(connection) -> dict`, `contract_sha256() -> str`.
  - Postgres test fixture `database` in `tests/test_admin_postgres.py` yielding `(sessionmaker, ids)` where `ids = SimpleNamespace(admin_id, user_id)`.

- [ ] **Step 1: Write the failing unit tests**

`backend/tests/test_admin_audit.py`:

```python
"""record_admin_action validates input and never commits."""
from types import SimpleNamespace
from uuid import uuid4

import pytest

from core.admin_audit import ADMIN_ACTIONS, REASON_MAX_LENGTH, record_admin_action


class FakeSession:
    def __init__(self):
        self.added, self.flushed, self.committed = [], 0, 0

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        self.flushed += 1

    def commit(self):  # pragma: no cover - must never be called
        self.committed += 1


def actor():
    return SimpleNamespace(id=uuid4())


def test_records_entry_without_commit():
    db, admin, target = FakeSession(), actor(), uuid4()
    entry = record_admin_action(db, actor=admin, action="user.role_changed", target_type="user",
                                target_id=target, before={"role": "user"}, after={"role": "admin"},
                                reason="  promote  ")
    assert db.added == [entry] and db.flushed == 1 and db.committed == 0
    assert entry.actor_id == admin.id and entry.target_id == str(target)
    assert entry.before == {"role": "user"} and entry.after == {"role": "admin"}
    assert entry.reason == "promote"


@pytest.mark.parametrize("reason", [None, "", "   \n\t"])
def test_blank_reason_is_null(reason):
    entry = record_admin_action(FakeSession(), actor=actor(), action="feedback.status_changed",
                                target_type="feedback", target_id=uuid4(), reason=reason)
    assert entry.reason is None


def test_reason_is_truncated():
    entry = record_admin_action(FakeSession(), actor=actor(), action="feedback.status_changed",
                                target_type="feedback", target_id=uuid4(), reason="x" * 1500)
    assert len(entry.reason) == REASON_MAX_LENGTH == 1000


def test_unknown_action_and_target_are_rejected():
    with pytest.raises(ValueError):
        record_admin_action(FakeSession(), actor=actor(), action="user.deleted", target_type="user", target_id=uuid4())
    with pytest.raises(ValueError):
        record_admin_action(FakeSession(), actor=actor(), action="user.role_changed", target_type="org", target_id=uuid4())


def test_action_set_is_closed():
    assert ADMIN_ACTIONS == {"user.role_changed", "subscription.activated", "feedback.status_changed"}
```

- [ ] **Step 2: Run to verify failure**

Run (from `backend/`, with the CI env vars): `rtk python -m pytest tests/test_admin_audit.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.admin_audit'`.

- [ ] **Step 3: Implement model and helper**

`backend/models/admin_audit.py`:

```python
"""
Append-only journal of administrator actions.

Rows are inserted in the same transaction as the change they describe and are
never updated or deleted (enforced by a PostgreSQL trigger installed by
scripts/add_admin_audit_log.py).
"""
from uuid import uuid4

from sqlalchemy import JSON, Column, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID

from core.database import Base
from core.time_utils import utc_now


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_log"
    __table_args__ = (
        Index("ix_admin_audit_created", "created_at"),
        Index("ix_admin_audit_action_created", "action", "created_at"),
        Index("ix_admin_audit_actor_created", "actor_id", "created_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    # No FK: removing an account must not rewrite or block the journal.
    actor_id = Column(UUID(as_uuid=True), nullable=False)
    action = Column(String(64), nullable=False)
    target_type = Column(String(32), nullable=False)
    target_id = Column(String(64), nullable=False)
    before = Column(JSON, nullable=True)
    after = Column(JSON, nullable=True)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
```

`backend/models/__init__.py` — add the import and export:

```python
from models.admin_audit import AdminAuditLog
```

and append `"AdminAuditLog",` to `__all__`.

`backend/core/admin_audit.py`:

```python
"""Record administrator actions in the append-only journal."""
from models import AdminAuditLog

ADMIN_ACTIONS = frozenset({"user.role_changed", "subscription.activated", "feedback.status_changed"})
TARGET_TYPES = frozenset({"user", "checkout", "feedback"})
REASON_MAX_LENGTH = 1000


def record_admin_action(db, *, actor, action, target_type, target_id,
                        before=None, after=None, reason=None) -> AdminAuditLog:
    """Add a journal row to the caller's transaction; the caller commits.

    Flushing here surfaces an insert failure before the caller commits, so the
    change and its journal row succeed or fail together.
    """
    if action not in ADMIN_ACTIONS:
        raise ValueError(f"Unknown admin action: {action}")
    if target_type not in TARGET_TYPES:
        raise ValueError(f"Unknown admin target type: {target_type}")
    cleaned = (reason or "").strip()[:REASON_MAX_LENGTH] or None
    entry = AdminAuditLog(
        actor_id=actor.id,
        action=action,
        target_type=target_type,
        target_id=str(target_id),
        before=before,
        after=after,
        reason=cleaned,
    )
    db.add(entry)
    db.flush()
    return entry
```

- [ ] **Step 4: Run unit tests to verify they pass**

Run: `rtk python -m pytest tests/test_admin_audit.py -q`
Expected: 7 passed.

- [ ] **Step 5: Write the failing PostgreSQL schema tests**

`backend/tests/test_admin_postgres.py`:

```python
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
```

- [ ] **Step 6: Run to verify failure**

Run (PostgreSQL up, `BILLING_PROVIDER_POSTGRES_TESTS=1`): `rtk python -m pytest tests/test_admin_postgres.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.add_admin_audit_log'`.

- [ ] **Step 7: Implement the schema script**

`backend/scripts/add_admin_audit_log.py`:

```python
#!/usr/bin/env python3
"""Install the additive, append-only administrator action journal; dry plan by default."""
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import inspect, text

from scripts.schema_contract_cli import ddl_contract_sha256, run

DDL = (
    '''CREATE TABLE IF NOT EXISTS admin_audit_log (
        id UUID PRIMARY KEY,
        actor_id UUID NOT NULL,
        action VARCHAR(64) NOT NULL,
        target_type VARCHAR(32) NOT NULL,
        target_id VARCHAR(64) NOT NULL,
        "before" JSON,
        "after" JSON,
        reason TEXT,
        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
    )''',
    "CREATE INDEX IF NOT EXISTS ix_admin_audit_created ON admin_audit_log (created_at DESC)",
    "CREATE INDEX IF NOT EXISTS ix_admin_audit_action_created ON admin_audit_log (action, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_admin_audit_actor_created ON admin_audit_log (actor_id, created_at)",
    '''CREATE OR REPLACE FUNCTION reject_admin_audit_mutation() RETURNS trigger
       LANGUAGE plpgsql AS $$ BEGIN
         RAISE EXCEPTION 'admin audit log is append-only';
       END; $$''',
    "DROP TRIGGER IF EXISTS admin_audit_immutable ON admin_audit_log",
    '''CREATE TRIGGER admin_audit_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
       ON admin_audit_log FOR EACH STATEMENT EXECUTE FUNCTION reject_admin_audit_mutation()''',
    "ALTER TABLE admin_audit_log ENABLE ALWAYS TRIGGER admin_audit_immutable",
)

EXPECTED_COLUMNS = {"id", "actor_id", "action", "target_type", "target_id", "before", "after",
                    "reason", "created_at"}


def contract_sha256() -> str:
    return ddl_contract_sha256(DDL)


def apply_schema(connection) -> dict:
    for sql in DDL:
        connection.execute(text(sql))
    columns = {column["name"] for column in inspect(connection).get_columns("admin_audit_log")}
    trigger = connection.execute(text("""SELECT tgenabled FROM pg_trigger
        WHERE tgrelid = 'admin_audit_log'::regclass AND tgname = 'admin_audit_immutable'""")).scalar_one()
    if EXPECTED_COLUMNS - columns or trigger != "A":
        raise RuntimeError("Admin audit journal schema audit failed")
    return {"missing_columns": [], "append_only_trigger": True}


def main() -> int:
    return run(
        output_key="ADMIN_AUDIT_SCHEMA",
        label="Admin audit journal",
        contract=contract_sha256(),
        apply_schema=apply_schema,
    )


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 8: Pin the contract in the deploy script**

Run (from `backend/`): `rtk python scripts/add_admin_audit_log.py`
Expected output: `ADMIN_AUDIT_SCHEMA={"contract_sha256": "<64 hex>", "execute": false}`. Copy the hex value.

In `scripts/deploy_production.sh`, directly after the `add_billing_review_journal.py` block, insert (replace `<64 hex>` with the printed value):

```bash
# Install the append-only administrator action journal before runtime writes to it.
ADMIN_AUDIT_SCHEMA_CONTRACT_SHA256="<64 hex>"
docker compose run --rm --no-deps backend \
    python scripts/add_admin_audit_log.py \
        --apply \
        --expected-contract-sha256 "$ADMIN_AUDIT_SCHEMA_CONTRACT_SHA256"
```

- [ ] **Step 9: Run PostgreSQL tests to verify they pass**

Run: `rtk python -m pytest tests/test_admin_postgres.py -q`
Expected: 2 passed.

- [ ] **Step 10: Wire tests into CI**

In `.github/workflows/ci.yml`, step "Run current API contracts": add `tests/test_admin_audit.py` on its own line after `tests/test_billing_gateway.py`. Step "Exercise PostgreSQL immutability and interval triggers": add `tests/test_admin_postgres.py` after `tests/test_billing_review_postgres.py`.

- [ ] **Step 11: Commit**

```bash
rtk git add backend/models/admin_audit.py backend/models/__init__.py backend/core/admin_audit.py backend/scripts/add_admin_audit_log.py backend/tests/test_admin_audit.py backend/tests/test_admin_postgres.py scripts/deploy_production.sh .github/workflows/ci.yml
rtk git commit -m "feat(admin): add append-only admin action journal"
```

---

### Task 2: Journal existing admin mutations

**Files:**
- Modify: `backend/api/routes/admin.py` (`RoleUpdate`, `update_user_role`, `FeedbackStatusUpdate`, `update_feedback_status`)
- Modify: `backend/api/routes/billing.py` (`ActivateRequest` ~line 58, `activate_subscription` ~line 854)
- Test: `backend/tests/test_admin_postgres.py` (append), `backend/tests/test_integration.py`

**Interfaces:**
- Consumes: `record_admin_action`, `AdminAuditLog`, fixture `database` (Task 1).
- Produces: request bodies `RoleUpdate{role, reason?}`, `FeedbackStatusUpdate{status, reason?}`, `ActivateRequest{…, reason?}`; `update_feedback_status(feedback_id, body, admin, db)` now takes `admin` as its third parameter.

- [ ] **Step 1: Write failing PostgreSQL tests** (append to `backend/tests/test_admin_postgres.py`)

```python
from fastapi import HTTPException

from api.routes import admin as admin_routes


def _entries(sessions):
    with sessions() as db:
        return db.query(AdminAuditLog).order_by(AdminAuditLog.created_at).all()


def test_role_change_is_journaled_with_reason(database):
    sessions, ids = database
    with sessions() as db:
        actor = db.get(User, ids.admin_id)
        admin_routes.update_user_role(ids.user_id, admin_routes.RoleUpdate(role="admin", reason=" promote "), actor, db)
    [entry] = _entries(sessions)
    assert (entry.action, entry.target_type, entry.target_id) == ("user.role_changed", "user", str(ids.user_id))
    assert entry.before == {"role": "user"} and entry.after == {"role": "admin"}
    assert entry.reason == "promote" and entry.actor_id == ids.admin_id


def test_unchanged_role_is_not_journaled(database):
    sessions, ids = database
    with sessions() as db:
        actor = db.get(User, ids.admin_id)
        result = admin_routes.update_user_role(ids.user_id, admin_routes.RoleUpdate(role="user"), actor, db)
    assert result["role"] == "user" and _entries(sessions) == []


def test_self_demotion_is_rejected_without_entry(database):
    sessions, ids = database
    with sessions() as db:
        actor = db.get(User, ids.admin_id)
        with pytest.raises(HTTPException) as exc:
            admin_routes.update_user_role(ids.admin_id, admin_routes.RoleUpdate(role="user"), actor, db)
    assert exc.value.status_code == 400 and _entries(sessions) == []


def test_journal_failure_rolls_back_role_change(database, monkeypatch):
    sessions, ids = database

    def broken(*_args, **_kwargs):
        raise RuntimeError("journal unavailable")

    monkeypatch.setattr(admin_routes, "record_admin_action", broken)
    with sessions() as db:
        actor = db.get(User, ids.admin_id)
        with pytest.raises(RuntimeError):
            admin_routes.update_user_role(ids.user_id, admin_routes.RoleUpdate(role="admin"), actor, db)
    with sessions() as db:
        assert db.get(User, ids.user_id).role == "user"
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
```

- [ ] **Step 2: Write failing integration assertions** (`backend/tests/test_integration.py`)

Add `AdminAuditLog` to the `from models import (...)` list and to `TEST_TABLES` (after `BillingReviewDecision.__table__`). In `test_admin_checkout_settlement_is_idempotent`, change the first activation call to send a reason:

```python
    activated = client.post(
        "/api/v1/billing/admin/activate",
        json={"checkout_id": checkout_id, "reason": "bank transfer received"},
    )
```

and inside the final `try:` block, after the existing payment assertions, add:

```python
        [entry] = db.query(AdminAuditLog).filter_by(target_id=checkout_id).all()
        assert entry.action == "subscription.activated" and entry.target_type == "checkout"
        assert entry.actor_id == db.query(User).filter_by(username=admin_username).one().id
        assert entry.before is None
        assert entry.after["plan"] == "pro" and entry.after["status"] == "active"
        assert entry.reason == "bank transfer received"
```

Add a new test after it:

```python
def test_legacy_email_activation_is_journaled(client):
    register_and_login(client, "legacy-customer")
    register_and_login(client, "legacy-admin")
    _make_current_user_admin("legacy-admin")
    with TestingSessionLocal() as db:
        customer = db.query(User).filter_by(username="legacy-customer").one()
        email, customer_id = customer.email, customer.id
    response = client.post("/api/v1/billing/admin/activate",
                           json={"email": email, "plan": "business", "months": 3})
    assert response.status_code == 200
    with TestingSessionLocal() as db:
        [entry] = db.query(AdminAuditLog).filter_by(target_id=str(customer_id)).all()
        assert (entry.action, entry.target_type) == ("subscription.activated", "user")
        assert entry.after["plan"] == "business" and entry.reason is None
```

- [ ] **Step 3: Run to verify failure**

Run: `rtk python -m pytest tests/test_integration.py -k "settlement_is_idempotent or legacy_email_activation" -q` and (PostgreSQL) `rtk python -m pytest tests/test_admin_postgres.py -q`
Expected: FAIL — `RoleUpdate` has no field `reason` / no `AdminAuditLog` rows found.

- [ ] **Step 4: Implement journaling in `backend/api/routes/admin.py`**

Add import: `from core.admin_audit import record_admin_action`. Replace `RoleUpdate`, `update_user_role`, `FeedbackStatusUpdate`, `update_feedback_status` with:

```python
class RoleUpdate(BaseModel):
    role: str = Field(pattern="^(user|admin)$")
    reason: Optional[str] = Field(default=None, max_length=1000)


@router.patch("/users/{user_id}/role")
def update_user_role(
    user_id: UUID,
    body: RoleUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if user_id == admin.id and body.role != "admin":
        raise HTTPException(status_code=400, detail="Нельзя снять права администратора с самого себя.")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role != body.role:
        before = {"role": user.role}
        user.role = body.role
        record_admin_action(db, actor=admin, action="user.role_changed", target_type="user",
                            target_id=user.id, before=before, after={"role": user.role}, reason=body.reason)
        db.commit()
    return {"id": str(user.id), "username": user.username, "role": user.role}
```

```python
class FeedbackStatusUpdate(BaseModel):
    status: str = Field(pattern="^(new|in_progress|fixed)$")
    reason: Optional[str] = Field(default=None, max_length=1000)


@router.patch("/feedback/{feedback_id}")
def update_feedback_status(
    feedback_id: UUID,
    body: FeedbackStatusUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    item = db.get(Feedback, feedback_id)
    if not item:
        raise HTTPException(status_code=404, detail="Feedback not found")
    if item.status != body.status:
        before = {"status": item.status}
        item.status = body.status
        record_admin_action(db, actor=admin, action="feedback.status_changed", target_type="feedback",
                            target_id=item.id, before=before, after={"status": item.status}, reason=body.reason)
        db.commit()
    return {"id": str(item.id), "status": item.status}
```

- [ ] **Step 5: Implement journaling in `backend/api/routes/billing.py`**

Add import: `from core.admin_audit import record_admin_action`. In `ActivateRequest` add the field after `months`:

```python
    reason: Optional[str] = Field(default=None, max_length=1000)
```

Add helper above `activate_subscription`:

```python
def _subscription_snapshot(db: Session, user_id) -> Optional[dict]:
    """Access-relevant subscription fields for the admin journal; no payment data."""
    sub = db.query(Subscription).filter_by(user_id=user_id).first()
    if not sub:
        return None
    return {
        "plan": sub.plan,
        "status": sub.status,
        "period_end": sub.period_end.isoformat() if sub.period_end else None,
    }
```

In `activate_subscription`: delete the line `del admin`. In the checkout branch, immediately before `payment = _settle_checkout(db, user, checkout, "manual", None)` insert `before = _subscription_snapshot(db, user.id)`, and between that `_settle_checkout` call and its `db.commit()` insert:

```python
        db.flush()
        record_admin_action(db, actor=admin, action="subscription.activated", target_type="checkout",
                            target_id=checkout.id, before=before,
                            after=_subscription_snapshot(db, user.id), reason=body.reason)
```

In the legacy branch, insert `before = _subscription_snapshot(db, user.id)` immediately after `user` is found (before `plan = PLAN_CATALOG[...]`), and between `payment = _settle_checkout(db, user, legacy_checkout, "manual", None)` and its `db.commit()` insert:

```python
    db.flush()
    record_admin_action(db, actor=admin, action="subscription.activated", target_type="user",
                        target_id=user.id, before=before,
                        after=_subscription_snapshot(db, user.id), reason=body.reason)
```

The `replayed: True` return path is unchanged and records nothing.

- [ ] **Step 6: Run tests to verify they pass**

Run: `rtk python -m pytest tests/test_integration.py tests/test_admin_audit.py -q` and (PostgreSQL) `rtk python -m pytest tests/test_admin_postgres.py tests/test_billing_review_postgres.py -q`
Expected: all pass (integration count = previous + 1).

- [ ] **Step 7: Commit**

```bash
rtk git add backend/api/routes/admin.py backend/api/routes/billing.py backend/tests/test_admin_postgres.py backend/tests/test_integration.py
rtk git commit -m "feat(admin): journal role, feedback and manual activation changes"
```

---

### Task 3: Admin read APIs — audit list, attention stats, config

**Files:**
- Create: `backend/billing/reconciliation.py`
- Create: `backend/core/public_config.py`
- Modify: `backend/api/routes/billing.py` (`reconciliation_queue` ~line 214)
- Modify: `backend/api/routes/admin.py` (`system_stats`, new `list_audit`, `admin_config`)
- Modify: `.github/workflows/ci.yml`
- Test: `backend/tests/test_public_config.py`, `backend/tests/test_admin_postgres.py` (append)

**Interfaces:**
- Consumes: `AdminAuditLog`, fixture `database`.
- Produces (HTTP contracts the frontend uses in Tasks 5–7):
  - `GET /api/v1/admin/audit?action=&actor_id=&limit=&offset=` → `{"total": int, "items": [{"id": str, "actor": {"id": str, "username": str | null}, "action": str, "target_type": str, "target_id": str, "before": object | null, "after": object | null, "reason": str | null, "created_at": str}]}` (newest first; `created_at` naive UTC ISO).
  - `GET /api/v1/admin/stats` gains `"feedback": {"new": int}`, `"billing": {"reconciliation_open": int, "manual_pending": int}`, `"attention": {"ingest_stale": bool}`.
  - `GET /api/v1/admin/config` → `{"app": {...}, "llm": {...}, "email": {...}, "billing": {...}, "limits": {...}, "secrets": {NAME: bool}}`.
  - Python: `billing.reconciliation.reconciliation_queue_filter()` → SQLAlchemy boolean clause; `core.public_config.public_config(source=settings) -> dict`, `PUBLIC_CONFIG`, `SECRET_PRESENCE`.

- [ ] **Step 1: Write failing config tests** — `backend/tests/test_public_config.py`

```python
"""The admin config view exposes a fixed whitelist and never a secret value."""
import json
import re
from types import SimpleNamespace

from pydantic import SecretStr

from core.config import Settings
from core.public_config import PUBLIC_CONFIG, SECRET_PRESENCE, public_config

SECRET_NAME = re.compile(r"SECRET|PASSWORD|KEY|TOKEN")


def fake_source(**overrides):
    values = {name: f"value-{name}" for keys in PUBLIC_CONFIG.values() for name in keys}
    values.update({name: SecretStr(f"leak-{name}-0123456789") for name in SECRET_PRESENCE})
    values.update(overrides)
    return SimpleNamespace(**values)


def test_secret_values_never_appear():
    source = fake_source()
    payload = json.dumps(public_config(source), default=str)
    for name in SECRET_PRESENCE:
        assert f"leak-{name}" not in payload
    assert public_config(source)["secrets"] == {name: True for name in SECRET_PRESENCE}


def test_missing_or_blank_secrets_are_false():
    source = fake_source(OPENAI_API_KEY=None, SMTP_PASSWORD=SecretStr("   "), TBC_API_KEY="")
    secrets = public_config(source)["secrets"]
    assert secrets["OPENAI_API_KEY"] is False and secrets["SMTP_PASSWORD"] is False and secrets["TBC_API_KEY"] is False


def test_whitelist_contains_no_secret_named_settings():
    exposed = {name for keys in PUBLIC_CONFIG.values() for name in keys}
    secret_fields = {name for name in Settings.model_fields if SECRET_NAME.search(name)}
    assert exposed.isdisjoint(secret_fields)
    assert set(SECRET_PRESENCE) <= set(Settings.model_fields)
    assert exposed <= set(Settings.model_fields)


def test_free_quota_is_reported():
    assert public_config(fake_source())["billing"]["FREE_DAILY_QUESTIONS"] == 5
```

- [ ] **Step 2: Write failing PostgreSQL API tests** (append to `backend/tests/test_admin_postgres.py`)

```python
from datetime import timedelta

from core.time_utils import utc_now


def _audit(sessions, **kwargs):
    params = {"action": None, "actor_id": None, "limit": 50, "offset": 0}
    params.update(kwargs)
    with sessions() as db:
        return admin_routes.list_audit(db=db, **params)


def test_audit_listing_filters_and_paginates(database):
    sessions, ids = database
    with sessions() as db:
        actor = db.get(User, ids.admin_id)
        admin_routes.update_user_role(ids.user_id, admin_routes.RoleUpdate(role="admin"), actor, db)
        admin_routes.update_user_role(ids.user_id, admin_routes.RoleUpdate(role="user"), actor, db)
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
    from tests.test_integration import billing as billing_routes
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
```

- [ ] **Step 3: Run to verify failure**

Run: `rtk python -m pytest tests/test_public_config.py -q` and (PostgreSQL) `rtk python -m pytest tests/test_admin_postgres.py -q`
Expected: FAIL — `No module named 'core.public_config'`; `admin_routes` has no `list_audit`; `KeyError: 'feedback'`.

- [ ] **Step 4: Implement the shared reconciliation filter**

`backend/billing/reconciliation.py`:

```python
"""The payment reconciliation worklist predicate, shared by the list and its counters."""
from sqlalchemy import and_, or_

from core.time_utils import utc_now
from models import BillingCheckout


def reconciliation_queue_filter():
    """Checkouts an operator must inspect, including TBC orders whose final callback never arrived."""
    return or_(
        BillingCheckout.status.in_(("provider_unknown", "provider_review")),
        and_(
            BillingCheckout.provider == "tbc",
            BillingCheckout.status.in_(("pending", "expired")),
            BillingCheckout.settled_payment_id.is_(None),
            BillingCheckout.expires_at < utc_now(),
            or_(
                BillingCheckout.provider_status.is_(None),
                BillingCheckout.provider_status.notin_(("Failed", "Expired")),
            ),
        ),
    )
```

In `backend/api/routes/billing.py` add `from billing.reconciliation import reconciliation_queue_filter` and replace the `.filter(or_(...))` argument inside `reconciliation_queue` with `.filter(reconciliation_queue_filter())`. Remove `and_`/`or_` from the sqlalchemy import only if no other code in the file uses them (check with `rtk grep -n "or_(\|and_(" backend/api/routes/billing.py`).

- [ ] **Step 5: Implement the config view**

`backend/core/public_config.py`:

```python
"""Read-only, whitelisted view of runtime configuration for the admin panel."""
from pydantic import SecretStr

from core.config import settings
from core.plans import FREE_DAILY_QUESTIONS

PUBLIC_CONFIG = {
    "app": ("APP_VERSION", "ENVIRONMENT", "DEBUG"),
    "llm": ("LLM_PROVIDER", "LLM_MODEL", "EMBEDDING_MODEL", "RAG_TOP_K", "RAG_MIN_SIMILARITY", "JEV_MODE"),
    "email": ("EMAIL_DELIVERY_ENABLED", "SMTP_HOST", "SMTP_PORT", "SMTP_FROM"),
    "billing": ("BILLING_TBC_ENABLED", "BILLING_CONTACT_EMAIL"),
    "limits": ("RATE_LIMIT_ENABLED",),
}
SECRET_PRESENCE = (
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "SMTP_PASSWORD", "TBC_API_KEY",
    "TBC_CLIENT_ID", "TBC_CLIENT_SECRET", "TYPESAFE_API_KEY",
)


def _is_set(value) -> bool:
    if isinstance(value, SecretStr):
        value = value.get_secret_value()
    return bool(value.strip()) if isinstance(value, str) else value is not None


def public_config(source=settings) -> dict:
    groups = {group: {name: getattr(source, name) for name in names} for group, names in PUBLIC_CONFIG.items()}
    groups["billing"]["FREE_DAILY_QUESTIONS"] = FREE_DAILY_QUESTIONS
    groups["secrets"] = {name: _is_set(getattr(source, name, None)) for name in SECRET_PRESENCE}
    return groups
```

If importing `core.plans` pulls in Redis at import time and breaks the unit test, move `FREE_DAILY_QUESTIONS` lookup inside `public_config` (`from core.plans import FREE_DAILY_QUESTIONS` in the function body) — check by running the test.

- [ ] **Step 6: Implement the admin endpoints**

In `backend/api/routes/admin.py` extend imports:

```python
from datetime import datetime, timedelta
from sqlalchemy import func
from billing.reconciliation import reconciliation_queue_filter
from core.public_config import public_config
from models import AdminAuditLog, BillingCheckout, Feedback, User
```

At the end of `system_stats`, before `return`, compute:

```python
    feedback_new = db.query(func.count(Feedback.id)).filter(Feedback.status == "new").scalar()
    reconciliation_open = db.query(func.count(BillingCheckout.id)).filter(reconciliation_queue_filter()).scalar()
    manual_pending = db.query(func.count(BillingCheckout.id)).filter(
        BillingCheckout.provider == "manual",
        BillingCheckout.status == "pending",
        BillingCheckout.expires_at >= utc_now(),
    ).scalar()
    ingest_stale = last_ingest is None or last_ingest < utc_now() - timedelta(hours=INGEST_STALE_HOURS)
```

and add to the returned dict:

```python
        "feedback": {"new": feedback_new},
        "billing": {"reconciliation_open": reconciliation_open, "manual_pending": manual_pending},
        "attention": {"ingest_stale": ingest_stale},
```

with module constant `INGEST_STALE_HOURS = 36` under the router definition. (The existing `from datetime import timedelta` import becomes `from datetime import datetime, timedelta`.)

Append the new endpoints:

```python
@router.get("/audit")
def list_audit(
    action: Optional[str] = Query(default=None, max_length=64),
    actor_id: Optional[UUID] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(AdminAuditLog, User.username).outerjoin(User, User.id == AdminAuditLog.actor_id)
    if action:
        query = query.filter(AdminAuditLog.action == action)
    if actor_id:
        query = query.filter(AdminAuditLog.actor_id == actor_id)
    total = query.count()
    rows = (query.order_by(AdminAuditLog.created_at.desc(), AdminAuditLog.id.desc())
            .offset(offset).limit(limit).all())
    return {
        "total": total,
        "items": [
            {
                "id": str(entry.id),
                "actor": {"id": str(entry.actor_id), "username": username},
                "action": entry.action,
                "target_type": entry.target_type,
                "target_id": entry.target_id,
                "before": entry.before,
                "after": entry.after,
                "reason": entry.reason,
                "created_at": entry.created_at.isoformat(),
            }
            for entry, username in rows
        ],
    }


@router.get("/config")
def admin_config():
    return public_config()
```

(The spec's `since`/`until` filters are dropped: the Audit page in this stage filters by action only and pages by offset; YAGNI. Remove `datetime` from the import if unused.)

- [ ] **Step 7: Run tests to verify they pass**

Run: `rtk python -m pytest tests/test_public_config.py tests/test_integration.py -q` and (PostgreSQL) `rtk python -m pytest tests/test_admin_postgres.py tests/test_billing_provider_postgres.py tests/test_billing_review_postgres.py -q`
Expected: all pass.

- [ ] **Step 8: Wire into CI and commit**

Add `tests/test_public_config.py` after `tests/test_admin_audit.py` in the "Run current API contracts" list.

```bash
rtk git add backend/billing/reconciliation.py backend/core/public_config.py backend/api/routes/admin.py backend/api/routes/billing.py backend/tests/test_public_config.py backend/tests/test_admin_postgres.py .github/workflows/ci.yml
rtk git commit -m "feat(admin): audit list, attention counters and read-only config API"
```

---

### Task 4: Frontend foundation — styles, copy, components, layout

**Files:**
- Rewrite: `frontend/app/admin/admin.module.css`
- Create: `frontend/lib/admin-i18n.ts`
- Create: `frontend/components/admin/PageHeader.tsx`, `StatTile.tsx`, `Badge.tsx`, `AdminState.tsx`, `Pagination.tsx`, `DataTable.tsx`, `ConfirmDialog.tsx`
- Rewrite: `frontend/app/admin/layout.tsx`
- Create: `frontend/scripts/check-admin-inline-styles.mjs`
- Modify: `frontend/package.json`, `.github/workflows/ci.yml` (frontend job)

**Interfaces:**
- Produces (used by Tasks 5–8):
  - `useAdminCopy(): { lang: Lang; c: AdminCopy; locale: string }`; `formatDateTime(value: string | null, locale: string): string`; `formatDate(...)`; `formatNumber(value: number, locale: string): string`; type `AdminCopy`.
  - `<PageHeader title subtitle? actions? />`
  - `<StatTile label value detail? href? />`
  - `<Badge tone="success"|"warning"|"error"|"neutral">…</Badge>`
  - `<AdminState kind="loading"|"error"|"empty" message? onRetry? />`
  - `<Pagination offset limit total onChange={(offset) => void} />`
  - `<DataTable<T> columns={Column<T>[]} rows={T[]} rowKey={(row) => string} loading? error? onRetry? emptyText? />` with `type Column<T> = { key: string; header: string; render: (row: T) => ReactNode; className?: string }`
  - `<ConfirmDialog open onOpenChange title description confirmLabel withReason? onConfirm={(reason: string) => Promise<void>} />` — shows the thrown `Error.message` inline and stays open on failure.
  - CSS module class names listed in Step 1.

- [ ] **Step 1: Write the inline-style guard (failing first)**

`frontend/scripts/check-admin-inline-styles.mjs`:

```js
#!/usr/bin/env node
// Admin UI styles live in app/admin/admin.module.css. Inline style objects are
// allowed only to pass CSS custom properties (e.g. style={{ '--w': '40%' }}).
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

const roots = ['app/admin', 'components/admin'];
const forbidden = /style=\{\{(?!\s*['"]--)/g;
const failures = [];

function walk(dir) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) walk(path);
    else if (path.endsWith('.tsx')) {
      readFileSync(path, 'utf8').split('\n').forEach((line, index) => {
        if (forbidden.test(line)) failures.push(`${relative('.', path)}:${index + 1}`);
        forbidden.lastIndex = 0;
      });
    }
  }
}

for (const root of roots) {
  try { walk(root); } catch (error) { if (error.code !== 'ENOENT') throw error; }
}
if (failures.length) {
  console.error(`Inline styles are not allowed in the admin UI:\n${failures.join('\n')}`);
  process.exit(1);
}
console.log('Admin UI has no inline style objects.');
```

In `frontend/package.json` `scripts` add: `"check:admin-styles": "node scripts/check-admin-inline-styles.mjs",`

Run (from `frontend/`): `rtk npm run check:admin-styles`
Expected: FAIL listing many `app/admin/...` lines (current pages). It stays red until Task 7; that is intended.

- [ ] **Step 2: Rewrite `frontend/app/admin/admin.module.css`**

```css
/* Admin workspace on the site's tokens (globals.css).
   RootLayout reserves 6rem for SiteHeader, which is hidden on admin routes. */
.frame { margin-top: -6rem; min-height: 100dvh; background: hsl(var(--background)); color: hsl(var(--foreground)); }
.checking { display: grid; place-items: center; margin-top: -6rem; min-height: 100dvh; background: hsl(var(--background)); color: hsl(var(--muted-foreground)); }

/* Shell */
.header { display: flex; align-items: center; justify-content: space-between; gap: 24px; min-height: 72px; padding: 16px 28px; border-bottom: 1px solid hsl(var(--border)); background: hsl(var(--muted)); }
.brand { display: flex; align-items: baseline; flex-wrap: wrap; gap: 8px 16px; }
.brand strong { font-size: 20px; font-weight: 500; }
.brand span, .username { color: hsl(var(--muted-foreground)); font-size: 14px; overflow-wrap: anywhere; }
.workspace { display: flex; min-height: calc(100dvh - 72px); }
.sidebar { width: 240px; flex-shrink: 0; border-right: 1px solid hsl(var(--border)); padding: 20px 12px; }
.sidebar nav { display: flex; flex-direction: column; gap: 4px; }
.sidebar a { display: flex; align-items: center; gap: 12px; min-height: 44px; padding: 12px; border-radius: 12px; font-size: 14px; line-height: 1.4; color: hsl(var(--muted-foreground)); }
.sidebar svg { width: 18px; height: 18px; flex-shrink: 0; }
.sidebar a:hover { color: hsl(var(--foreground)); background: hsl(var(--secondary)); }
.sidebar a[aria-current='page'] { color: hsl(var(--foreground)); background: hsl(var(--primary) / 0.14); box-shadow: inset 3px 0 0 hsl(var(--primary)); font-weight: 500; }
.back { margin-top: 28px; }
.menuButton { display: none; min-height: 44px; align-items: center; gap: 8px; padding: 10px 14px; border: 1px solid hsl(var(--input)); border-radius: 9999px; background: transparent; color: hsl(var(--foreground)); font: inherit; font-size: 14px; }
.content { flex: 1; min-width: 0; padding: 32px; }

/* Page */
.page { display: flex; flex-direction: column; gap: 24px; max-width: 1200px; }
.pageHeader { display: flex; align-items: flex-start; justify-content: space-between; flex-wrap: wrap; gap: 16px; }
.pageHeader h1 { margin: 0; font-size: clamp(1.6rem, 2.8vw, 2.2rem); line-height: 1.2; font-weight: 500; text-wrap: balance; }
.pageHeader p { margin: 8px 0 0; max-width: 65ch; color: hsl(var(--muted-foreground)); line-height: 1.6; }
.panel { position: relative; padding: 20px; border-radius: var(--radius); }
.panelTitle { margin: 0 0 12px; font-size: 14px; font-weight: 500; color: hsl(var(--muted-foreground)); }
.grid2 { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 1fr); gap: 24px; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 16px; }
.tile { display: flex; flex-direction: column; gap: 4px; padding: 20px; border-radius: var(--radius); color: inherit; }
a.tile:hover { box-shadow: inset 0 0 0 1px hsl(var(--primary) / 0.6); }
.tileLabel { font-size: 13px; color: hsl(var(--muted-foreground)); }
.tileValue { font-size: 28px; font-weight: 600; font-variant-numeric: tabular-nums; }
.tileDetail { font-size: 12px; color: hsl(var(--muted-foreground)); overflow-wrap: anywhere; }
.toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }
.muted { color: hsl(var(--muted-foreground)); }
.mono { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 12px; overflow-wrap: anywhere; }
.truncate { display: block; max-width: 480px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.prewrap { white-space: pre-wrap; overflow-wrap: anywhere; }
.notice { font-size: 14px; color: hsl(var(--muted-foreground)); }
.noticeError { color: hsl(var(--error-foreground)); }

/* Controls */
.input, .select, .textarea { box-sizing: border-box; min-height: 44px; padding: 10px 14px; border: 1px solid hsl(var(--input)); border-radius: 12px; background: hsl(var(--secondary)); color: hsl(var(--foreground)); font: inherit; font-size: 14px; max-width: 100%; }
.input { width: 320px; }
.textarea { width: 100%; min-height: 96px; resize: vertical; }
.select option { background: hsl(var(--secondary)); color: hsl(var(--foreground)); }
.button { display: inline-flex; align-items: center; justify-content: center; gap: 8px; min-height: 44px; padding: 10px 18px; border: 1px solid hsl(var(--input)); border-radius: 9999px; background: transparent; color: hsl(var(--foreground)); font: inherit; font-size: 14px; cursor: pointer; }
.button:hover:not(:disabled) { background: hsl(var(--secondary)); }
.buttonPrimary { border-color: hsl(var(--primary)); background: hsl(var(--primary)); color: hsl(var(--primary-foreground)); }
.buttonPrimary:hover:not(:disabled) { background: hsl(var(--primary) / 0.85); }
.button:disabled { opacity: 0.45; cursor: default; }
.chip[aria-pressed='true'] { border-color: hsl(var(--primary)); background: hsl(var(--primary) / 0.14); }
.field { display: flex; flex-direction: column; gap: 8px; font-size: 14px; }
.divider { height: 1px; margin: 20px 0; background: hsl(var(--border)); border: 0; }
.sidebar a:focus-visible, .menuButton:focus-visible, .button:focus-visible, .input:focus-visible, .select:focus-visible, .textarea:focus-visible, a.tile:focus-visible { outline: 2px solid hsl(var(--ring)); outline-offset: 3px; }

/* Badge */
.badge { display: inline-flex; align-items: center; gap: 6px; padding: 2px 10px; border-radius: 9999px; font-size: 12px; line-height: 20px; white-space: nowrap; }
.badge-success { color: hsl(var(--success)); background: hsl(var(--success) / 0.12); }
.badge-warning { color: #fbbf24; background: rgba(217, 119, 6, 0.16); }
.badge-error { color: hsl(var(--error-foreground)); background: hsl(var(--error)); }
.badge-neutral { color: hsl(var(--muted-foreground)); background: hsl(var(--secondary)); }

/* Table */
.tableWrap { overflow-x: auto; border-radius: var(--radius); }
.table { width: 100%; border-collapse: collapse; font-size: 14px; }
.table th { padding: 12px 16px; text-align: left; font-weight: 500; color: hsl(var(--muted-foreground)); border-bottom: 1px solid hsl(var(--border)); white-space: nowrap; }
.table td { padding: 12px 16px; vertical-align: top; border-bottom: 1px solid hsl(var(--border) / 0.6); overflow-wrap: anywhere; }
.table tr:last-child td { border-bottom: 0; }

/* States, pagination, lists */
.state { padding: 32px 16px; text-align: center; color: hsl(var(--muted-foreground)); }
.stateError { color: hsl(var(--error-foreground)); }
.pagination { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; font-size: 13px; color: hsl(var(--muted-foreground)); }
.list { display: flex; flex-direction: column; margin: 0; padding: 0; list-style: none; }
.list li { display: flex; justify-content: space-between; gap: 12px; padding: 12px 0; border-bottom: 1px solid hsl(var(--border) / 0.6); font-size: 14px; }
.list li:last-child { border-bottom: 0; }
.list a { color: hsl(var(--foreground)); text-decoration: underline; text-decoration-color: hsl(var(--primary)); text-underline-offset: 3px; }
.pills { display: flex; flex-wrap: wrap; gap: 8px; }
.log { max-height: 220px; margin: 0; overflow-y: auto; font-size: 12px; line-height: 1.5; white-space: pre-wrap; overflow-wrap: anywhere; color: hsl(var(--muted-foreground)); }

/* Dialog content */
.dialogBody { display: flex; flex-direction: column; gap: 16px; font-size: 14px; line-height: 1.6; }
.dialogActions { display: flex; justify-content: flex-end; flex-wrap: wrap; gap: 12px; }

/* Analytics bars: widths and colours arrive as --w / --c custom properties. */
.legend { display: flex; flex-wrap: wrap; gap: 16px; margin-bottom: 12px; font-size: 13px; color: hsl(var(--muted-foreground)); }
.legend span { display: inline-flex; align-items: center; gap: 6px; }
.swatch { width: 10px; height: 10px; border-radius: 3px; background: var(--c); }
.bars { display: flex; flex-direction: column; gap: 8px; }
.barRow { display: grid; grid-template-columns: 220px minmax(0, 1fr) 120px; align-items: center; gap: 12px; font-size: 14px; }
.barTrack { display: flex; gap: 2px; height: 18px; }
.barSegment { width: var(--w); min-width: 2px; border-radius: 4px; background: var(--c); }
.barMeta { text-align: right; font-size: 13px; color: hsl(var(--muted-foreground)); }

@media (max-width: 1023px) {
  .grid2 { grid-template-columns: minmax(0, 1fr); }
}

@media (max-width: 767px) {
  .header { flex-wrap: wrap; gap: 12px; padding: 16px; }
  .brand { width: 100%; }
  .username { flex: 1; min-width: 0; }
  .menuButton { display: inline-flex; max-width: 100%; }
  .workspace { flex-direction: column; }
  .sidebar { display: none; width: 100%; border-right: 0; border-bottom: 1px solid hsl(var(--border)); padding: 12px 16px; }
  .sidebar[data-open='true'] { display: block; }
  .sidebar nav { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .sidebar a { overflow-wrap: anywhere; }
  .back { margin-top: 12px; }
  .content { padding: 24px 16px; }
  .input { width: 100%; }
  .truncate { max-width: 100%; white-space: normal; }
  /* Tables become label/value cards on phones. */
  .table thead { display: none; }
  .table, .table tbody, .table tr, .table td { display: block; width: 100%; }
  .table tr { padding: 12px 16px; border-bottom: 1px solid hsl(var(--border)); }
  .table tr:last-child { border-bottom: 0; }
  .table td { display: flex; justify-content: space-between; gap: 12px; padding: 6px 0; border: 0; text-align: right; }
  .table td::before { content: attr(data-label); flex-shrink: 0; color: hsl(var(--muted-foreground)); text-align: left; }
  .barRow { grid-template-columns: minmax(0, 1fr); gap: 4px; }
  .barMeta { text-align: left; }
}
```

- [ ] **Step 3: Create `frontend/lib/admin-i18n.ts`**

```ts
'use client';

/**
 * Admin panel copy (ru / ka / en). Language follows the site header via useLang().
 * Payments keep their own dictionary in lib/billing-reconciliation.ts.
 */
import { useLang, type Lang } from './i18n';

export const ADMIN_LOCALE: Record<Lang, string> = { ru: 'ru-RU', ka: 'ka-GE', en: 'en-GB' };

const ru = {
  nav: {
    menu: 'Меню администратора', checking: 'Проверяем доступ…', admin: 'Администрирование', back: 'На сайт',
    dashboard: 'Обзор', documents: 'Документы', analytics: 'Аналитика споров', users: 'Пользователи',
    feedback: 'Обращения', scraper: 'Ингест', audit: 'Журнал действий', config: 'Конфигурация',
  },
  common: {
    loading: 'Загружаем…', loadError: 'Не удалось загрузить данные.', retry: 'Повторить', empty: 'Пока пусто.',
    refresh: 'Обновить', cancel: 'Отмена', confirm: 'Подтвердить', reason: 'Причина (необязательно)',
    reasonHint: 'Попадёт в журнал действий.', saveError: 'Не удалось сохранить изменение.',
    prev: 'Назад', next: 'Вперёд', range: (from: number, to: number, total: string) => `${from}–${to} из ${total}`,
    all: 'Все', dash: '—', yes: 'да', no: 'нет', set: 'задан', notSet: 'не задан',
  },
  dashboard: {
    title: 'Обзор', subtitle: 'Что требует внимания и общее состояние системы.',
    attention: 'Требует внимания', allClear: 'Сейчас ничего не требует вашего внимания.',
    feedbackNew: (n: string) => `Новые обращения: ${n}`,
    reconciliation: (n: string) => `Платежи на сверке: ${n}`,
    manualPending: (n: string) => `Заявки ждут активации: ${n}`,
    ingestStale: 'Ночной ингест не обновлялся больше 36 часов',
    decisionsQueue: (n: string) => `Решения ждут извлечения фактов: ${n}`,
    documents: 'Документов в базе', lastIngest: (d: string) => `последний ингест ${d}`,
    decisions: 'Решения: извлечено фактов', queue: (n: string) => `в очереди ${n}`,
    amendments: 'Поправки: извлечено', amendmentsDetail: (r: string, p: string) => `закон найден: ${r} · в очереди ${p}`,
    users: 'Пользователи', admins: (n: string) => `администраторов: ${n}`,
    subscriptions: 'Активные подписки', noSubscriptions: 'пока нет',
    messages7d: 'Сообщений за 7 дней', conversations: (n: string) => `всего диалогов: ${n}`,
    corpus: 'Корпус по типам', recent: 'Последние действия', openAudit: 'Весь журнал',
  },
  audit: {
    title: 'Журнал действий', subtitle: 'Каждое изменение, сделанное администратором. Записи нельзя изменить или удалить.',
    when: 'Когда', who: 'Кто', action: 'Действие', target: 'Объект', change: 'Изменение', reason: 'Причина',
    actions: {
      'user.role_changed': 'Смена роли', 'subscription.activated': 'Активация подписки',
      'feedback.status_changed': 'Статус обращения',
    } as Record<string, string>,
    targets: { user: 'Пользователь', checkout: 'Заявка', feedback: 'Обращение' } as Record<string, string>,
  },
  config: {
    title: 'Конфигурация', subtitle: 'Текущие настройки сервера, только для чтения.',
    howToChange: 'Значения меняются в /root/infohub/.env на сервере и вступают в силу после деплоя. Секреты здесь не показываются, только признак «задан».',
    groups: { app: 'Приложение', llm: 'Модели и поиск', email: 'Почта', billing: 'Оплата', limits: 'Ограничения', secrets: 'Секреты' } as Record<string, string>,
    name: 'Параметр', value: 'Значение',
  },
  users: {
    title: 'Пользователи', settleTitle: 'Подтвердить заявку клиента после оплаты',
    checkoutPlaceholder: 'UUID заявки из кабинета клиента', settle: 'Подтвердить оплату',
    legacyTitle: 'Резервный режим без заявки (для старых счетов)', emailPlaceholder: 'email клиента',
    months: (n: number) => `${n} мес.`, activate: 'Активировать',
    settled: (email: string, plan: string, until: string) => `Оплата подтверждена: ${email} → ${plan} до ${until}`,
    replayed: (email: string, plan: string, until: string) => `Уже подтверждено: ${email} → ${plan} до ${until}`,
    activated: (email: string, plan: string, until: string) => `Активировано: ${email} → ${plan} до ${until}`,
    login: 'Логин', email: 'Email', role: 'Роль', plan: 'Тариф', until: 'Подписка до', lastLogin: 'Последний вход',
    confirmRole: (user: string, role: string) => `Сменить роль ${user} на «${role}»?`,
    confirmSettle: 'Подтвердить оплату по этой заявке и открыть доступ?',
    confirmActivate: (email: string, plan: string, months: number) => `Активировать ${plan} на ${months} мес. для ${email}?`,
  },
  feedback: {
    title: 'Обращения', date: 'Дата', user: 'Пользователь', page: 'Страница', message: 'Сообщение', status: 'Статус',
    statuses: { new: 'Новое', in_progress: 'В работе', fixed: 'Исправлено' } as Record<string, string>,
    confirmStatus: (status: string) => `Перевести обращение в статус «${status}»?`,
  },
  documents: {
    title: 'Документы', search: 'Поиск по названию или номеру…', allTypes: 'Все типы',
    name: 'Название', type: 'Тип', number: 'Номер', date: 'Дата', authority: 'Орган', notFound: 'Ничего не найдено.',
  },
  scraper: {
    title: 'Ингест и фоновые задачи', lastIngest: 'Последний ингест', today: (n: string) => `сегодня добавлено: ${n}`,
    decisions: 'Решения в очереди на разметку', amendments: 'Поправки в очереди', logEmpty: 'Лог пуст или недоступен.',
    logs: { scraper: 'Ночной скрейпер', law_amendments_backfill: 'Бэкфилл поправок', decision_facts_backfill: 'Бэкфилл решений' } as Record<string, string>,
  },
  analytics: {
    title: 'Аналитика споров', subtitle: 'Исходы налоговых и таможенных споров по решениям из официальной базы.',
    analyzed: 'Решений разобрано', coverage: (p: number, total: string) => `${p}% из ${total} в базе`,
    relief: 'Доля удовлетворённых', reliefDetail: 'жалоба удовлетворена полностью или частично',
    satisfied: 'Удовлетворено полностью', vsRejected: (n: string) => `против ${n} отказов`,
    byYear: 'Исходы по годам', byBody: 'Исходы по органам', topArticles: 'Самые оспариваемые статьи НК',
    article: 'Статья', decisions: 'Решений', split: 'Распределение исходов', reliefRate: 'Доля удовлетворённых',
    outcomes: { satisfied: 'Удовлетворено', partially_satisfied: 'Частично', rejected: 'Отказ' } as Record<string, string>,
    bodies: {
      revenue_service_council: 'Совет по спорам Службы доходов', mof_dispute_council: 'Совет по спорам Минфина',
      city_court: 'Городской суд', appeals_court: 'Апелляционный суд', supreme_court: 'Верховный суд', other: 'Другое',
    } as Record<string, string>,
    reliefShort: 'удовл.',
  },
};

export type AdminCopy = typeof ru;

const ka: AdminCopy = {
  nav: {
    menu: 'ადმინისტრატორის მენიუ', checking: 'წვდომა მოწმდება…', admin: 'ადმინისტრირება', back: 'საიტზე დაბრუნება',
    dashboard: 'მიმოხილვა', documents: 'დოკუმენტები', analytics: 'დავების ანალიტიკა', users: 'მომხმარებლები',
    feedback: 'მიმართვები', scraper: 'მონაცემების შეგროვება', audit: 'მოქმედებების ჟურნალი', config: 'კონფიგურაცია',
  },
  common: {
    loading: 'იტვირთება…', loadError: 'მონაცემები ვერ ჩაიტვირთა.', retry: 'ხელახლა ცდა', empty: 'ჯერ ცარიელია.',
    refresh: 'განახლება', cancel: 'გაუქმება', confirm: 'დადასტურება', reason: 'მიზეზი (არასავალდებულო)',
    reasonHint: 'ჩაიწერება მოქმედებების ჟურნალში.', saveError: 'ცვლილება ვერ შეინახა.',
    prev: 'უკან', next: 'შემდეგი', range: (from: number, to: number, total: string) => `${from}–${to} / ${total}`,
    all: 'ყველა', dash: '—', yes: 'კი', no: 'არა', set: 'მითითებულია', notSet: 'არ არის მითითებული',
  },
  dashboard: {
    title: 'მიმოხილვა', subtitle: 'რას სჭირდება ყურადღება და სისტემის ზოგადი მდგომარეობა.',
    attention: 'საჭიროებს ყურადღებას', allClear: 'ამჟამად თქვენს ყურადღებას არაფერი საჭიროებს.',
    feedbackNew: (n: string) => `ახალი მიმართვები: ${n}`,
    reconciliation: (n: string) => `შესამოწმებელი გადახდები: ${n}`,
    manualPending: (n: string) => `გააქტიურების მომლოდინე განაცხადები: ${n}`,
    ingestStale: 'ღამის შეგროვება 36 საათზე მეტია არ განახლებულა',
    decisionsQueue: (n: string) => `ფაქტების ამოღების მომლოდინე გადაწყვეტილებები: ${n}`,
    documents: 'დოკუმენტები ბაზაში', lastIngest: (d: string) => `ბოლო შეგროვება ${d}`,
    decisions: 'გადაწყვეტილებები: ამოღებული ფაქტები', queue: (n: string) => `რიგშია ${n}`,
    amendments: 'ცვლილებები: დამუშავებული', amendmentsDetail: (r: string, p: string) => `კანონი ნაპოვნია: ${r} · რიგშია ${p}`,
    users: 'მომხმარებლები', admins: (n: string) => `ადმინისტრატორები: ${n}`,
    subscriptions: 'აქტიური გამოწერები', noSubscriptions: 'ჯერ არ არის',
    messages7d: 'შეტყობინებები 7 დღეში', conversations: (n: string) => `სულ დიალოგები: ${n}`,
    corpus: 'კორპუსი ტიპების მიხედვით', recent: 'ბოლო მოქმედებები', openAudit: 'მთელი ჟურნალი',
  },
  audit: {
    title: 'მოქმედებების ჟურნალი', subtitle: 'ადმინისტრატორის ყველა ცვლილება. ჩანაწერის შეცვლა ან წაშლა შეუძლებელია.',
    when: 'როდის', who: 'ვინ', action: 'მოქმედება', target: 'ობიექტი', change: 'ცვლილება', reason: 'მიზეზი',
    actions: {
      'user.role_changed': 'როლის შეცვლა', 'subscription.activated': 'გამოწერის გააქტიურება',
      'feedback.status_changed': 'მიმართვის სტატუსი',
    },
    targets: { user: 'მომხმარებელი', checkout: 'განაცხადი', feedback: 'მიმართვა' },
  },
  config: {
    title: 'კონფიგურაცია', subtitle: 'სერვერის მიმდინარე პარამეტრები, მხოლოდ სანახავად.',
    howToChange: 'მნიშვნელობები იცვლება სერვერზე, ფაილში /root/infohub/.env, და ძალაში შედის დეპლოის შემდეგ. საიდუმლო მნიშვნელობები აქ არ ჩანს, მხოლოდ ის, მითითებულია თუ არა.',
    groups: { app: 'აპლიკაცია', llm: 'მოდელები და ძიება', email: 'ფოსტა', billing: 'გადახდა', limits: 'შეზღუდვები', secrets: 'საიდუმლოები' },
    name: 'პარამეტრი', value: 'მნიშვნელობა',
  },
  users: {
    title: 'მომხმარებლები', settleTitle: 'კლიენტის განაცხადის დადასტურება გადახდის შემდეგ',
    checkoutPlaceholder: 'განაცხადის UUID კლიენტის კაბინეტიდან', settle: 'გადახდის დადასტურება',
    legacyTitle: 'სარეზერვო რეჟიმი განაცხადის გარეშე (ძველი ანგარიშებისთვის)', emailPlaceholder: 'კლიენტის ელფოსტა',
    months: (n: number) => `${n} თვე`, activate: 'გააქტიურება',
    settled: (email: string, plan: string, until: string) => `გადახდა დადასტურდა: ${email} → ${plan}, ${until}-მდე`,
    replayed: (email: string, plan: string, until: string) => `უკვე დადასტურებულია: ${email} → ${plan}, ${until}-მდე`,
    activated: (email: string, plan: string, until: string) => `გააქტიურდა: ${email} → ${plan}, ${until}-მდე`,
    login: 'მომხმარებლის სახელი', email: 'ელფოსტა', role: 'როლი', plan: 'ტარიფი', until: 'გამოწერა მოქმედებს', lastLogin: 'ბოლო შესვლა',
    confirmRole: (user: string, role: string) => `შეიცვალოს ${user}-ის როლი „${role}“-ით?`,
    confirmSettle: 'დადასტურდეს ამ განაცხადის გადახდა და გაიხსნას წვდომა?',
    confirmActivate: (email: string, plan: string, months: number) => `გააქტიურდეს ${plan} ${months} თვით ${email}-ისთვის?`,
  },
  feedback: {
    title: 'მიმართვები', date: 'თარიღი', user: 'მომხმარებელი', page: 'გვერდი', message: 'შეტყობინება', status: 'სტატუსი',
    statuses: { new: 'ახალი', in_progress: 'მუშავდება', fixed: 'გამოსწორებულია' },
    confirmStatus: (status: string) => `მიენიჭოს მიმართვას სტატუსი „${status}“?`,
  },
  documents: {
    title: 'დოკუმენტები', search: 'ძიება სათაურით ან ნომრით…', allTypes: 'ყველა ტიპი',
    name: 'სათაური', type: 'ტიპი', number: 'ნომერი', date: 'თარიღი', authority: 'ორგანო', notFound: 'ვერაფერი მოიძებნა.',
  },
  scraper: {
    title: 'შეგროვება და ფონური ამოცანები', lastIngest: 'ბოლო შეგროვება', today: (n: string) => `დღეს დაემატა: ${n}`,
    decisions: 'დასამუშავებელი გადაწყვეტილებები', amendments: 'დასამუშავებელი ცვლილებები', logEmpty: 'ჟურნალი ცარიელია ან მიუწვდომელია.',
    logs: { scraper: 'ღამის შეგროვება', law_amendments_backfill: 'ცვლილებების დამუშავება', decision_facts_backfill: 'გადაწყვეტილებების დამუშავება' },
  },
  analytics: {
    title: 'დავების ანალიტიკა', subtitle: 'საგადასახადო და საბაჟო დავების შედეგები ოფიციალური ბაზის გადაწყვეტილებების მიხედვით.',
    analyzed: 'გაანალიზებული გადაწყვეტილებები', coverage: (p: number, total: string) => `${p}% ბაზაში არსებული ${total}-დან`,
    relief: 'დაკმაყოფილების წილი', reliefDetail: 'საჩივარი დაკმაყოფილდა სრულად ან ნაწილობრივ',
    satisfied: 'სრულად დაკმაყოფილდა', vsRejected: (n: string) => `${n} უარის წინააღმდეგ`,
    byYear: 'შედეგები წლების მიხედვით', byBody: 'შედეგები ორგანოების მიხედვით', topArticles: 'საგადასახადო კოდექსის ყველაზე სადავო მუხლები',
    article: 'მუხლი', decisions: 'გადაწყვეტილებები', split: 'შედეგების განაწილება', reliefRate: 'დაკმაყოფილების წილი',
    outcomes: { satisfied: 'დაკმაყოფილდა', partially_satisfied: 'ნაწილობრივ', rejected: 'უარი' },
    bodies: {
      revenue_service_council: 'შემოსავლების სამსახურის დავების საბჭო', mof_dispute_council: 'ფინანსთა სამინისტროს დავების საბჭო',
      city_court: 'საქალაქო სასამართლო', appeals_court: 'სააპელაციო სასამართლო', supreme_court: 'უზენაესი სასამართლო', other: 'სხვა',
    },
    reliefShort: 'დაკმ.',
  },
};

const en: AdminCopy = {
  nav: {
    menu: 'Administrator menu', checking: 'Checking access…', admin: 'Administration', back: 'Back to site',
    dashboard: 'Overview', documents: 'Documents', analytics: 'Dispute analytics', users: 'Users',
    feedback: 'Feedback', scraper: 'Ingest', audit: 'Action log', config: 'Configuration',
  },
  common: {
    loading: 'Loading…', loadError: 'Could not load the data.', retry: 'Retry', empty: 'Nothing here yet.',
    refresh: 'Refresh', cancel: 'Cancel', confirm: 'Confirm', reason: 'Reason (optional)',
    reasonHint: 'Saved to the action log.', saveError: 'Could not save the change.',
    prev: 'Previous', next: 'Next', range: (from: number, to: number, total: string) => `${from}–${to} of ${total}`,
    all: 'All', dash: '—', yes: 'yes', no: 'no', set: 'set', notSet: 'not set',
  },
  dashboard: {
    title: 'Overview', subtitle: 'What needs attention and the overall state of the system.',
    attention: 'Needs attention', allClear: 'Nothing needs your attention right now.',
    feedbackNew: (n: string) => `New feedback: ${n}`,
    reconciliation: (n: string) => `Payments to reconcile: ${n}`,
    manualPending: (n: string) => `Orders awaiting activation: ${n}`,
    ingestStale: 'The nightly ingest has not run for more than 36 hours',
    decisionsQueue: (n: string) => `Decisions awaiting fact extraction: ${n}`,
    documents: 'Documents in the corpus', lastIngest: (d: string) => `last ingest ${d}`,
    decisions: 'Decisions: facts extracted', queue: (n: string) => `${n} queued`,
    amendments: 'Amendments: extracted', amendmentsDetail: (r: string, p: string) => `law resolved: ${r} · ${p} queued`,
    users: 'Users', admins: (n: string) => `administrators: ${n}`,
    subscriptions: 'Active subscriptions', noSubscriptions: 'none yet',
    messages7d: 'Messages in 7 days', conversations: (n: string) => `conversations in total: ${n}`,
    corpus: 'Corpus by type', recent: 'Recent actions', openAudit: 'Full log',
  },
  audit: {
    title: 'Action log', subtitle: 'Every change made by an administrator. Entries cannot be edited or deleted.',
    when: 'When', who: 'Who', action: 'Action', target: 'Target', change: 'Change', reason: 'Reason',
    actions: {
      'user.role_changed': 'Role change', 'subscription.activated': 'Subscription activation',
      'feedback.status_changed': 'Feedback status',
    },
    targets: { user: 'User', checkout: 'Order', feedback: 'Feedback' },
  },
  config: {
    title: 'Configuration', subtitle: 'Current server settings, read-only.',
    howToChange: 'Values are changed in /root/infohub/.env on the server and take effect after a deploy. Secrets are never shown here, only whether they are set.',
    groups: { app: 'Application', llm: 'Models and retrieval', email: 'Email', billing: 'Billing', limits: 'Limits', secrets: 'Secrets' },
    name: 'Setting', value: 'Value',
  },
  users: {
    title: 'Users', settleTitle: 'Confirm a customer order after payment',
    checkoutPlaceholder: 'Order UUID from the customer account', settle: 'Confirm payment',
    legacyTitle: 'Fallback without an order (legacy invoices)', emailPlaceholder: 'customer email',
    months: (n: number) => `${n} mo`, activate: 'Activate',
    settled: (email: string, plan: string, until: string) => `Payment confirmed: ${email} → ${plan} until ${until}`,
    replayed: (email: string, plan: string, until: string) => `Already confirmed: ${email} → ${plan} until ${until}`,
    activated: (email: string, plan: string, until: string) => `Activated: ${email} → ${plan} until ${until}`,
    login: 'Username', email: 'Email', role: 'Role', plan: 'Plan', until: 'Subscription until', lastLogin: 'Last login',
    confirmRole: (user: string, role: string) => `Change ${user}'s role to “${role}”?`,
    confirmSettle: 'Confirm payment for this order and grant access?',
    confirmActivate: (email: string, plan: string, months: number) => `Activate ${plan} for ${months} mo for ${email}?`,
  },
  feedback: {
    title: 'Feedback', date: 'Date', user: 'User', page: 'Page', message: 'Message', status: 'Status',
    statuses: { new: 'New', in_progress: 'In progress', fixed: 'Fixed' },
    confirmStatus: (status: string) => `Set this report to “${status}”?`,
  },
  documents: {
    title: 'Documents', search: 'Search by title or number…', allTypes: 'All types',
    name: 'Title', type: 'Type', number: 'Number', date: 'Date', authority: 'Authority', notFound: 'Nothing found.',
  },
  scraper: {
    title: 'Ingest and background jobs', lastIngest: 'Last ingest', today: (n: string) => `added today: ${n}`,
    decisions: 'Decisions awaiting extraction', amendments: 'Amendments awaiting extraction', logEmpty: 'Log is empty or unavailable.',
    logs: { scraper: 'Nightly scraper', law_amendments_backfill: 'Amendments backfill', decision_facts_backfill: 'Decision facts backfill' },
  },
  analytics: {
    title: 'Dispute analytics', subtitle: 'Outcomes of tax and customs dispute decisions from the official corpus.',
    analyzed: 'Decisions analysed', coverage: (p: number, total: string) => `${p}% of ${total} in the corpus`,
    relief: 'Taxpayer relief rate', reliefDetail: 'complaint satisfied fully or partially',
    satisfied: 'Fully satisfied', vsRejected: (n: string) => `vs ${n} rejected`,
    byYear: 'Outcomes by year', byBody: 'Outcomes by deciding body', topArticles: 'Most contested Tax Code articles',
    article: 'Article', decisions: 'Decisions', split: 'Outcome split', reliefRate: 'Relief rate',
    outcomes: { satisfied: 'Satisfied', partially_satisfied: 'Partially', rejected: 'Rejected' },
    bodies: {
      revenue_service_council: 'Revenue Service dispute council', mof_dispute_council: 'MoF dispute council',
      city_court: 'City court', appeals_court: 'Appeals court', supreme_court: 'Supreme court', other: 'Other',
    },
    reliefShort: 'relief',
  },
};

const COPY: Record<Lang, AdminCopy> = { ru, ka, en };

export function useAdminCopy(): { lang: Lang; c: AdminCopy; locale: string } {
  const lang = useLang();
  return { lang, c: COPY[lang], locale: ADMIN_LOCALE[lang] };
}

/** Backend timestamps are naive UTC ISO strings; treat them as UTC. */
function parseUtc(value: string): Date {
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(value) ? value : `${value}Z`);
}

export function formatDateTime(value: string | null, locale: string): string {
  return value ? parseUtc(value).toLocaleString(locale, { dateStyle: 'short', timeStyle: 'short' }) : '—';
}

export function formatDate(value: string | null, locale: string): string {
  return value ? parseUtc(value).toLocaleDateString(locale) : '—';
}

export function formatNumber(value: number, locale: string): string {
  return value.toLocaleString(locale);
}
```

- [ ] **Step 4: Create the components**

`frontend/components/admin/PageHeader.tsx`:

```tsx
import type { ReactNode } from 'react';
import styles from '@/app/admin/admin.module.css';

export function PageHeader({ title, subtitle, actions }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode }) {
  return <div className={styles.pageHeader}>
    <div>
      <h1>{title}</h1>
      {subtitle && <p>{subtitle}</p>}
    </div>
    {actions && <div className={styles.toolbar}>{actions}</div>}
  </div>;
}
```

`frontend/components/admin/StatTile.tsx`:

```tsx
import Link from 'next/link';
import styles from '@/app/admin/admin.module.css';

export function StatTile({ label, value, detail, href }: { label: string; value: string; detail?: string; href?: string }) {
  const body = <>
    <span className={styles.tileLabel}>{label}</span>
    <span className={styles.tileValue}>{value}</span>
    {detail && <span className={styles.tileDetail}>{detail}</span>}
  </>;
  const className = `liquid-glass ${styles.tile}`;
  return href ? <Link href={href} className={className}>{body}</Link> : <div className={className}>{body}</div>;
}
```

`frontend/components/admin/Badge.tsx`:

```tsx
import type { ReactNode } from 'react';
import styles from '@/app/admin/admin.module.css';

export type BadgeTone = 'success' | 'warning' | 'error' | 'neutral';

export function Badge({ tone, children }: { tone: BadgeTone; children: ReactNode }) {
  return <span className={`${styles.badge} ${styles[`badge-${tone}`]}`}>{children}</span>;
}
```

`frontend/components/admin/AdminState.tsx`:

```tsx
'use client';

import styles from '@/app/admin/admin.module.css';
import { useAdminCopy } from '@/lib/admin-i18n';

export function AdminState({ kind, message, onRetry }: { kind: 'loading' | 'error' | 'empty'; message?: string; onRetry?: () => void }) {
  const { c } = useAdminCopy();
  const text = message ?? (kind === 'loading' ? c.common.loading : kind === 'error' ? c.common.loadError : c.common.empty);
  return <div className={`${styles.state} ${kind === 'error' ? styles.stateError : ''}`}
    role={kind === 'error' ? 'alert' : 'status'}>
    <p>{text}</p>
    {kind === 'error' && onRetry && <button type="button" className={styles.button} onClick={onRetry}>{c.common.retry}</button>}
  </div>;
}
```

`frontend/components/admin/Pagination.tsx`:

```tsx
'use client';

import styles from '@/app/admin/admin.module.css';
import { formatNumber, useAdminCopy } from '@/lib/admin-i18n';

export function Pagination({ offset, limit, total, onChange }: { offset: number; limit: number; total: number; onChange: (offset: number) => void }) {
  const { c, locale } = useAdminCopy();
  if (total <= limit && offset === 0) return null;
  const to = Math.min(offset + limit, total);
  return <div className={styles.pagination}>
    <span>{c.common.range(total ? offset + 1 : 0, to, formatNumber(total, locale))}</span>
    <div className={styles.toolbar}>
      <button type="button" className={styles.button} disabled={offset === 0}
        onClick={() => onChange(Math.max(offset - limit, 0))}>{c.common.prev}</button>
      <button type="button" className={styles.button} disabled={to >= total}
        onClick={() => onChange(offset + limit)}>{c.common.next}</button>
    </div>
  </div>;
}
```

`frontend/components/admin/DataTable.tsx`:

```tsx
'use client';

import type { ReactNode } from 'react';
import styles from '@/app/admin/admin.module.css';
import { AdminState } from './AdminState';

export type Column<T> = { key: string; header: string; render: (row: T) => ReactNode; className?: string };

export function DataTable<T>({ columns, rows, rowKey, loading, error, onRetry, emptyText }: {
  columns: Column<T>[]; rows: T[]; rowKey: (row: T) => string;
  loading?: boolean; error?: boolean; onRetry?: () => void; emptyText?: string;
}) {
  if (error) return <div className={`liquid-glass ${styles.panel}`}><AdminState kind="error" onRetry={onRetry} /></div>;
  if (loading && rows.length === 0) return <div className={`liquid-glass ${styles.panel}`}><AdminState kind="loading" /></div>;
  if (rows.length === 0) return <div className={`liquid-glass ${styles.panel}`}><AdminState kind="empty" message={emptyText} /></div>;
  return <div className={`liquid-glass ${styles.tableWrap}`}>
    <table className={styles.table} aria-busy={loading || undefined}>
      <thead><tr>{columns.map((col) => <th key={col.key} scope="col">{col.header}</th>)}</tr></thead>
      <tbody>
        {rows.map((row) => <tr key={rowKey(row)}>
          {columns.map((col) => <td key={col.key} data-label={col.header} className={col.className}>{col.render(row)}</td>)}
        </tr>)}
      </tbody>
    </table>
  </div>;
}
```

`frontend/components/admin/ConfirmDialog.tsx`:

```tsx
'use client';

import { useState } from 'react';
import { GlassDialog } from '@/components/ui/Dialog';
import styles from '@/app/admin/admin.module.css';
import { useAdminCopy } from '@/lib/admin-i18n';

export function ConfirmDialog({ open, onOpenChange, title, description, confirmLabel, withReason = true, onConfirm }: {
  open: boolean; onOpenChange: (open: boolean) => void; title: string; description?: string;
  confirmLabel?: string; withReason?: boolean; onConfirm: (reason: string) => Promise<void>;
}) {
  const { c } = useAdminCopy();
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const change = (next: boolean) => {
    if (busy) return;
    if (!next) { setReason(''); setError(null); }
    onOpenChange(next);
  };

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await onConfirm(reason.trim());
      setReason('');
      onOpenChange(false);
    } catch (e) {
      setError(e instanceof Error && e.message ? e.message : c.common.saveError);
    } finally {
      setBusy(false);
    }
  };

  return <GlassDialog open={open} onOpenChange={change} title={title} closeLabel={c.common.cancel}>
    <div className={styles.dialogBody}>
      {description && <p>{description}</p>}
      {withReason && <label className={styles.field}>
        {c.common.reason}
        <textarea className={styles.textarea} maxLength={1000} value={reason}
          onChange={(e) => setReason(e.target.value)} />
        <span className={styles.muted}>{c.common.reasonHint}</span>
      </label>}
      {error && <p className={styles.noticeError} role="alert">{error}</p>}
      <div className={styles.dialogActions}>
        <button type="button" className={styles.button} onClick={() => change(false)} disabled={busy}>{c.common.cancel}</button>
        <button type="button" className={`${styles.button} ${styles.buttonPrimary}`} onClick={submit} disabled={busy}>
          {confirmLabel ?? c.common.confirm}
        </button>
      </div>
    </div>
  </GlassDialog>;
}
```

- [ ] **Step 5: Rewrite `frontend/app/admin/layout.tsx`**

```tsx
'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { authFetch } from '@/lib/auth';
import { useAdminCopy } from '@/lib/admin-i18n';
import { reconciliationCopy } from '@/lib/billing-reconciliation';
import {
  DashboardIcon, FileTextIcon, PersonIcon, ActivityLogIcon, BarChartIcon, ChatBubbleIcon,
  GearIcon, ExitIcon, HamburgerMenuIcon, CardStackIcon, ReaderIcon,
} from '@radix-ui/react-icons';
import styles from './admin.module.css';

const navigation = [
  { key: 'dashboard', href: '/admin', icon: DashboardIcon },
  { key: 'users', href: '/admin/users', icon: PersonIcon },
  { key: 'payments', href: '/admin/billing', icon: CardStackIcon },
  { key: 'feedback', href: '/admin/feedback', icon: ChatBubbleIcon },
  { key: 'documents', href: '/admin/documents', icon: FileTextIcon },
  { key: 'analytics', href: '/admin/analytics', icon: BarChartIcon },
  { key: 'scraper', href: '/admin/scraper', icon: ActivityLogIcon },
  { key: 'audit', href: '/admin/audit', icon: ReaderIcon },
  { key: 'config', href: '/admin/settings', icon: GearIcon },
] as const;

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { lang, c } = useAdminCopy();
  const [openPath, setOpenPath] = useState<string | null>(null);
  const [admin, setAdmin] = useState<{ username: string } | null>(null);
  const menuOpen = openPath === pathname;

  useEffect(() => {
    const controller = new AbortController();
    authFetch('/api/v1/auth/me', { signal: controller.signal, cache: 'no-store' })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((me) => {
        if (controller.signal.aborted) return;
        if (me.role === 'admin') setAdmin({ username: me.username });
        else router.replace('/login');
      })
      .catch(() => { if (!controller.signal.aborted) router.replace('/login'); });
    return () => controller.abort();
  }, [router]);

  if (!admin) return <div className={styles.checking} role="status">{c.nav.checking}</div>;

  return <div className={styles.frame}>
    <header className={styles.header}>
      <div className={styles.brand}><strong>Tax Advisor</strong><span>{c.nav.admin}</span></div>
      <span className={styles.username}>{admin.username}</span>
      <button type="button" className={styles.menuButton} aria-expanded={menuOpen} aria-controls="admin-navigation"
        onClick={() => setOpenPath(menuOpen ? null : pathname)}>
        <HamburgerMenuIcon aria-hidden="true" />{c.nav.menu}
      </button>
    </header>
    <div className={styles.workspace}>
      <aside id="admin-navigation" className={styles.sidebar} data-open={menuOpen}>
        <nav aria-label={c.nav.menu}>
          {navigation.map((item) => {
            const active = pathname === item.href || (item.href !== '/admin' && pathname.startsWith(`${item.href}/`));
            const Icon = item.icon;
            const label = item.key === 'payments' ? reconciliationCopy[lang].title : c.nav[item.key];
            return <Link key={item.href} href={item.href} aria-current={active ? 'page' : undefined}
              onClick={() => setOpenPath(null)}>
              <Icon aria-hidden="true" />{label}
            </Link>;
          })}
        </nav>
        <Link href="/" className={styles.back}><ExitIcon aria-hidden="true" />{c.nav.back}</Link>
      </aside>
      <main className={styles.content}>{children}</main>
    </div>
  </div>;
}
```

- [ ] **Step 6: Review Georgian copy**

Invoke the `georgian-writing-style` skill on the `ka` object in `lib/admin-i18n.ts`; apply its corrections in place (keep keys and function signatures).

- [ ] **Step 7: Typecheck and lint**

Run (from `frontend/`): `rtk npm run type-check && rtk npm run lint`
Expected: both pass (`check:admin-styles` still fails — expected until Task 7).

- [ ] **Step 8: Add the guard to CI and commit**

In `.github/workflows/ci.yml` frontend job, after `- run: npm run lint` add `- run: npm run check:admin-styles`. (CI goes green only after Task 7; do not push before Task 7.)

```bash
rtk git add frontend/app/admin/admin.module.css frontend/lib/admin-i18n.ts frontend/components/admin frontend/app/admin/layout.tsx frontend/scripts/check-admin-inline-styles.mjs frontend/package.json .github/workflows/ci.yml
rtk git commit -m "feat(admin): shared admin styles, RU/KA/EN copy and component kit"
```

---

### Task 5: Dashboard, Audit and Config pages

**Files:**
- Rewrite: `frontend/app/admin/page.tsx`
- Create: `frontend/app/admin/audit/page.tsx`
- Rewrite: `frontend/app/admin/settings/page.tsx`

**Interfaces:**
- Consumes: Task 3 HTTP contracts; Task 4 components and `useAdminCopy`, `formatDateTime`, `formatNumber`.
- Produces: `AuditEntry` type exported from `frontend/app/admin/audit/page.tsx` is NOT exported (pages may only export default); instead define it in `frontend/lib/admin-types.ts`:

```ts
export interface AuditEntry {
  id: string;
  actor: { id: string; username: string | null };
  action: string;
  target_type: string;
  target_id: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  reason: string | null;
  created_at: string;
}

export interface AuditPage { total: number; items: AuditEntry[] }

export interface AdminStats {
  documents: { total: number; by_type: Record<string, number>; last_ingest: string | null };
  decisions: { total: number; extracted: number; pending: number };
  amendments: { acts_total: number; extracted: number; resolved: number; pending: number };
  users: { total: number; admins: number };
  subscriptions: Record<string, number>;
  conversations: { total: number; messages: number; messages_7d: number };
  feedback: { new: number };
  billing: { reconciliation_open: number; manual_pending: number };
  attention: { ingest_stale: boolean };
}

export type AdminConfig = Record<string, Record<string, string | number | boolean | null>>;

/** "role: user → admin" style summary of an audit entry's change. */
export function summarizeChange(entry: AuditEntry): string {
  const keys = new Set([...Object.keys(entry.before ?? {}), ...Object.keys(entry.after ?? {})]);
  return [...keys].map((key) => {
    const from = entry.before?.[key];
    const to = entry.after?.[key];
    return `${key}: ${from == null ? '—' : String(from)} → ${to == null ? '—' : String(to)}`;
  }).join('; ');
}
```

(Add `frontend/lib/admin-types.ts` to this task's files.)

- [ ] **Step 1: Create `frontend/lib/admin-types.ts`** with the code above.

- [ ] **Step 2: Rewrite `frontend/app/admin/page.tsx`**

```tsx
'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { authFetch } from '@/lib/auth';
import { formatDateTime, formatNumber, useAdminCopy } from '@/lib/admin-i18n';
import { summarizeChange, type AdminStats, type AuditPage } from '@/lib/admin-types';
import { PageHeader } from '@/components/admin/PageHeader';
import { StatTile } from '@/components/admin/StatTile';
import { AdminState } from '@/components/admin/AdminState';
import styles from './admin.module.css';

export default function AdminDashboard() {
  const { c, locale } = useAdminCopy();
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [statsError, setStatsError] = useState(false);
  const [audit, setAudit] = useState<AuditPage | null>(null);
  const [auditError, setAuditError] = useState(false);

  const loadStats = useCallback(() => {
    setStatsError(false);
    authFetch('/api/v1/admin/stats').then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setStats).catch(() => setStatsError(true));
  }, []);
  const loadAudit = useCallback(() => {
    setAuditError(false);
    authFetch('/api/v1/admin/audit?limit=5').then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setAudit).catch(() => setAuditError(true));
  }, []);
  useEffect(() => { loadStats(); loadAudit(); }, [loadStats, loadAudit]);

  const n = (value: number) => formatNumber(value, locale);
  const attention = stats ? [
    stats.feedback.new > 0 && { href: '/admin/feedback', text: c.dashboard.feedbackNew(n(stats.feedback.new)) },
    stats.billing.reconciliation_open > 0 && { href: '/admin/billing', text: c.dashboard.reconciliation(n(stats.billing.reconciliation_open)) },
    stats.billing.manual_pending > 0 && { href: '/admin/users', text: c.dashboard.manualPending(n(stats.billing.manual_pending)) },
    stats.attention.ingest_stale && { href: '/admin/scraper', text: c.dashboard.ingestStale },
    stats.decisions.pending > 0 && { href: '/admin/scraper', text: c.dashboard.decisionsQueue(n(stats.decisions.pending)) },
  ].filter((item): item is { href: string; text: string } => Boolean(item)) : [];
  const subsTotal = stats ? Object.values(stats.subscriptions).reduce((a, b) => a + b, 0) : 0;

  return <div className={styles.page}>
    <PageHeader title={c.dashboard.title} subtitle={c.dashboard.subtitle} />

    <section className={`liquid-glass ${styles.panel}`} aria-labelledby="attention-title">
      <h2 id="attention-title" className={styles.panelTitle}>{c.dashboard.attention}</h2>
      {statsError ? <AdminState kind="error" onRetry={loadStats} />
        : !stats ? <AdminState kind="loading" />
        : attention.length === 0 ? <p className={styles.notice}>{c.dashboard.allClear}</p>
        : <ul className={styles.list}>{attention.map((item) => <li key={item.text}><Link href={item.href}>{item.text}</Link></li>)}</ul>}
    </section>

    {stats && <div className={styles.tiles}>
      <StatTile label={c.dashboard.documents} value={n(stats.documents.total)}
        detail={stats.documents.last_ingest ? c.dashboard.lastIngest(formatDateTime(stats.documents.last_ingest, locale)) : undefined} />
      <StatTile label={c.dashboard.decisions} value={`${n(stats.decisions.extracted)} / ${n(stats.decisions.total)}`}
        detail={c.dashboard.queue(n(stats.decisions.pending))} />
      <StatTile label={c.dashboard.amendments} value={`${n(stats.amendments.extracted)} / ${n(stats.amendments.acts_total)}`}
        detail={c.dashboard.amendmentsDetail(n(stats.amendments.resolved), n(stats.amendments.pending))} />
      <StatTile label={c.dashboard.users} value={n(stats.users.total)} detail={c.dashboard.admins(n(stats.users.admins))} href="/admin/users" />
      <StatTile label={c.dashboard.subscriptions} value={n(subsTotal)}
        detail={Object.entries(stats.subscriptions).map(([p, v]) => `${p}: ${n(v)}`).join(' · ') || c.dashboard.noSubscriptions} />
      <StatTile label={c.dashboard.messages7d} value={n(stats.conversations.messages_7d)}
        detail={c.dashboard.conversations(n(stats.conversations.total))} />
    </div>}

    <div className={styles.grid2}>
      {stats && <section className={`liquid-glass ${styles.panel}`} aria-labelledby="corpus-title">
        <h2 id="corpus-title" className={styles.panelTitle}>{c.dashboard.corpus}</h2>
        <div className={styles.pills}>
          {Object.entries(stats.documents.by_type).map(([type, count]) =>
            <span key={type} className={`${styles.badge} ${styles['badge-neutral']}`}>{type}: {n(count)}</span>)}
        </div>
      </section>}
      <section className={`liquid-glass ${styles.panel}`} aria-labelledby="recent-title">
        <h2 id="recent-title" className={styles.panelTitle}>{c.dashboard.recent}</h2>
        {auditError ? <AdminState kind="error" onRetry={loadAudit} />
          : !audit ? <AdminState kind="loading" />
          : audit.items.length === 0 ? <AdminState kind="empty" />
          : <ul className={styles.list}>{audit.items.map((entry) => <li key={entry.id}>
            <span>{c.audit.actions[entry.action] ?? entry.action}<br /><span className={styles.muted}>{summarizeChange(entry)}</span></span>
            <span className={styles.muted}>{formatDateTime(entry.created_at, locale)}</span>
          </li>)}</ul>}
        <p className={styles.notice}><Link href="/admin/audit">{c.dashboard.openAudit}</Link></p>
      </section>
    </div>
  </div>;
}
```

- [ ] **Step 3: Create `frontend/app/admin/audit/page.tsx`**

```tsx
'use client';

import { useCallback, useEffect, useState } from 'react';
import { authFetch } from '@/lib/auth';
import { formatDateTime, useAdminCopy } from '@/lib/admin-i18n';
import { summarizeChange, type AuditEntry, type AuditPage } from '@/lib/admin-types';
import { PageHeader } from '@/components/admin/PageHeader';
import { DataTable, type Column } from '@/components/admin/DataTable';
import { Pagination } from '@/components/admin/Pagination';
import styles from '../admin.module.css';

const LIMIT = 50;
const ACTIONS = ['user.role_changed', 'subscription.activated', 'feedback.status_changed'];

export default function AdminAudit() {
  const { c, locale } = useAdminCopy();
  const [action, setAction] = useState('');
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<AuditPage | null>(null);
  const [error, setError] = useState(false);

  const load = useCallback(() => {
    setError(false);
    const params = new URLSearchParams({ limit: String(LIMIT), offset: String(offset) });
    if (action) params.set('action', action);
    authFetch(`/api/v1/admin/audit?${params}`).then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setData).catch(() => setError(true));
  }, [action, offset]);
  useEffect(load, [load]);

  const columns: Column<AuditEntry>[] = [
    { key: 'when', header: c.audit.when, render: (e) => formatDateTime(e.created_at, locale) },
    { key: 'who', header: c.audit.who, render: (e) => e.actor.username ?? e.actor.id },
    { key: 'action', header: c.audit.action, render: (e) => c.audit.actions[e.action] ?? e.action },
    { key: 'target', header: c.audit.target, render: (e) => <>
      {c.audit.targets[e.target_type] ?? e.target_type}<br /><span className={styles.mono}>{e.target_id}</span></> },
    { key: 'change', header: c.audit.change, render: (e) => summarizeChange(e) || c.common.dash },
    { key: 'reason', header: c.audit.reason, render: (e) => e.reason ?? c.common.dash, className: styles.prewrap },
  ];

  return <div className={styles.page}>
    <PageHeader title={c.audit.title} subtitle={c.audit.subtitle} />
    <div className={styles.toolbar}>
      <select className={styles.select} aria-label={c.audit.action} value={action}
        onChange={(e) => { setOffset(0); setAction(e.target.value); }}>
        <option value="">{c.common.all}</option>
        {ACTIONS.map((a) => <option key={a} value={a}>{c.audit.actions[a]}</option>)}
      </select>
    </div>
    <DataTable columns={columns} rows={data?.items ?? []} rowKey={(e) => e.id}
      loading={!data && !error} error={error} onRetry={load} />
    {data && <Pagination offset={offset} limit={LIMIT} total={data.total} onChange={setOffset} />}
  </div>;
}
```

- [ ] **Step 4: Rewrite `frontend/app/admin/settings/page.tsx`**

```tsx
'use client';

import { useCallback, useEffect, useState } from 'react';
import { authFetch } from '@/lib/auth';
import { useAdminCopy } from '@/lib/admin-i18n';
import type { AdminConfig } from '@/lib/admin-types';
import { PageHeader } from '@/components/admin/PageHeader';
import { AdminState } from '@/components/admin/AdminState';
import { Badge } from '@/components/admin/Badge';
import styles from '../admin.module.css';

const GROUPS = ['app', 'llm', 'email', 'billing', 'limits', 'secrets'];

export default function AdminConfigPage() {
  const { c } = useAdminCopy();
  const [config, setConfig] = useState<AdminConfig | null>(null);
  const [error, setError] = useState(false);

  const load = useCallback(() => {
    setError(false);
    authFetch('/api/v1/admin/config').then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setConfig).catch(() => setError(true));
  }, []);
  useEffect(load, [load]);

  const render = (group: string, value: string | number | boolean | null) => {
    if (group === 'secrets') return <Badge tone={value ? 'success' : 'warning'}>{value ? c.common.set : c.common.notSet}</Badge>;
    if (typeof value === 'boolean') return <Badge tone={value ? 'success' : 'neutral'}>{value ? c.common.yes : c.common.no}</Badge>;
    return <span className={styles.mono}>{value === null || value === '' ? c.common.dash : String(value)}</span>;
  };

  return <div className={styles.page}>
    <PageHeader title={c.config.title} subtitle={c.config.subtitle} />
    <p className={styles.notice}>{c.config.howToChange}</p>
    {error ? <AdminState kind="error" onRetry={load} />
      : !config ? <AdminState kind="loading" />
      : GROUPS.filter((g) => config[g]).map((group) => <section key={group} aria-labelledby={`cfg-${group}`}>
        <h2 id={`cfg-${group}`} className={styles.panelTitle}>{c.config.groups[group]}</h2>
        <div className={`liquid-glass ${styles.tableWrap}`}>
          <table className={styles.table}>
            <thead><tr><th scope="col">{c.config.name}</th><th scope="col">{c.config.value}</th></tr></thead>
            <tbody>{Object.entries(config[group]).map(([name, value]) => <tr key={name}>
              <td data-label={c.config.name} className={styles.mono}>{name}</td>
              <td data-label={c.config.value}>{render(group, value)}</td>
            </tr>)}</tbody>
          </table>
        </div>
      </section>)}
  </div>;
}
```

- [ ] **Step 5: Typecheck, lint, and look at the pages**

Run: `rtk npm run type-check && rtk npm run lint`
Expected: pass. Then run the app against the mocked API in Task 8, or locally against a dev backend, and open `/admin`, `/admin/audit`, `/admin/settings` in RU and KA at 1280 px and 390 px to confirm layout before committing.

- [ ] **Step 6: Commit**

```bash
rtk git add frontend/lib/admin-types.ts frontend/app/admin/page.tsx frontend/app/admin/audit/page.tsx frontend/app/admin/settings/page.tsx
rtk git commit -m "feat(admin): attention dashboard, action log and read-only config pages"
```

---

### Task 6: Users and Feedback on the new kit, with confirmed, reasoned changes

**Files:**
- Rewrite: `frontend/app/admin/users/page.tsx`
- Rewrite: `frontend/app/admin/feedback/page.tsx`

**Interfaces:**
- Consumes: Task 2 request bodies (`{role, reason}`, `{status, reason}`, `{checkout_id, reason}` / `{email, plan, months, reason}`); Task 4 components.
- Produces: no new exports.

- [ ] **Step 1: Rewrite `frontend/app/admin/users/page.tsx`**

```tsx
'use client';

import { useCallback, useEffect, useState } from 'react';
import { authFetch } from '@/lib/auth';
import { formatDate, formatDateTime, formatNumber, useAdminCopy } from '@/lib/admin-i18n';
import { PageHeader } from '@/components/admin/PageHeader';
import { DataTable, type Column } from '@/components/admin/DataTable';
import { Pagination } from '@/components/admin/Pagination';
import { ConfirmDialog } from '@/components/admin/ConfirmDialog';
import { Badge } from '@/components/admin/Badge';
import styles from '../admin.module.css';

interface AdminUser {
  id: string; username: string; email: string; role: 'user' | 'admin';
  created_at: string | null; last_login: string | null; plan: string; period_end: string | null;
}

type Pending =
  | { kind: 'role'; user: AdminUser; role: 'user' | 'admin' }
  | { kind: 'settle'; checkoutId: string }
  | { kind: 'activate'; email: string; plan: 'pro' | 'business'; months: number };

const LIMIT = 50;

async function send(url: string, method: string, body: object, fallback: string) {
  const res = await authFetch(url, { method, body: JSON.stringify(body) });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : fallback);
  return data;
}

export default function AdminUsers() {
  const { c, locale } = useAdminCopy();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [checkoutId, setCheckoutId] = useState('');
  const [email, setEmail] = useState('');
  const [plan, setPlan] = useState<'pro' | 'business'>('pro');
  const [months, setMonths] = useState(1);
  const [pending, setPending] = useState<Pending | null>(null);

  const load = useCallback(() => {
    setError(false);
    setLoading(true);
    authFetch(`/api/v1/admin/users?limit=${LIMIT}&offset=${offset}`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => { setUsers(d.items); setTotal(d.total); })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [offset]);
  useEffect(load, [load]);

  const confirm = async (reason: string) => {
    if (!pending) return;
    const until = (d: { period_end: string | null }) => formatDate(d.period_end, locale);
    if (pending.kind === 'role') {
      await send(`/api/v1/admin/users/${pending.user.id}/role`, 'PATCH', { role: pending.role, reason }, c.common.saveError);
    } else if (pending.kind === 'settle') {
      const d = await send('/api/v1/billing/admin/activate', 'POST', { checkout_id: pending.checkoutId, reason }, c.common.saveError);
      setMessage((d.replayed ? c.users.replayed : c.users.settled)(d.email, d.plan, until(d)));
      setCheckoutId('');
    } else {
      const d = await send('/api/v1/billing/admin/activate', 'POST',
        { email: pending.email, plan: pending.plan, months: pending.months, reason }, c.common.saveError);
      setMessage(c.users.activated(d.email, d.plan, until(d)));
      setEmail('');
    }
    load();
  };

  const dialogTitle = !pending ? '' : pending.kind === 'role' ? c.users.confirmRole(pending.user.username, pending.role)
    : pending.kind === 'settle' ? c.users.confirmSettle : c.users.confirmActivate(pending.email, pending.plan, pending.months);

  const columns: Column<AdminUser>[] = [
    { key: 'login', header: c.users.login, render: (u) => <strong>{u.username}</strong> },
    { key: 'email', header: c.users.email, render: (u) => u.email },
    { key: 'role', header: c.users.role, render: (u) => <select className={styles.select} aria-label={`${c.users.role}: ${u.username}`}
      value={u.role} onChange={(e) => setPending({ kind: 'role', user: u, role: e.target.value as 'user' | 'admin' })}>
      <option value="user">user</option><option value="admin">admin</option>
    </select> },
    { key: 'plan', header: c.users.plan, render: (u) => <Badge tone={u.plan === 'free' ? 'neutral' : 'success'}>{u.plan}</Badge> },
    { key: 'until', header: c.users.until, render: (u) => formatDate(u.period_end, locale) },
    { key: 'last', header: c.users.lastLogin, render: (u) => <span className={styles.muted}>{formatDateTime(u.last_login, locale)}</span> },
  ];

  return <div className={styles.page}>
    <PageHeader title={`${c.users.title} (${formatNumber(total, locale)})`} />

    <section className={`liquid-glass ${styles.panel}`}>
      <h2 className={styles.panelTitle}>{c.users.settleTitle}</h2>
      <div className={styles.toolbar}>
        <input className={styles.input} aria-label={c.users.checkoutPlaceholder} placeholder={c.users.checkoutPlaceholder}
          value={checkoutId} onChange={(e) => setCheckoutId(e.target.value)} />
        <button type="button" className={`${styles.button} ${styles.buttonPrimary}`} disabled={!checkoutId.trim()}
          onClick={() => setPending({ kind: 'settle', checkoutId: checkoutId.trim() })}>{c.users.settle}</button>
      </div>
      <hr className={styles.divider} />
      <h2 className={styles.panelTitle}>{c.users.legacyTitle}</h2>
      <div className={styles.toolbar}>
        <input className={styles.input} type="email" aria-label={c.users.emailPlaceholder} placeholder={c.users.emailPlaceholder}
          value={email} onChange={(e) => setEmail(e.target.value)} />
        <select className={styles.select} aria-label={c.users.plan} value={plan} onChange={(e) => setPlan(e.target.value as 'pro' | 'business')}>
          <option value="pro">Pro</option><option value="business">Business</option>
        </select>
        <select className={styles.select} aria-label={c.users.period} value={months} onChange={(e) => setMonths(Number(e.target.value))}>
          {[1, 3, 6, 12].map((m) => <option key={m} value={m}>{c.users.months(m)}</option>)}
        </select>
        <button type="button" className={styles.button} disabled={!email.trim()}
          onClick={() => setPending({ kind: 'activate', email: email.trim(), plan, months })}>{c.users.activate}</button>
      </div>
      {message && <p className={styles.notice} role="status">{message}</p>}
    </section>

    <DataTable columns={columns} rows={users} rowKey={(u) => u.id} loading={loading} error={error} onRetry={load} />
    <Pagination offset={offset} limit={LIMIT} total={total} onChange={setOffset} />

    <ConfirmDialog open={pending !== null} onOpenChange={(open) => { if (!open) setPending(null); }}
      title={dialogTitle} onConfirm={confirm} />
  </div>;
}
```

- [ ] **Step 2: Rewrite `frontend/app/admin/feedback/page.tsx`**

```tsx
'use client';

import { useCallback, useEffect, useState } from 'react';
import { authFetch } from '@/lib/auth';
import { formatDateTime, useAdminCopy } from '@/lib/admin-i18n';
import { PageHeader } from '@/components/admin/PageHeader';
import { DataTable, type Column } from '@/components/admin/DataTable';
import { ConfirmDialog } from '@/components/admin/ConfirmDialog';
import { Badge, type BadgeTone } from '@/components/admin/Badge';
import styles from '../admin.module.css';

type Status = 'new' | 'in_progress' | 'fixed';
interface FeedbackItem { id: string; message: string; page: string | null; status: Status; created_at: string | null; email: string; username: string }
interface FeedbackResponse { total: number; counts: Record<Status, number>; items: FeedbackItem[] }

const STATUSES: Status[] = ['new', 'in_progress', 'fixed'];
const TONE: Record<Status, BadgeTone> = { new: 'warning', in_progress: 'neutral', fixed: 'success' };

export default function AdminFeedback() {
  const { c, locale } = useAdminCopy();
  const [data, setData] = useState<FeedbackResponse | null>(null);
  const [error, setError] = useState(false);
  const [filter, setFilter] = useState<Status | ''>('');
  const [pending, setPending] = useState<{ item: FeedbackItem; status: Status } | null>(null);

  const load = useCallback(() => {
    setError(false);
    authFetch(`/api/v1/admin/feedback?limit=100${filter ? `&status=${filter}` : ''}`)
      .then((r) => (r.ok ? r.json() : Promise.reject())).then(setData).catch(() => setError(true));
  }, [filter]);
  useEffect(load, [load]);

  const confirm = async (reason: string) => {
    if (!pending) return;
    const res = await authFetch(`/api/v1/admin/feedback/${pending.item.id}`, {
      method: 'PATCH', body: JSON.stringify({ status: pending.status, reason }),
    });
    if (!res.ok) throw new Error(c.common.saveError);
    load();
  };

  const columns: Column<FeedbackItem>[] = [
    { key: 'date', header: c.feedback.date, render: (f) => <span className={styles.muted}>{formatDateTime(f.created_at, locale)}</span> },
    { key: 'user', header: c.feedback.user, render: (f) => f.email },
    { key: 'page', header: c.feedback.page, render: (f) => <span className={styles.mono}>{f.page ?? c.common.dash}</span> },
    { key: 'message', header: c.feedback.message, render: (f) => f.message, className: styles.prewrap },
    { key: 'status', header: c.feedback.status, render: (f) => <div className={styles.toolbar}>
      <Badge tone={TONE[f.status]}>{c.feedback.statuses[f.status]}</Badge>
      <select className={styles.select} aria-label={c.feedback.status} value={f.status}
        onChange={(e) => setPending({ item: f, status: e.target.value as Status })}>
        {STATUSES.map((s) => <option key={s} value={s}>{c.feedback.statuses[s]}</option>)}
      </select>
    </div> },
  ];

  return <div className={styles.page}>
    <PageHeader title={`${c.feedback.title}${data ? ` (${data.total})` : ''}`} />
    <div className={styles.toolbar} role="group" aria-label={c.feedback.status}>
      {(['', ...STATUSES] as const).map((s) => <button key={s || 'all'} type="button"
        className={`${styles.button} ${styles.chip}`} aria-pressed={filter === s} onClick={() => setFilter(s)}>
        {s === '' ? c.common.all : `${c.feedback.statuses[s]}${data ? ` · ${data.counts[s]}` : ''}`}
      </button>)}
    </div>
    <DataTable columns={columns} rows={data?.items ?? []} rowKey={(f) => f.id}
      loading={!data && !error} error={error} onRetry={load} />
    <ConfirmDialog open={pending !== null} onOpenChange={(open) => { if (!open) setPending(null); }}
      title={pending ? c.feedback.confirmStatus(c.feedback.statuses[pending.status]) : ''} onConfirm={confirm} />
  </div>;
}
```

Note: the `<select>` value stays at the saved status while the dialog is open (React controlled value is `f.status`), so cancelling leaves the row unchanged.

- [ ] **Step 3: Add the period label**

Add `period: 'Срок',` / `period: 'ვადა',` / `period: 'Period',` to the `users` section of the `ru` / `ka` / `en` dictionaries in `frontend/lib/admin-i18n.ts` (used as the months select's `aria-label`).

- [ ] **Step 4: Typecheck and lint**

Run: `rtk npm run type-check && rtk npm run lint`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
rtk git add frontend/app/admin/users/page.tsx frontend/app/admin/feedback/page.tsx frontend/lib/admin-i18n.ts
rtk git commit -m "feat(admin): confirmed, journaled user and feedback changes on the new kit"
```

---

### Task 7: Documents, Scraper, Analytics and Payments palette

**Files:**
- Rewrite: `frontend/app/admin/documents/page.tsx`, `frontend/app/admin/scraper/page.tsx`, `frontend/app/admin/analytics/page.tsx`
- Modify: `frontend/app/admin/billing/reconciliation.module.css`, `frontend/app/admin/billing/DESIGN.md`

**Interfaces:**
- Consumes: Task 4 components and copy.
- Produces: `npm run check:admin-styles` passes.

- [ ] **Step 1: Rewrite `frontend/app/admin/documents/page.tsx`**

```tsx
'use client';

import { useEffect, useState } from 'react';
import { authFetch } from '@/lib/auth';
import { formatDate, formatNumber, useAdminCopy } from '@/lib/admin-i18n';
import { PageHeader } from '@/components/admin/PageHeader';
import { DataTable, type Column } from '@/components/admin/DataTable';
import { Pagination } from '@/components/admin/Pagination';
import styles from '../admin.module.css';

interface AdminDoc {
  id: string; title: string; document_type: string; document_number: string | null;
  date_published: string | null; authority: string | null; source_url: string; created_at: string | null;
}

const TYPES = ['law', 'regulation', 'court_decision', 'guideline', 'news', 'bill'];
const LIMIT = 50;

export default function AdminDocuments() {
  const { c, locale } = useAdminCopy();
  const [items, setItems] = useState<AdminDoc[]>([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState('');
  const [docType, setDocType] = useState('');
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams({ limit: String(LIMIT), offset: String(offset) });
    if (search.trim()) params.set('search', search.trim());
    if (docType) params.set('doc_type', docType);
    setLoading(true);
    setError(false);
    authFetch(`/api/v1/admin/documents?${params}`, { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => { setItems(d.items); setTotal(d.total); })
      .catch(() => { if (!controller.signal.aborted) setError(true); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [search, docType, offset, attempt]);

  const columns: Column<AdminDoc>[] = [
    { key: 'title', header: c.documents.name, render: (d) =>
      <a href={d.source_url} target="_blank" rel="noopener noreferrer" title={d.title} className={styles.truncate}>{d.title}</a> },
    { key: 'type', header: c.documents.type, render: (d) => d.document_type },
    { key: 'number', header: c.documents.number, render: (d) => d.document_number ?? c.common.dash },
    { key: 'date', header: c.documents.date, render: (d) => formatDate(d.date_published, locale) },
    { key: 'authority', header: c.documents.authority, render: (d) => d.authority ?? c.common.dash },
  ];

  return <div className={styles.page}>
    <PageHeader title={`${c.documents.title} (${formatNumber(total, locale)})`} />
    <div className={styles.toolbar}>
      <input className={styles.input} type="search" aria-label={c.documents.search} placeholder={c.documents.search}
        value={search} onChange={(e) => { setOffset(0); setSearch(e.target.value); }} />
      <select className={styles.select} aria-label={c.documents.type} value={docType}
        onChange={(e) => { setOffset(0); setDocType(e.target.value); }}>
        <option value="">{c.documents.allTypes}</option>
        {TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
      </select>
    </div>
    <DataTable columns={columns} rows={items} rowKey={(d) => d.id} loading={loading} error={error}
      onRetry={() => setAttempt((a) => a + 1)} emptyText={c.documents.notFound} />
    <Pagination offset={offset} limit={LIMIT} total={total} onChange={setOffset} />
  </div>;
}
```

- [ ] **Step 2: Rewrite `frontend/app/admin/scraper/page.tsx`**

```tsx
'use client';

import { useCallback, useEffect, useState } from 'react';
import { authFetch } from '@/lib/auth';
import { formatDateTime, formatNumber, useAdminCopy } from '@/lib/admin-i18n';
import { PageHeader } from '@/components/admin/PageHeader';
import { StatTile } from '@/components/admin/StatTile';
import { AdminState } from '@/components/admin/AdminState';
import styles from '../admin.module.css';

interface OpsStatus {
  last_ingest: string | null;
  documents_today: number;
  pending: { decision_facts: number; law_amendments: number };
  logs: Record<string, string[]>;
}

export default function AdminScraper() {
  const { c, locale } = useAdminCopy();
  const [ops, setOps] = useState<OpsStatus | null>(null);
  const [error, setError] = useState(false);

  const load = useCallback(() => {
    setError(false);
    authFetch('/api/v1/admin/ops').then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setOps).catch(() => setError(true));
  }, []);
  useEffect(load, [load]);

  return <div className={styles.page}>
    <PageHeader title={c.scraper.title}
      actions={<button type="button" className={styles.button} onClick={load}>{c.common.refresh}</button>} />
    {error ? <AdminState kind="error" onRetry={load} /> : !ops ? <AdminState kind="loading" /> : <>
      <div className={styles.tiles}>
        <StatTile label={c.scraper.lastIngest} value={formatDateTime(ops.last_ingest, locale)}
          detail={c.scraper.today(formatNumber(ops.documents_today, locale))} />
        <StatTile label={c.scraper.decisions} value={formatNumber(ops.pending.decision_facts, locale)} />
        <StatTile label={c.scraper.amendments} value={formatNumber(ops.pending.law_amendments, locale)} />
      </div>
      {Object.entries(ops.logs).map(([key, lines]) => <section key={key} className={`liquid-glass ${styles.panel}`}>
        <h2 className={styles.panelTitle}>{c.scraper.logs[key] ?? key}</h2>
        {lines.length === 0 ? <p className={styles.notice}>{c.scraper.logEmpty}</p>
          : <pre className={styles.log}>{lines.join('\n')}</pre>}
      </section>)}
    </>}
  </div>;
}
```

- [ ] **Step 3: Rewrite `frontend/app/admin/analytics/page.tsx`**

```tsx
'use client';

import { useCallback, useEffect, useState, type CSSProperties } from 'react';
import { formatNumber, useAdminCopy, type AdminCopy } from '@/lib/admin-i18n';
import { PageHeader } from '@/components/admin/PageHeader';
import { StatTile } from '@/components/admin/StatTile';
import { AdminState } from '@/components/admin/AdminState';
import styles from '../admin.module.css';

// Outcome palette — validated (dataviz six checks, dark surface).
const OUTCOMES = [
  { key: 'satisfied', color: '#059669' },
  { key: 'partially_satisfied', color: '#d97706' },
  { key: 'rejected', color: '#3b82f6' },
] as const;

interface OutcomeRow { total: number; satisfied: number; partially_satisfied: number; rejected: number; unclear: number; taxpayer_relief_rate: number | null }
interface Analytics {
  coverage: { decisions_in_corpus: number; decisions_extracted: number };
  overall: OutcomeRow;
  by_year: (OutcomeRow & { year: number })[];
  by_body: (OutcomeRow & { body: string })[];
  top_articles: (OutcomeRow & { article: string })[];
}

const pct = (rate: number | null) => (rate == null ? '—' : `${Math.round(rate * 100)}%`);
const vars = (v: Record<string, string>) => v as CSSProperties;

function StackedBar({ row, c }: { row: OutcomeRow; c: AdminCopy }) {
  const total = row.satisfied + row.partially_satisfied + row.rejected;
  if (!total) return <div className={styles.barTrack} />;
  return <div className={styles.barTrack}>
    {OUTCOMES.map(({ key, color }) => row[key] ? <span key={key} className={styles.barSegment}
      title={`${c.analytics.outcomes[key]}: ${row[key]} (${Math.round((row[key] / total) * 100)}%)`}
      style={vars({ '--w': `${(row[key] / total) * 100}%`, '--c': color })} /> : null)}
  </div>;
}

function Legend({ c }: { c: AdminCopy }) {
  return <div className={styles.legend}>
    {OUTCOMES.map(({ key, color }) => <span key={key}>
      <span className={styles.swatch} style={vars({ '--c': color })} />{c.analytics.outcomes[key]}</span>)}
  </div>;
}

function BarSection({ title, rows, c }: { title: string; rows: { label: string; row: OutcomeRow }[]; c: AdminCopy }) {
  return <section className={`liquid-glass ${styles.panel}`}>
    <h2 className={styles.panelTitle}>{title}</h2>
    <Legend c={c} />
    <div className={styles.bars}>
      {rows.map(({ label, row }) => <div key={label} className={styles.barRow}>
        <span>{label}</span>
        <StackedBar row={row} c={c} />
        <span className={styles.barMeta}>{row.total} · {c.analytics.reliefShort} {pct(row.taxpayer_relief_rate)}</span>
      </div>)}
    </div>
  </section>;
}

export default function AnalyticsPage() {
  const { c, locale } = useAdminCopy();
  const [data, setData] = useState<Analytics | null>(null);
  const [error, setError] = useState(false);

  const load = useCallback(() => {
    setError(false);
    fetch('/api/v1/analytics/decisions').then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setData).catch(() => setError(true));
  }, []);
  useEffect(load, [load]);

  if (error) return <AdminState kind="error" onRetry={load} />;
  if (!data) return <AdminState kind="loading" />;
  const n = (v: number) => formatNumber(v, locale);
  const coverage = data.coverage.decisions_in_corpus
    ? Math.round((data.coverage.decisions_extracted / data.coverage.decisions_in_corpus) * 100) : 0;

  return <div className={styles.page}>
    <PageHeader title={c.analytics.title} subtitle={c.analytics.subtitle} />
    <div className={styles.tiles}>
      <StatTile label={c.analytics.analyzed} value={n(data.coverage.decisions_extracted)}
        detail={c.analytics.coverage(coverage, n(data.coverage.decisions_in_corpus))} />
      <StatTile label={c.analytics.relief} value={pct(data.overall.taxpayer_relief_rate)} detail={c.analytics.reliefDetail} />
      <StatTile label={c.analytics.satisfied} value={n(data.overall.satisfied)} detail={c.analytics.vsRejected(n(data.overall.rejected))} />
    </div>
    <BarSection c={c} title={c.analytics.byYear} rows={data.by_year.map((r) => ({ label: String(r.year), row: r }))} />
    <BarSection c={c} title={c.analytics.byBody}
      rows={data.by_body.filter((r) => r.body).map((r) => ({ label: c.analytics.bodies[r.body] ?? r.body, row: r }))} />
    <section className={`liquid-glass ${styles.panel}`}>
      <h2 className={styles.panelTitle}>{c.analytics.topArticles}</h2>
      <Legend c={c} />
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead><tr>
            <th scope="col">{c.analytics.article}</th><th scope="col">{c.analytics.decisions}</th>
            <th scope="col">{c.analytics.split}</th><th scope="col">{c.analytics.reliefRate}</th>
          </tr></thead>
          <tbody>{data.top_articles.map((r) => <tr key={r.article}>
            <td data-label={c.analytics.article}><strong>{r.article}</strong></td>
            <td data-label={c.analytics.decisions}>{r.total}</td>
            <td data-label={c.analytics.split}><StackedBar row={r} c={c} /></td>
            <td data-label={c.analytics.reliefRate}>{pct(r.taxpayer_relief_rate)}</td>
          </tr>)}</tbody>
        </table>
      </div>
    </section>
  </div>;
}
```

- [ ] **Step 4: Run the inline-style guard**

Run: `rtk npm run check:admin-styles`
Expected: PASS — `Admin UI has no inline style objects.` If `billing/ReviewControls.tsx` or `billing/page.tsx` is listed, move each listed inline style into a class in `reconciliation.module.css` (same values, token colours) and re-run.

- [ ] **Step 5: Retune the Payments palette**

In `frontend/app/admin/billing/reconciliation.module.css` replace colours exactly (all occurrences):

| Old | New |
|---|---|
| `#0f172a` | `hsl(var(--background))` |
| `#1e293b` | `hsl(var(--secondary))` |
| `#334155` | `hsl(var(--border))` |
| `#475569` | `hsl(var(--border))` |
| `#64748b` | `hsl(var(--input))` |
| `#94a3b8` | `hsl(var(--primary))` |
| `#cbd5e1` | `hsl(var(--muted-foreground))` |
| `#fca5a5` | `hsl(var(--ring))` |
| `#fff` | `hsl(var(--foreground))` |

Then: `rtk grep -n "#[0-9a-fA-F]\{3,6\}" frontend/app/admin/billing/reconciliation.module.css` — map any remaining hex to the nearest token from Global Constraints. In `frontend/app/admin/billing/DESIGN.md`, replace the `colors:` block with:

```yaml
colors:
  background: "hsl(var(--background))"   # #000
  surface: "hsl(var(--secondary))"       # quiet raised surface
  divider: "hsl(var(--border))"
  control-border: "hsl(var(--input))"
  selection-border: "hsl(var(--primary))" # #DC2626
  secondary-text: "hsl(var(--muted-foreground))"
  primary-text: "hsl(var(--foreground))"
  focus: "hsl(var(--ring))"
```

and update any prose in DESIGN.md that names navy/slate to say the page uses the shared admin palette from `globals.css`.

- [ ] **Step 6: Typecheck, lint, guard, billing e2e**

Run: `rtk npm run type-check && rtk npm run lint && rtk npm run check:admin-styles && rtk npm run build && rtk npx playwright test e2e/billing-reconciliation.spec.ts`
Expected: all pass (billing behaviour unchanged).

- [ ] **Step 7: Commit**

```bash
rtk git add frontend/app/admin/documents/page.tsx frontend/app/admin/scraper/page.tsx frontend/app/admin/analytics/page.tsx frontend/app/admin/billing
rtk git commit -m "feat(admin): move documents, ingest, analytics and payments onto the shared palette"
```

---

### Task 8: Admin e2e smoke, mobile overflow and visual snapshots

**Files:**
- Create: `frontend/e2e/admin.spec.ts`
- Modify: `frontend/playwright.config.ts` (`testMatch`)
- Create: `frontend/e2e/__screenshots__/admin-dashboard-ru-desktop.png`, `admin-users-ka-mobile.png` (generated)

**Interfaces:**
- Consumes: all HTTP contracts from Tasks 2–3, all pages from Tasks 4–7.

- [ ] **Step 1: Write the e2e spec**

`frontend/e2e/admin.spec.ts`:

```ts
import { expect, Page, Route, test } from '@playwright/test';

const longEmail = `very.long.customer.address.${'x'.repeat(30)}@example-company-domain.ge`;
const stats = {
  documents: { total: 48211, by_type: { law: 1204, court_decision: 11249, guideline: 631 }, last_ingest: '2026-10-11T02:10:00' },
  decisions: { total: 11249, extracted: 11000, pending: 249 },
  amendments: { acts_total: 926, extracted: 926, resolved: 627, pending: 0 },
  users: { total: 42, admins: 1 },
  subscriptions: { pro: 3 },
  conversations: { total: 310, messages: 2400, messages_7d: 120 },
  feedback: { new: 2 },
  billing: { reconciliation_open: 1, manual_pending: 1 },
  attention: { ingest_stale: false },
};
const auditItems = [{
  id: 'a1', actor: { id: 'u0', username: 'admin' }, action: 'user.role_changed', target_type: 'user',
  target_id: '20000000-0000-0000-0000-000000000001', before: { role: 'user' }, after: { role: 'admin' },
  reason: 'promote accountant', created_at: '2026-10-11T09:00:00',
}];
const users = [{
  id: '20000000-0000-0000-0000-000000000001', username: 'customer', email: longEmail, role: 'user',
  created_at: '2026-10-01T10:00:00', last_login: '2026-10-10T18:00:00', plan: 'pro', period_end: '2026-11-01T00:00:00',
}];
const config = {
  app: { APP_VERSION: '0.1.0', ENVIRONMENT: 'production', DEBUG: false },
  llm: { LLM_PROVIDER: 'openai', LLM_MODEL: 'gpt-4o-mini', EMBEDDING_MODEL: 'paraphrase-multilingual-mpnet-base-v2', RAG_TOP_K: 10, RAG_MIN_SIMILARITY: 0.5, JEV_MODE: 'off' },
  email: { EMAIL_DELIVERY_ENABLED: true, SMTP_HOST: 'smtp.resend.com', SMTP_PORT: 587, SMTP_FROM: 'Tax Advisor <info@tax-advisor.ge>' },
  billing: { BILLING_TBC_ENABLED: false, BILLING_CONTACT_EMAIL: 'info@tax-advisor.ge', FREE_DAILY_QUESTIONS: 5 },
  limits: { RATE_LIMIT_ENABLED: true },
  secrets: { OPENAI_API_KEY: true, ANTHROPIC_API_KEY: false, SMTP_PASSWORD: true, TBC_API_KEY: false, TBC_CLIENT_ID: false, TBC_CLIENT_SECRET: false, TYPESAFE_API_KEY: false },
};
const feedback = { total: 1, counts: { new: 1, in_progress: 0, fixed: 0 }, items: [{
  id: 'f1', message: 'Ссылка на статью 168 не открывается', page: '/laws', status: 'new',
  created_at: '2026-10-10T12:00:00', email: longEmail, username: 'customer',
}] };
const ops = { last_ingest: '2026-10-11T02:10:00', documents_today: 14, pending: { decision_facts: 249, law_amendments: 0 },
  logs: { scraper: ['2026-10-11 02:10 done: +14 new'], law_amendments_backfill: [], decision_facts_backfill: [] } };
const row = { total: 100, satisfied: 1, partially_satisfied: 27, rejected: 72, unclear: 0, taxpayer_relief_rate: 0.28 };
const analytics = { coverage: { decisions_in_corpus: 11249, decisions_extracted: 11000 }, overall: row,
  by_year: [{ ...row, year: 2025 }], by_body: [{ ...row, body: 'revenue_service_council' }], by_dispute_type: [],
  top_articles: [{ ...row, article: '168' }] };

async function json(route: Route, data: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
}

async function setup(page: Page, lang: 'ru' | 'ka' | 'en' = 'ru') {
  await page.addInitScript((language) => {
    localStorage.setItem('ta_lang', language);
    localStorage.setItem('ta_authenticated', '1');
  }, lang);
  const writes: { method: string; path: string; body: unknown }[] = [];
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() !== 'GET') {
      writes.push({ method: request.method(), path: url.pathname, body: request.postDataJSON() });
      return json(route, { id: users[0].id, username: 'customer', role: 'admin', status: 'fixed' });
    }
    const fixtures: Record<string, unknown> = {
      '/api/v1/auth/me': { username: 'admin', role: 'admin' },
      '/api/v1/admin/stats': stats,
      '/api/v1/admin/audit': { total: 1, items: auditItems },
      '/api/v1/admin/config': config,
      '/api/v1/admin/users': { total: 1, items: users },
      '/api/v1/admin/feedback': feedback,
      '/api/v1/admin/documents': { total: 0, items: [] },
      '/api/v1/admin/ops': ops,
      '/api/v1/analytics/decisions': analytics,
      '/api/v1/billing/admin/reconciliation': { items: [], next_offset: null },
    };
    return url.pathname in fixtures ? json(route, fixtures[url.pathname]) : json(route, { detail: 'No fixture' }, 404);
  });
  return writes;
}

const PAGES = ['/admin', '/admin/users', '/admin/billing', '/admin/feedback', '/admin/documents',
  '/admin/analytics', '/admin/scraper', '/admin/audit', '/admin/settings'];

for (const lang of ['ru', 'ka'] as const) {
  for (const viewport of [{ width: 1280, height: 900 }, { width: 390, height: 844 }]) {
    test(`every admin page renders without horizontal scroll (${lang}, ${viewport.width}px)`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await setup(page, lang);
      for (const path of PAGES) {
        await page.goto(path);
        await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
        expect(overflow, `${path} overflows by ${overflow}px`).toBeLessThanOrEqual(0);
      }
    });
  }
}

test('dashboard lists what needs attention', async ({ page }) => {
  await setup(page, 'en');
  await page.goto('/admin');
  const attention = page.getByRole('region', { name: 'Needs attention' });
  await expect(attention.getByRole('link', { name: 'New feedback: 2' })).toHaveAttribute('href', '/admin/feedback');
  await expect(attention.getByRole('link', { name: 'Payments to reconcile: 1' })).toHaveAttribute('href', '/admin/billing');
  await expect(attention.getByRole('link', { name: 'Orders awaiting activation: 1' })).toBeVisible();
  await expect(page.getByText('role: user → admin')).toBeVisible();
});

test('role change requires confirmation and sends the reason', async ({ page }) => {
  const writes = await setup(page, 'en');
  await page.goto('/admin/users');
  await page.getByLabel('Role: customer').selectOption('admin');
  const dialog = page.getByRole('dialog');
  await expect(dialog).toContainText('Change customer\'s role to “admin”?');
  await dialog.getByLabel('Reason (optional)').fill('promote accountant');
  await dialog.getByRole('button', { name: 'Confirm' }).click();
  await expect(dialog).toBeHidden();
  expect(writes).toEqual([{ method: 'PATCH', path: `/api/v1/admin/users/${users[0].id}/role`,
    body: { role: 'admin', reason: 'promote accountant' } }]);
});

test('cancelling a feedback status change sends nothing', async ({ page }) => {
  const writes = await setup(page, 'en');
  await page.goto('/admin/feedback');
  await page.getByRole('combobox', { name: 'Status' }).selectOption('fixed');
  await page.getByRole('dialog').getByRole('button', { name: 'Cancel' }).first().click();
  await expect(page.getByRole('dialog')).toBeHidden();
  await expect(page.getByRole('combobox', { name: 'Status' })).toHaveValue('new');
  expect(writes).toEqual([]);
});

test('config shows secrets only as set / not set', async ({ page }) => {
  await setup(page, 'en');
  await page.goto('/admin/settings');
  await expect(page.getByRole('heading', { name: 'Secrets' })).toBeVisible();
  const secretsTable = page.getByRole('table').last();
  await expect(secretsTable.getByText('set', { exact: true }).first()).toBeVisible();
  await expect(secretsTable.getByText('not set', { exact: true }).first()).toBeVisible();
});

test('admin visual baseline', async ({ page }) => {
  await setup(page, 'ru');
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto('/admin');
  await expect(page.getByText('role: user → admin')).toBeVisible();
  await page.evaluate(async () => { await document.fonts.ready; });
  await expect(page).toHaveScreenshot('admin-dashboard-ru-desktop.png', { fullPage: true });

  await setup(page, 'ka');
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/admin/users');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await page.evaluate(async () => { await document.fonts.ready; });
  await expect(page).toHaveScreenshot('admin-users-ka-mobile.png', { fullPage: true });
});
```

In `frontend/playwright.config.ts` change `testMatch` to `['visual.spec.ts', 'billing-reconciliation.spec.ts', 'admin.spec.ts']`.

- [ ] **Step 2: Run the functional tests**

Run (from `frontend/`): `rtk npm run build && rtk npx playwright test e2e/admin.spec.ts --grep-invert "visual baseline"`
Expected: PASS. If an overflow test fails, fix the offending element's CSS in `admin.module.css` (never by hiding overflow on `body`) and re-run. If a role/label locator does not match, fix the markup (labels are the contract), not the test.

- [ ] **Step 3: Generate snapshots in the CI image**

Snapshots must come from the pinned Playwright container, not Windows. From the repo root:

```bash
rtk docker run --rm --ipc=host -v "$PWD":/work -v /work/frontend/node_modules -w /work/frontend \
  mcr.microsoft.com/playwright@sha256:dcc5531e97840b9b5e794f2814476b21571c5124a3fca2267d73041f56e7580e \
  bash -c "npm ci --ignore-scripts && npm run build && npx playwright test e2e/admin.spec.ts --grep 'visual baseline' --update-snapshots"
```

Expected: `frontend/e2e/__screenshots__/admin-dashboard-ru-desktop.png` and `admin-users-ka-mobile.png` created. Open both PNGs and check them by eye (red accent on active menu item, glass panels, no clipped Georgian text). If Docker is unavailable on this machine, stop and report it — do not commit Windows-rendered snapshots.

- [ ] **Step 4: Commit**

```bash
rtk git add frontend/e2e/admin.spec.ts frontend/playwright.config.ts frontend/e2e/__screenshots__/admin-dashboard-ru-desktop.png frontend/e2e/__screenshots__/admin-users-ka-mobile.png
rtk git commit -m "test(admin): e2e smoke, mobile overflow and visual baselines"
```

---

### Task 9: Docs and full verification

**Files:**
- Modify: `docs/PRODUCTION_OPERATIONS.md` (deploy schema steps section)
- Modify: `docs/DEVELOPMENT_MEMORY.md` (append a dated entry)

- [ ] **Step 1: Document the deploy step**

In `docs/PRODUCTION_OPERATIONS.md`, next to the existing description of the billing review journal install step, add:

```markdown
- `backend/scripts/add_admin_audit_log.py` installs `admin_audit_log`, the append-only journal of
  administrator actions (role changes, manual subscription activation, feedback status). The deploy
  script applies it with the pinned `ADMIN_AUDIT_SCHEMA_CONTRACT_SHA256` before starting the backend.
  The table is additive; rolling back the code leaves it unused and harmless. Rows cannot be updated
  or deleted (statement trigger `admin_audit_immutable`).
```

In `docs/DEVELOPMENT_MEMORY.md` append:

```markdown
## 2026-10-11 — Admin stage 1 (foundation)

- `/admin` uses one CSS module (`app/admin/admin.module.css`) on `globals.css` tokens and the kit in
  `components/admin/`; copy lives in `lib/admin-i18n.ts` (RU/KA/EN). `npm run check:admin-styles`
  rejects inline style objects other than CSS custom properties.
- Admin mutations write `admin_audit_log` in the same transaction via `core.admin_audit.record_admin_action`;
  no-op changes and activation replays write nothing. Read at `/admin/audit`.
- `/admin/config` is a whitelist (`core/public_config.py`); secrets are booleans only.
- Dashboard attention counters reuse `billing.reconciliation.reconciliation_queue_filter()`.
- Next stages: 2 clients → 4 answer quality → 3 trends → 5 operations.
```

- [ ] **Step 2: Full backend verification**

Run (from `backend/`, CI env): `rtk python -m pytest tests/test_admin_audit.py tests/test_public_config.py tests/test_integration.py tests/test_billing_gateway.py tests/test_config_contract.py -q`
and (PostgreSQL, `BILLING_PROVIDER_POSTGRES_TESTS=1`): `rtk python -m pytest tests/test_admin_postgres.py tests/test_billing_provider_postgres.py tests/test_billing_review_postgres.py -q`
Expected: all pass. Paste the summary lines into the PR description.

- [ ] **Step 3: Full frontend verification**

Run (from `frontend/`): `rtk npm run lint && rtk npm run type-check && rtk npm run check:admin-styles && rtk npm run build && rtk npx playwright test`
Expected: all pass (existing visual and billing specs unchanged).

- [ ] **Step 4: Commit and open the PR**

```bash
rtk git add docs/PRODUCTION_OPERATIONS.md docs/DEVELOPMENT_MEMORY.md
rtk git commit -m "docs(admin): record stage 1 journal deploy step and admin UI conventions"
rtk git push -u origin feat/admin-stage1-foundation
rtk gh pr create --title "Admin stage 1: shared UI, RU/KA/EN, action journal, dashboard, config" --body-file <(printf '%s\n' "Implements docs/superpowers/specs/2026-10-11-admin-stage1-foundation-design.md." "" "Deploy: new pinned schema step add_admin_audit_log.py (runs before backend start)." "" "🤖 Generated with [Claude Code](https://claude.com/claude-code)")
```

Wait for CI (backend, temporal-postgres, frontend, visual) to pass before reporting done. Deploy remains Gela's step via `deploy.sh`.
