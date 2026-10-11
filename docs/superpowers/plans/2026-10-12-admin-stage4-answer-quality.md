# Admin Stage 4 — Answer Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist answer-quality signals, let signed-in users rate answers, and give the admin a pseudonymous answer feed with review (verdict + reasons), an audited "reveal user" action and a quality summary.

**Architecture:** One additive, SHA-pinned schema script (`add_answer_quality.py`) adds `messages.evidence`/`processing_ms` and tables `answer_ratings`/`answer_reviews` (reviews protected by triggers). `POST /query` stores the signals and returns `message_id`; a small rating API lives in the query router. A new admin router `admin_quality.py` backed by pure helpers in `core/admin_quality.py` serves the feed, detail, review, reveal and summary. Frontend adds `/admin/quality` and `/admin/quality/[id]` on the stage 1–2 kit, an `AnswerRating` component on the site, and privacy-policy wording.

**Tech Stack:** FastAPI, SQLAlchemy 2, PostgreSQL 15 + pgvector, pytest (SQLite for `test_integration.py`); Next.js 16 / React 19, CSS Modules (admin) + Tailwind/liquid-glass (site), Playwright 1.62.

**Spec:** `docs/superpowers/specs/2026-10-12-admin-stage4-answer-quality-design.md`

## Global Constraints

- One role `admin`; every `/admin/quality/*` route is behind `require_admin` (router-level dependency). Rating routes require `get_current_user`.
- Schema changes ONLY through `backend/scripts/add_answer_quality.py` (additive, idempotent, dry plan by default), pinned as `ANSWER_QUALITY_SCHEMA_CONTRACT_SHA256` in `scripts/deploy_production.sh`, run right after the admin-audit step. No other DDL.
- ORM column types must work on SQLite too (`tests/test_integration.py` uses `sqlite://`): use `sqlalchemy.JSON` for `evidence` and `reasons` (the DDL creates `JSONB` in PostgreSQL), never `ARRAY`/`JSONB` in models.
- Admin mutations (review, reveal): change + `record_admin_action` in one transaction; reason required via `core.admin_users.Reason` (stripped, 3–1000).
- Every `HTTPException` in new admin code and in the new rating routes uses `admin_error` → `detail={"code","message"}`; each route documents its codes in a literal `responses={...}` dict.
- No f-string SQL in new code (SonarCloud S2077) — SQLAlchemy Core/ORM expressions only (the schema script's static DDL tuple is the existing exception pattern).
- Admin feed and detail never expose email, username or user id — only the pseudonym. The user id is returned only by `reveal-user`.
- RAG/routing/generation logic unchanged; only persistence and the response's `message_id` change. Guest `/public/query` unchanged.
- Frontend admin: no `style={{…}}` except CSS custom properties (`npm run check:admin-styles`); colours from `globals.css` tokens + warning `#d97706`; data via `useAdminFetch`, writes via `adminSend`/`errorText`.
- All copy RU/KA/EN (admin copy in `lib/admin-i18n.ts`, site copy in `lib/i18n.tsx`, policy in `lib/legal-content.ts`); Georgian written and reviewed with the `georgian-writing-style` skill. Free grants terminology from stage 2 stays «подарочный сертификат».
- Visual baselines only in the pinned Playwright container `mcr.microsoft.com/playwright@sha256:dcc5531e97840b9b5e794f2814476b21571c5124a3fca2267d73041f56e7580e`.
- Shell commands prefixed with `rtk`; commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Backend env (from `backend/`): `DATABASE_URL=postgresql://test:test@127.0.0.1:5440/test REDIS_URL=redis://localhost:6379/0 SECRET_KEY=test-secret-key-for-ci-minimum-32-characters JWT_SECRET_KEY=test-jwt-secret-for-ci-minimum-32-characters`; PG tests add `BILLING_PROVIDER_POSTGRES_TESTS=1`.
- Slow machine (pytest collection ≈6 min, PG suites ≈9 min, Next build ≈15 min, container ≈25–40 min): long commands in the background with a log, bounded `sleep N; tail` polling, never end a turn waiting.

## Plan-level decisions (deviations from the spec text, made while planning)

- `answer_reviews.reasons` is `JSONB NOT NULL DEFAULT '[]'` (spec said `TEXT[]`) so the ORM can use portable `JSON`. Allowed values are still validated in the API.
- Reviews protection: row-level `BEFORE UPDATE` trigger rejects all updates; row-level `BEFORE DELETE` trigger rejects deletes while the parent message still exists (so `ON DELETE CASCADE` from `messages` works); statement-level `BEFORE TRUNCATE` trigger rejects truncates.

## Review Focus

1. **Ratings on someone else's message / on a user message** — expected 404 `message_not_found` / 409 `not_assistant_message`, nothing stored. Tests in Task 3.
2. **Old answers without `evidence`** — expected: feed shows them, `no_evidence` flag, other evidence flags do NOT match them, detail shows "no data", summary shares ignore them. Tests in Tasks 4 and 8.
3. **Deleting a user/message with reviews** — expected: cascade succeeds despite the immutability trigger; direct UPDATE/DELETE/TRUNCATE on reviews fail. Test in Task 1.
4. **Pseudonym leakage** — expected: feed/detail JSON contains no email, username or user id; pseudonym stable per user. Test in Task 4.
5. **Rating click failure** — expected: UI rolls back to the previous state and shows a hint; answer stays readable. E2E in Task 10.

---

## File Structure

Backend
- Create `backend/scripts/add_answer_quality.py`.
- Create `backend/models/answer_quality.py` (`AnswerRating`, `AnswerReview`); modify `backend/models/conversation.py` (`Message.evidence`, `Message.processing_ms`), `backend/models/__init__.py`.
- Modify `backend/api/routes/query.py` (persist signals, `message_id`, rating routes, conversation detail `rating`), `backend/api/schemas.py` (`QueryResponse.message_id`).
- Create `backend/core/admin_quality.py`, `backend/api/routes/admin_quality.py`; modify `backend/api/main.py`, `backend/core/admin_audit.py`, `backend/api/routes/admin.py` (stats `quality`).
- Modify `scripts/deploy_production.sh`, `.github/workflows/ci.yml`.
- Tests: create `backend/tests/test_admin_quality_postgres.py`; modify `backend/tests/test_integration.py`, `backend/tests/test_admin_audit.py`.

Frontend
- Modify `frontend/lib/admin-types.ts`, `frontend/lib/admin-i18n.ts`, `frontend/app/admin/layout.tsx`, `frontend/app/admin/page.tsx`, `frontend/app/admin/audit/page.tsx` (via `actionLabel` + target labels), `frontend/app/admin/admin.module.css`.
- Create `frontend/app/admin/quality/page.tsx`, `frontend/app/admin/quality/[id]/page.tsx`, `frontend/app/admin/quality/[id]/ReviewPanel.tsx`.
- Create `frontend/components/AnswerRating.tsx`; modify `frontend/lib/api.ts`, `frontend/hooks/useQuery.ts`, `frontend/components/ChatPanel.tsx`, `frontend/app/account/conversations/[conversationId]/page.tsx`, `frontend/lib/i18n.tsx`, `frontend/lib/legal-content.ts`.
- E2E: create `frontend/e2e/admin-quality.spec.ts`, `frontend/e2e/answer-rating.spec.ts`; modify `frontend/e2e/admin.spec.ts`, `frontend/playwright.config.ts`; baselines `admin-quality-ru-desktop.png`, `admin-quality-review-ka-mobile.png`, regenerated `admin-dashboard-ru-desktop.png`.
- Docs: `docs/DEVELOPMENT_MEMORY.md`, `docs/PRODUCTION_OPERATIONS.md`.

---

### Task 1: Schema script, ORM models, deploy pin

**Files:**
- Create: `backend/scripts/add_answer_quality.py`, `backend/models/answer_quality.py`
- Modify: `backend/models/conversation.py`, `backend/models/__init__.py`, `scripts/deploy_production.sh`, `.github/workflows/ci.yml`
- Create: `backend/tests/test_admin_quality_postgres.py`

**Interfaces:**
- Produces: `scripts.add_answer_quality.{DDL, contract_sha256() -> str, apply_schema(connection) -> dict}`; models `AnswerRating(id, message_id, user_id, value, comment, created_at, updated_at)`, `AnswerReview(id, message_id, reviewer_id, verdict, reasons, note, created_at)`; `Message.evidence` (JSON, nullable), `Message.processing_ms` (Integer, nullable); test fixture `database` in `test_admin_quality_postgres.py` yielding `(sessions, ids)` with `ids.admin_id`, `ids.user_id`, `ids.other_id`.

- [ ] **Step 1: Write failing PostgreSQL tests**

`backend/tests/test_admin_quality_postgres.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

From `backend/` (PG env): `rtk python -m pytest tests/test_admin_quality_postgres.py -q` → `ModuleNotFoundError: scripts.add_answer_quality` / `models.answer_quality`.

- [ ] **Step 3: Implement the schema script**

`backend/scripts/add_answer_quality.py`:

```python
#!/usr/bin/env python3
"""Install answer-quality signals, user ratings and append-only admin reviews; dry plan by default."""
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import inspect, text

from scripts.schema_contract_cli import ddl_contract_sha256, run

DDL = (
    "ALTER TABLE messages ADD COLUMN IF NOT EXISTS evidence JSONB",
    "ALTER TABLE messages ADD COLUMN IF NOT EXISTS processing_ms INTEGER",
    '''DO $$ BEGIN
         IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_messages_processing_ms_nonneg'
                        AND conrelid = 'messages'::regclass) THEN
           ALTER TABLE messages ADD CONSTRAINT ck_messages_processing_ms_nonneg
             CHECK (processing_ms IS NULL OR processing_ms >= 0);
         END IF;
       END $$''',
    "CREATE INDEX IF NOT EXISTS ix_messages_role_created ON messages (role, created_at)",
    '''CREATE TABLE IF NOT EXISTS answer_ratings (
        id UUID PRIMARY KEY,
        message_id UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        value SMALLINT NOT NULL CHECK (value IN (-1, 1)),
        comment TEXT CHECK (comment IS NULL OR char_length(comment) <= 1000),
        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        CONSTRAINT uq_answer_ratings_message UNIQUE (message_id)
    )''',
    "CREATE INDEX IF NOT EXISTS ix_answer_ratings_value ON answer_ratings (value)",
    '''CREATE TABLE IF NOT EXISTS answer_reviews (
        id UUID PRIMARY KEY,
        message_id UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
        reviewer_id UUID NOT NULL,
        verdict VARCHAR(16) NOT NULL CHECK (verdict IN ('correct', 'partial', 'wrong')),
        reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
        note TEXT CHECK (note IS NULL OR char_length(note) <= 2000),
        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
    )''',
    "CREATE INDEX IF NOT EXISTS ix_answer_reviews_message_created ON answer_reviews (message_id, created_at)",
    '''CREATE OR REPLACE FUNCTION reject_answer_review_mutation() RETURNS trigger
       LANGUAGE plpgsql AS $$ BEGIN
         IF TG_OP = 'DELETE' AND NOT EXISTS (SELECT 1 FROM messages WHERE id = OLD.message_id) THEN
           RETURN OLD;  -- cascade from a deleted message
         END IF;
         RAISE EXCEPTION 'answer reviews are append-only';
       END; $$''',
    "DROP TRIGGER IF EXISTS answer_reviews_immutable ON answer_reviews",
    '''CREATE TRIGGER answer_reviews_immutable BEFORE UPDATE OR DELETE
       ON answer_reviews FOR EACH ROW EXECUTE FUNCTION reject_answer_review_mutation()''',
    "DROP TRIGGER IF EXISTS answer_reviews_no_truncate ON answer_reviews",
    '''CREATE TRIGGER answer_reviews_no_truncate BEFORE TRUNCATE
       ON answer_reviews FOR EACH STATEMENT EXECUTE FUNCTION reject_answer_review_mutation()''',
    "ALTER TABLE answer_reviews ENABLE ALWAYS TRIGGER answer_reviews_immutable",
    "ALTER TABLE answer_reviews ENABLE ALWAYS TRIGGER answer_reviews_no_truncate",
)

EXPECTED = {
    "messages": {"evidence", "processing_ms"},
    "answer_ratings": {"id", "message_id", "user_id", "value", "comment", "created_at", "updated_at"},
    "answer_reviews": {"id", "message_id", "reviewer_id", "verdict", "reasons", "note", "created_at"},
}


def contract_sha256() -> str:
    return ddl_contract_sha256(DDL)


def apply_schema(connection) -> dict:
    for sql in DDL:
        connection.execute(text(sql))
    inspector = inspect(connection)
    missing = {table: sorted(cols - {c["name"] for c in inspector.get_columns(table)})
               for table, cols in EXPECTED.items()}
    triggers = connection.execute(text("""SELECT tgname, tgenabled FROM pg_trigger
        WHERE tgrelid = 'answer_reviews'::regclass
          AND tgname IN ('answer_reviews_immutable', 'answer_reviews_no_truncate')""")).all()
    if any(missing.values()) or sorted(triggers) != [("answer_reviews_immutable", "A"),
                                                     ("answer_reviews_no_truncate", "A")]:
        raise RuntimeError("Answer quality schema audit failed")
    return {"missing_columns": [], "append_only_triggers": True}


def main() -> int:
    return run(
        output_key="ANSWER_QUALITY_SCHEMA",
        label="Answer quality",
        contract=contract_sha256(),
        apply_schema=apply_schema,
    )


if __name__ == "__main__":
    raise SystemExit(main())
```

Note: the TRUNCATE trigger shares the function; in a statement trigger `TG_OP = 'TRUNCATE'` and `OLD` is unset, so the `IF TG_OP = 'DELETE'` guard must stay first (it short-circuits before touching `OLD`).

- [ ] **Step 4: ORM models**

`backend/models/answer_quality.py`:

```python
"""
User ratings of assistant answers and append-only admin reviews.

Installed by scripts/add_answer_quality.py; reviews are protected by triggers.
Types are portable (JSON, not JSONB/ARRAY) so the SQLite integration tests can create them.
"""
from uuid import uuid4

from sqlalchemy import JSON, Column, DateTime, ForeignKey, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from core.database import Base
from core.time_utils import utc_now


class AnswerRating(Base):
    __tablename__ = "answer_ratings"
    __table_args__ = (UniqueConstraint("message_id", name="uq_answer_ratings_message"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    message_id = Column(UUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    value = Column(SmallInteger, nullable=False)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)


class AnswerReview(Base):
    __tablename__ = "answer_reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    message_id = Column(UUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    # No FK: removing an admin account must not rewrite review history.
    reviewer_id = Column(UUID(as_uuid=True), nullable=False)
    verdict = Column(String(16), nullable=False)
    reasons = Column(JSON, nullable=False, default=list)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
```

In `backend/models/conversation.py` add to `Message` (import `Integer` from sqlalchemy):

```python
    evidence = Column(JSON, nullable=True)  # answer-quality signals (assistant messages only)
    processing_ms = Column(Integer, nullable=True)
```

In `backend/models/__init__.py` import and export `AnswerRating`, `AnswerReview`.

- [ ] **Step 5: Deploy pin and CI**

Compute the contract: from `backend/`, `rtk python -c "from scripts.add_answer_quality import contract_sha256; print(contract_sha256())"`.

In `scripts/deploy_production.sh`, right after the admin-audit block, add:

```bash
# Install answer-quality signals, ratings and append-only reviews before runtime writes to them.
ANSWER_QUALITY_SCHEMA_CONTRACT_SHA256="<printed value>"
docker compose run --rm --no-deps backend \
    python scripts/add_answer_quality.py \
        --apply \
        --expected-contract-sha256 "$ANSWER_QUALITY_SCHEMA_CONTRACT_SHA256"
```

In `.github/workflows/ci.yml`: add `scripts/add_answer_quality.py` to the `compileall` list next to `scripts/add_billing_review_journal.py`, and `tests/test_admin_quality_postgres.py` to the "Exercise PostgreSQL immutability and interval triggers" pytest list after `tests/test_admin_users_postgres.py`. If CI applies the admin-audit schema with its contract in a separate step, mirror that step for the new script (read the workflow to decide; the PG test fixture applies it itself, so a CI step is only needed if one exists for the audit script).

- [ ] **Step 6: Run tests**

PG: `rtk python -m pytest tests/test_admin_quality_postgres.py tests/test_admin_postgres.py tests/test_admin_users_postgres.py -q` → pass. Non-PG: `rtk python -m pytest tests/test_integration.py -q` → pass (SQLite still creates `messages` with the new portable columns).

- [ ] **Step 7: Commit** — `feat(quality): answer quality schema, rating and review models`.

---

### Task 2: Persist signals on answers and return `message_id`

**Files:**
- Modify: `backend/api/routes/query.py`, `backend/api/schemas.py`
- Modify: `backend/tests/test_integration.py` (add `AnswerRating` to `TEST_TABLES` after `Message`, new test)

**Interfaces:**
- Produces: `QueryResponse.message_id: Optional[UUID]`; stored `Message.evidence` = `{**result["evidence"], "retrieved_count": int}`, `Message.processing_ms` = int ms; `GET /query/conversations/{id}` messages gain `rating: {"value": int, "comment": str|None} | None` (assistant messages; `None` for user messages).

- [ ] **Step 1: Failing test** (append to `test_integration.py`, reusing the stub pattern of the existing authenticated-query test ~line 490):

```python
def test_answer_signals_are_stored_and_message_id_returned(client, monkeypatch):
    register_and_login(client, "signals-user")
    monkeypatch.setattr(query_routes, "check_and_count_question", lambda *_args: None)
    monkeypatch.setattr(query_routes.rag_pipeline, "process_query", lambda **_kwargs: {
        "response": "The VAT rate is grounded in Article 166.",
        "sources": [{"document_id": None, "title": "Tax Code of Georgia", "document_type": "law",
                     "url": "https://matsne.gov.ge/", "relevance": 0.99, "article_ref": "166"}],
        "retrieved_count": 1,
    })
    answer = client.post("/api/v1/query", json={"query": "What is the VAT rate?", "language": "en"})
    assert answer.status_code == 200
    message_id = answer.json()["message_id"]
    db = TestingSessionLocal()
    stored = db.get(Message, UUID(message_id))
    assert stored.role == "assistant"
    assert stored.evidence["status"] == "grounded" and stored.evidence["retrieved_count"] == 1
    assert isinstance(stored.processing_ms, int) and stored.processing_ms >= 0
    db.close()
    detail = client.get(f"/api/v1/query/conversations/{answer.json()['conversation_id']}").json()
    assistant = [m for m in detail["messages"] if m["role"] == "assistant"][0]
    assert assistant["rating"] is None
```

(Use the session factory and imports the file already has — read its top; if the factory is named differently, use that name.)

- [ ] **Step 2: Run** `rtk python -m pytest tests/test_integration.py -q -k signals` → KeyError `message_id`.

- [ ] **Step 3: Implement**

`api/schemas.py` → `QueryResponse`: add `message_id: Optional[UUID] = None`.

`api/routes/query.py`:
- imports: `from uuid import UUID, uuid4`; `from models import ..., AnswerRating`.
- When saving the assistant answer:

```python
        assistant_id = uuid4()
        db.add(Message(
            id=assistant_id,
            conversation_id=conversation.id,
            role="assistant",
            content=result["response"],
            sources=result.get("sources", []),
            evidence={**dict(result["evidence"]), "retrieved_count": int(result.get("retrieved_count", 0))},
            processing_ms=max(0, int((time.time() - start_time) * 1000)),
        ))
```

  (`result["evidence"]` may be a dict or a Pydantic model depending on `attach_evidence`; read `api/evidence.py` and convert with `.model_dump()` if it is a model.)
- add `"message_id": assistant_id` to `response_data`.
- In `get_conversation` (conversation detail), load ratings in one query and attach:

```python
    ratings = {r.message_id: r for r in db.query(AnswerRating).filter(
        AnswerRating.message_id.in_([m.id for m in messages if m.role == "assistant"])).all()}
    # inside the per-message dict:
    "rating": ({"value": ratings[message.id].value, "comment": ratings[message.id].comment}
               if message.id in ratings else None),
```

- [ ] **Step 4: Run** `rtk python -m pytest tests/test_integration.py -q` → all pass.

- [ ] **Step 5: Commit** — `feat(quality): store answer signals and return message_id`.

---

### Task 3: User rating API

**Files:**
- Modify: `backend/api/routes/query.py`
- Modify: `backend/tests/test_integration.py`

**Interfaces:**
- Produces: `PUT /api/v1/query/messages/{message_id}/rating` body `RatingRequest(value: Literal[1, -1], comment: Optional[str] max 1000)` → `{"value", "comment"}`; `DELETE` same path → 204; helper `rating_rate_limited(user_id) -> bool` (module-level, monkeypatchable); codes `message_not_found` (404), `not_assistant_message` (409), `rating_rate_limited` (429).

- [ ] **Step 1: Failing tests** (append to `test_integration.py`):

```python
def _ask(client, monkeypatch, username):
    register_and_login(client, username)
    monkeypatch.setattr(query_routes, "check_and_count_question", lambda *_args: None)
    monkeypatch.setattr(query_routes.rag_pipeline, "process_query", lambda **_kwargs: {
        "response": "Answer.", "sources": [], "retrieved_count": 0})
    payload = client.post("/api/v1/query", json={"query": "Question?", "language": "en"}).json()
    return payload["message_id"], payload["conversation_id"]


def test_rating_lifecycle(client, monkeypatch):
    message_id, conversation_id = _ask(client, monkeypatch, "rater")
    url = f"/api/v1/query/messages/{message_id}/rating"
    assert client.put(url, json={"value": 1}).json() == {"value": 1, "comment": None}
    assert client.put(url, json={"value": -1, "comment": "  wrong article  "}).json() == {
        "value": -1, "comment": "wrong article"}
    assert client.put(url, json={"value": -1, "comment": "   "}).json()["comment"] is None
    detail = client.get(f"/api/v1/query/conversations/{conversation_id}").json()
    assert [m["rating"] for m in detail["messages"] if m["role"] == "assistant"] == [{"value": -1, "comment": None}]
    assert client.delete(url).status_code == 204
    assert client.delete(url).status_code == 204
    assert client.put(url, json={"value": 2}).status_code == 422
    assert client.put(url, json={"value": 1, "comment": "x" * 1001}).status_code == 422


def test_rating_guards(client, monkeypatch):
    message_id, conversation_id = _ask(client, monkeypatch, "owner-user")
    detail = client.get(f"/api/v1/query/conversations/{conversation_id}").json()
    user_message_id = [m["id"] for m in detail["messages"] if m["role"] == "user"][0]
    response = client.put(f"/api/v1/query/messages/{user_message_id}/rating", json={"value": 1})
    assert response.status_code == 409 and response.json()["detail"]["code"] == "not_assistant_message"
    missing = client.put(f"/api/v1/query/messages/{uuid4()}/rating", json={"value": 1})
    assert missing.status_code == 404 and missing.json()["detail"]["code"] == "message_not_found"
    client.post("/api/v1/auth/logout")
    register_and_login(client, "intruder-user")
    foreign = client.put(f"/api/v1/query/messages/{message_id}/rating", json={"value": -1})
    assert foreign.status_code == 404
    monkeypatch.setattr(query_routes, "rating_rate_limited", lambda _uid: True)
    limited = client.delete(f"/api/v1/query/messages/{message_id}/rating")
    assert limited.status_code == 429 and limited.json()["detail"]["code"] == "rating_rate_limited"


def test_guest_cannot_rate(client):
    assert client.put(f"/api/v1/query/messages/{uuid4()}/rating", json={"value": 1}).status_code == 401
```

(If logout/login helpers differ, read the file and use its patterns; the point is a second user gets 404 on the first user's message. Note the rate-limit check happens before ownership lookup, so the last assertion holds for any user.)

- [ ] **Step 2: Run** `-k "rating or guest_cannot_rate"` → 404/405 failures.

- [ ] **Step 3: Implement** (in `api/routes/query.py`; imports `from datetime import datetime`, `from typing import Literal, Optional`, `from pydantic import BaseModel, Field`, `from core.admin_users import admin_error`, `from core.plans import _redis`):

```python
RATING_LIMIT_PER_HOUR = 60


class RatingRequest(BaseModel):
    value: Literal[1, -1]
    comment: Optional[str] = Field(default=None, max_length=1000)


def rating_rate_limited(user_id) -> bool:
    """True when the user exceeded RATING_LIMIT_PER_HOUR changes; no Redis → no limit."""
    client = _redis()
    if client is None:
        return False
    key = f"rating:{user_id}:{utc_now().strftime('%Y%m%d%H')}"
    try:
        count = client.incr(key)
        if count == 1:
            client.expire(key, 3600)
        return count > RATING_LIMIT_PER_HOUR
    except Exception:
        return False


def _owned_assistant_message(db: Session, user: User, message_id: UUID) -> Message:
    message = (db.query(Message).join(Conversation, Message.conversation_id == Conversation.id)
               .filter(Message.id == message_id, Conversation.user_id == user.id).first())
    if message is None:
        raise admin_error(404, "message_not_found", "Message not found")
    if message.role != "assistant":
        raise admin_error(409, "not_assistant_message", "Only assistant answers can be rated")
    return message


def _check_rating_limit(user: User) -> None:
    if rating_rate_limited(user.id):
        raise admin_error(429, "rating_rate_limited", "Too many rating changes, try again later")


@router.put(
    "/messages/{message_id}/rating",
    responses={
        404: {"description": "Message not found"},
        409: {"description": "Only assistant answers can be rated"},
        429: {"description": "Too many rating changes"},
    },
)
def rate_answer(message_id: UUID, body: RatingRequest, current_user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    _check_rating_limit(current_user)
    message = _owned_assistant_message(db, current_user, message_id)
    comment = (body.comment or "").strip() or None
    rating = db.query(AnswerRating).filter_by(message_id=message.id).first()
    if rating is None:
        rating = AnswerRating(message_id=message.id, user_id=current_user.id, value=body.value, comment=comment)
        db.add(rating)
    else:
        rating.value, rating.comment = body.value, comment
    db.commit()
    return {"value": rating.value, "comment": rating.comment}


@router.delete(
    "/messages/{message_id}/rating",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        404: {"description": "Message not found"},
        409: {"description": "Only assistant answers can be rated"},
        429: {"description": "Too many rating changes"},
    },
)
def unrate_answer(message_id: UUID, current_user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    _check_rating_limit(current_user)
    message = _owned_assistant_message(db, current_user, message_id)
    db.query(AnswerRating).filter_by(message_id=message.id).delete()
    db.commit()
```

(`core.plans._redis` is module-private; importing it is acceptable here — if lint/Sonar objects, add a public `redis_client()` alias in `core/plans.py` and use it.)

- [ ] **Step 4: Run** `rtk python -m pytest tests/test_integration.py -q` → pass.

- [ ] **Step 5: Commit** — `feat(quality): let signed-in users rate answers`.

---

### Task 4: Admin quality core and read endpoints

**Files:**
- Create: `backend/core/admin_quality.py`, `backend/api/routes/admin_quality.py`
- Modify: `backend/api/main.py`, `backend/tests/test_integration.py` (include router), `backend/tests/test_admin_quality_postgres.py`

**Interfaces:**
- Consumes: Task 1 models; `core.admin_users.{admin_error, escape_like, iso}`.
- Produces: `core.admin_quality.{REVIEW_REASONS, FLAGS, SLOW_MS, PERIOD_DAYS, pseudonym(user_id) -> str, FeedFilter (dataclass: period, rating, verdict, flags, q), answers_page(db, filt, limit, offset) -> dict, answer_detail(db, message_id, filt) -> dict, quality_summary(db, period) -> dict, down_unreviewed(db) -> int}`; router `api.routes.admin_quality.router` (prefix `/admin/quality`) with `list_answers`, `get_answer`, `get_summary`.

- [ ] **Step 1: Failing tests** (append to `test_admin_quality_postgres.py`):

```python
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
    assert names(q="100%") == ["liked 100%"] and names(q="LIKED") == ["liked 100%"]


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
    with sessions() as db:
        empty = routes.get_summary(period="7d", db=db) if False else None
    assert empty is None


def test_summary_empty_period_returns_nulls(database):
    sessions, _ = database
    with sessions() as db:
        s = routes.get_summary(period="7d", db=db)
    assert s["answers"] == 0 and s["down_share"] is None and s["median_processing_ms"] is None
```

Delete the meaningless three lines starting `with sessions() as db:\n        empty = ...` in `test_summary` when writing it (the empty case is covered by the next test). Also add `from fastapi import HTTPException` to the imports.

- [ ] **Step 2: Run** `-k "pseudonym or feed or detail or summary"` → import errors.

- [ ] **Step 3: Implement `core/admin_quality.py`**

```python
"""Admin answer-quality helpers: pseudonyms, the answer feed, detail and summary."""
import hashlib
import hmac
from dataclasses import dataclass, field
from datetime import timedelta
from statistics import median
from typing import Optional

from sqlalchemy import and_, func, or_, select, tuple_
from sqlalchemy.orm import Session, aliased

from core.admin_users import admin_error, escape_like, iso
from core.config import settings
from core.time_utils import utc_now
from models import AnswerRating, AnswerReview, Conversation, Message, User

REVIEW_REASONS = ("not_in_corpus", "wrong_version", "wrong_citation", "fabricated", "incomplete",
                  "language", "other")
VERDICTS = ("correct", "partial", "wrong")
FLAGS = ("no_precise_citation", "no_sources", "not_grounded", "slow", "no_evidence")
SLOW_MS = 30_000
PERIOD_DAYS = {"7d": 7, "30d": 30, "90d": 90, "all": None}
PREVIEW = 200


def pseudonym(user_id) -> str:
    digest = hmac.new(settings.SECRET_KEY.encode(), str(user_id).encode(), hashlib.sha256).hexdigest()
    return "U-" + digest[:6].upper()


@dataclass
class FeedFilter:
    period: str = "7d"
    rating: Optional[str] = None
    verdict: Optional[str] = None
    flags: list = field(default_factory=list)
    q: Optional[str] = None


Question = aliased(Message)


def _question_sq():
    return (select(Question.content)
            .where(Question.conversation_id == Message.conversation_id, Question.role == "user",
                   Question.created_at <= Message.created_at)
            .order_by(Question.created_at.desc()).limit(1).correlate(Message).scalar_subquery())


def _latest_verdict_sq():
    return (select(AnswerReview.verdict).where(AnswerReview.message_id == Message.id)
            .order_by(AnswerReview.created_at.desc(), AnswerReview.id.desc()).limit(1)
            .correlate(Message).scalar_subquery())


def _ev(key):
    return Message.evidence[key]


def _flag_condition(flag):
    has = Message.evidence.isnot(None)
    if flag == "no_evidence":
        return Message.evidence.is_(None)
    if flag == "slow":
        return Message.processing_ms > SLOW_MS
    if flag == "no_precise_citation":
        return and_(has, func.coalesce(_ev("has_precise_citation").as_boolean(), False).is_(False))
    if flag == "no_sources":
        return and_(has, func.coalesce(_ev("source_count").as_integer(), 0) == 0)
    return and_(has, func.coalesce(_ev("status").as_string(), "") != "grounded")  # not_grounded


def _conditions(filt: FeedFilter, now) -> list:
    conditions = [Message.role == "assistant"]
    days = PERIOD_DAYS[filt.period]
    if days is not None:
        conditions.append(Message.created_at >= now - timedelta(days=days))
    if filt.rating == "up":
        conditions.append(AnswerRating.value == 1)
    elif filt.rating == "down":
        conditions.append(AnswerRating.value == -1)
    elif filt.rating == "none":
        conditions.append(AnswerRating.id.is_(None))
    verdict = _latest_verdict_sq()
    if filt.verdict == "unreviewed":
        conditions.append(verdict.is_(None))
    elif filt.verdict:
        conditions.append(verdict == filt.verdict)
    for flag in filt.flags:
        conditions.append(_flag_condition(flag))
    term = (filt.q or "").strip()
    if term:
        conditions.append(_question_sq().ilike(f"%{escape_like(term)}%", escape="\\"))
    return conditions


def _base(columns, conditions):
    return (select(*columns).select_from(Message)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .outerjoin(AnswerRating, AnswerRating.message_id == Message.id)
            .where(*conditions))


def _flags_of(message) -> list:
    ev, flags = message.evidence, []
    if ev is None:
        return ["no_evidence"]
    if not ev.get("has_precise_citation"):
        flags.append("no_precise_citation")
    if not ev.get("source_count"):
        flags.append("no_sources")
    if ev.get("status") != "grounded":
        flags.append("not_grounded")
    if (message.processing_ms or 0) > SLOW_MS:
        flags.append("slow")
    return flags


def answers_page(db: Session, filt: FeedFilter, limit: int, offset: int) -> dict:
    now = utc_now()
    conditions = _conditions(filt, now)
    total = db.execute(_base([func.count()], conditions)).scalar_one()
    rows = db.execute(
        _base([Message, Conversation.user_id, _question_sq().label("question"),
               AnswerRating.value.label("rating"), _latest_verdict_sq().label("verdict")], conditions)
        .order_by(Message.created_at.desc(), Message.id.desc()).limit(limit).offset(offset)
    ).all()
    return {"total": total, "items": [{
        "message_id": str(m.id), "created_at": iso(m.created_at), "pseudonym": pseudonym(user_id),
        "question": (question or "")[:PREVIEW], "answer": m.content[:PREVIEW], "flags": _flags_of(m),
        "rating": rating, "verdict": verdict, "processing_ms": m.processing_ms,
    } for m, user_id, question, rating, verdict in rows]}


def _neighbors(db: Session, message, filt: FeedFilter) -> dict:
    conditions = _conditions(filt, utc_now())
    key = tuple_(Message.created_at, Message.id)
    current = tuple_(message.created_at, message.id)
    newer = db.execute(_base([Message.id], conditions + [key > current])
                       .order_by(Message.created_at.asc(), Message.id.asc()).limit(1)).scalar()
    older = db.execute(_base([Message.id], conditions + [key < current])
                       .order_by(Message.created_at.desc(), Message.id.desc()).limit(1)).scalar()
    return {"prev_id": str(newer) if newer else None, "next_id": str(older) if older else None}


def answer_detail(db: Session, message_id, filt: FeedFilter) -> dict:
    message = db.get(Message, message_id)
    if message is None or message.role != "assistant":
        raise admin_error(404, "message_not_found", "Message not found")
    conversation = db.get(Conversation, message.conversation_id)
    dialog = (db.query(Message).filter(Message.conversation_id == conversation.id)
              .order_by(Message.created_at, Message.id).all())
    rating = db.query(AnswerRating).filter_by(message_id=message.id).first()
    reviews = (db.query(AnswerReview, User.username)
               .outerjoin(User, User.id == AnswerReview.reviewer_id)
               .filter(AnswerReview.message_id == message.id)
               .order_by(AnswerReview.created_at.desc(), AnswerReview.id.desc()).all())
    return {
        "message": {"id": str(message.id), "created_at": iso(message.created_at), "content": message.content,
                    "sources": message.sources or [], "evidence": message.evidence,
                    "processing_ms": message.processing_ms, "flags": _flags_of(message)},
        "conversation": {"pseudonym": pseudonym(conversation.user_id), "messages": [
            {"id": str(m.id), "role": m.role, "content": m.content, "created_at": iso(m.created_at)}
            for m in dialog]},
        "rating": ({"value": rating.value, "comment": rating.comment, "updated_at": iso(rating.updated_at)}
                   if rating else None),
        "reviews": [{"verdict": r.verdict, "reasons": list(r.reasons or []), "note": r.note,
                     "created_at": iso(r.created_at), "reviewer": {"username": username}}
                    for r, username in reviews],
        "neighbors": _neighbors(db, message, filt),
    }


def down_unreviewed(db: Session) -> int:
    reviewed = select(AnswerReview.id).where(AnswerReview.message_id == AnswerRating.message_id).exists()
    return db.execute(select(func.count()).select_from(AnswerRating)
                      .where(AnswerRating.value == -1, ~reviewed)).scalar_one()


def quality_summary(db: Session, period: str) -> dict:
    now = utc_now()
    conditions = [Message.role == "assistant"]
    days = PERIOD_DAYS[period]
    if days is not None:
        conditions.append(Message.created_at >= now - timedelta(days=days))
    messages = db.execute(select(Message.id, Message.evidence, Message.processing_ms)
                          .where(*conditions)).all()
    ids = [m.id for m in messages]
    ratings = dict(db.execute(select(AnswerRating.message_id, AnswerRating.value)
                              .where(AnswerRating.message_id.in_(ids))).all()) if ids else {}
    latest = {}
    if ids:
        for review in db.query(AnswerReview).filter(AnswerReview.message_id.in_(ids)).order_by(
                AnswerReview.created_at, AnswerReview.id):
            latest[review.message_id] = review
    with_evidence = [m for m in messages if m.evidence is not None]
    no_cite = [m for m in with_evidence if not m.evidence.get("has_precise_citation")]
    timings = [m.processing_ms for m in messages if m.processing_ms is not None]
    rated, down = len(ratings), sum(1 for v in ratings.values() if v == -1)
    reasons = {reason: 0 for reason in REVIEW_REASONS}
    for review in latest.values():
        for reason in review.reasons or []:
            if reason in reasons:
                reasons[reason] += 1
    share = lambda part, whole: round(part / whole, 4) if whole else None  # noqa: E731
    return {
        "answers": len(messages), "rated": rated, "down": down, "down_share": share(down, rated),
        "reviewed": len(latest), "reviewed_share": share(len(latest), len(messages)),
        "verdicts": {v: sum(1 for r in latest.values() if r.verdict == v) for v in VERDICTS},
        "reasons": reasons,
        "no_precise_citation_share": share(len(no_cite), len(with_evidence)),
        "median_processing_ms": int(median(timings)) if timings else None,
        "down_unreviewed": down_unreviewed(db),
    }
```

Note: `quality_summary` loads the period's messages into Python. That is fine at current volume (hundreds–thousands of answers); add a comment saying so.

- [ ] **Step 4: Router read endpoints** — `backend/api/routes/admin_quality.py`:

```python
"""Admin answer quality: pseudonymous feed, detail, review, reveal and summary.
All endpoints require the admin role."""
from typing import List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from core.admin_quality import FeedFilter, answer_detail, answers_page, quality_summary
from core.database import get_db
from core.security import require_admin

router = APIRouter(prefix="/admin/quality", tags=["Admin"], dependencies=[Depends(require_admin)])

Period = Literal["7d", "30d", "90d", "all"]
RatingFilter = Literal["up", "down", "none"]
VerdictFilter = Literal["unreviewed", "correct", "partial", "wrong"]
Flag = Literal["no_precise_citation", "no_sources", "not_grounded", "slow", "no_evidence"]


def _filter(period, rating, verdict, flags, q) -> FeedFilter:
    return FeedFilter(period=period, rating=rating, verdict=verdict, flags=list(dict.fromkeys(flags or [])), q=q)


@router.get("/answers")
def list_answers(
    period: Period = "7d",
    rating: Optional[RatingFilter] = None,
    verdict: Optional[VerdictFilter] = None,
    flags: List[Flag] = Query(default=[]),
    q: Optional[str] = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    return answers_page(db, _filter(period, rating, verdict, flags, q), limit, offset)


@router.get("/answers/{message_id}", responses={404: {"description": "Message not found"}})
def get_answer(
    message_id: UUID,
    period: Period = "all",
    rating: Optional[RatingFilter] = None,
    verdict: Optional[VerdictFilter] = None,
    flags: List[Flag] = Query(default=[]),
    q: Optional[str] = Query(default=None, max_length=200),
    db: Session = Depends(get_db),
):
    return answer_detail(db, message_id, _filter(period, rating, verdict, flags, q))


@router.get("/summary")
def get_summary(period: Period = "7d", db: Session = Depends(get_db)):
    return quality_summary(db, period)
```

Include the router in `backend/api/main.py` (`admin_quality` in the routes import; `app.include_router(admin_quality.router, prefix=settings.API_PREFIX)  # Admin: answer quality`) and in `tests/test_integration.py`'s test app.

- [ ] **Step 5: Run** PG: `rtk python -m pytest tests/test_admin_quality_postgres.py -q` → pass; non-PG `tests/test_integration.py` → pass.

- [ ] **Step 6: Commit** — `feat(quality): pseudonymous admin answer feed, detail and summary`.

---

### Task 5: Review, reveal, journal actions, dashboard counter

**Files:**
- Modify: `backend/api/routes/admin_quality.py`, `backend/core/admin_audit.py`, `backend/api/routes/admin.py`, `backend/tests/test_admin_quality_postgres.py`, `backend/tests/test_admin_audit.py`, `backend/tests/test_integration.py`

**Interfaces:**
- Produces: `ReviewRequest(verdict: Literal[...], reasons: List[Literal[REVIEW_REASONS]] (max 7, unique), note: Optional[str] ≤2000, reason: Reason)`, `review_answer(message_id, body, admin, db)` → detail dict; `RevealRequest(reason: Reason)`, `reveal_user(message_id, body, admin, db)` → `{"user_id": str}`; `ADMIN_ACTIONS` + `answer.reviewed`, `user.identity_revealed`; `TARGET_TYPES` + `message`; `/admin/stats` gains `"quality": {"down_unreviewed": int}`.

- [ ] **Step 1: Failing tests** (append to `test_admin_quality_postgres.py`):

```python
from pydantic import ValidationError


def _journal(sessions):
    with sessions() as db:
        return db.query(AdminAuditLog).order_by(AdminAuditLog.created_at).all()


def test_review_appends_history_and_journals(database):
    sessions, ids = database
    with sessions() as db:
        _, _, a = _dialog(db, ids.user_id)
        db.commit()
        message_id = a.id
    body = routes.ReviewRequest(verdict="wrong", reasons=["wrong_citation", "fabricated"], note="cites 168",
                                reason="weekly review")
    with sessions() as db:
        routes.review_answer(message_id, body, admin=db.get(User, ids.admin_id), db=db)
    with sessions() as db:
        detail = routes.review_answer(message_id, routes.ReviewRequest(verdict="partial", reasons=[],
                                      reason="second look"), admin=db.get(User, ids.admin_id), db=db)
    assert [r["verdict"] for r in detail["reviews"]] == ["partial", "wrong"]
    assert detail["reviews"][1]["reviewer"]["username"] == "boss"
    entries = _journal(sessions)
    assert [e.action for e in entries] == ["answer.reviewed", "answer.reviewed"]
    assert entries[0].target_type == "message" and entries[0].target_id == str(message_id)
    assert entries[0].after == {"verdict": "wrong", "reasons": ["wrong_citation", "fabricated"]}


def test_review_validation():
    with pytest.raises(ValidationError):
        routes.ReviewRequest(verdict="wrong", reasons=["bogus"], reason="testing")
    with pytest.raises(ValidationError):
        routes.ReviewRequest(verdict="wrong", reasons=["other", "other"], reason="testing")
    with pytest.raises(ValidationError):
        routes.ReviewRequest(verdict="wrong", reasons=[], reason="no")


def test_review_rolls_back_when_journal_fails(database, monkeypatch):
    sessions, ids = database
    with sessions() as db:
        _, _, a = _dialog(db, ids.user_id)
        db.commit()
        message_id = a.id

    def broken(*_args, **_kwargs):
        raise RuntimeError("journal unavailable")

    monkeypatch.setattr(routes, "record_admin_action", broken)
    with sessions() as db:
        with pytest.raises(RuntimeError):
            routes.review_answer(message_id, routes.ReviewRequest(verdict="correct", reasons=[], reason="ok fine"),
                                 admin=db.get(User, ids.admin_id), db=db)
        db.rollback()
    with sessions() as db:
        assert db.query(AnswerReview).count() == 0


def test_reveal_returns_user_and_journals(database):
    sessions, ids = database
    with sessions() as db:
        _, _, a = _dialog(db, ids.user_id)
        db.commit()
        message_id = a.id
    with sessions() as db:
        result = routes.reveal_user(message_id, routes.RevealRequest(reason="needs follow-up"),
                                    admin=db.get(User, ids.admin_id), db=db)
    assert result == {"user_id": str(ids.user_id)}
    [entry] = _journal(sessions)
    assert entry.action == "user.identity_revealed" and entry.after == {"user_id": str(ids.user_id)}
    with sessions() as db:
        with pytest.raises(HTTPException) as exc:
            routes.reveal_user(uuid4(), routes.RevealRequest(reason="needs follow-up"),
                               admin=db.get(User, ids.admin_id), db=db)
    assert exc.value.detail["code"] == "message_not_found"


def test_stats_counts_down_unreviewed(database):
    from api.routes import admin as admin_routes
    sessions, ids = database
    with sessions() as db:
        _, _, a = _dialog(db, ids.user_id)
        db.add(AnswerRating(message_id=a.id, user_id=ids.user_id, value=-1))
        db.commit()
        assert admin_routes.system_stats(db)["quality"] == {"down_unreviewed": 1}
```

`system_stats` queries `documents`, `decision_facts`, `law_amendments`, `subscriptions`, `feedback`, `billing_checkouts` — add those models to this file's `TABLES` (as in `test_admin_postgres.py`: `Subscription, Payment, BillingCheckout, Feedback, Document, DecisionFacts, LawAmendment`) so the stats query runs.

In `test_integration.py` add:

```python
def test_non_admin_is_forbidden_from_answer_quality(client):
    register_and_login(client, "plain-quality-user")
    some_id = "00000000-0000-0000-0000-000000000001"
    assert client.get("/api/v1/admin/quality/answers").status_code == 403
    assert client.get(f"/api/v1/admin/quality/answers/{some_id}").status_code == 403
    assert client.get("/api/v1/admin/quality/summary").status_code == 403
    assert client.post(f"/api/v1/admin/quality/answers/{some_id}/review",
                       json={"verdict": "wrong", "reasons": [], "reason": "trying"}).status_code == 403
    assert client.post(f"/api/v1/admin/quality/answers/{some_id}/reveal-user",
                       json={"reason": "trying"}).status_code == 403
```

Update `tests/test_admin_audit.py` if it asserts the exact `ADMIN_ACTIONS`/`TARGET_TYPES` sets.

- [ ] **Step 2: Run** → failures on missing `ReviewRequest`, `quality` key.

- [ ] **Step 3: Implement**

`core/admin_audit.py`: add `"answer.reviewed", "user.identity_revealed"` to `ADMIN_ACTIONS` and `"message"` to `TARGET_TYPES`.

Append to `api/routes/admin_quality.py` (imports: `from pydantic import BaseModel, Field, field_validator`; `from core.admin_audit import record_admin_action`; `from core.admin_users import Reason, admin_error`; `from core.admin_quality import REVIEW_REASONS`; `from models import AnswerReview, Conversation, Message, User`):

```python
ReviewReason = Literal["not_in_corpus", "wrong_version", "wrong_citation", "fabricated", "incomplete",
                       "language", "other"]


class ReviewRequest(BaseModel):
    verdict: Literal["correct", "partial", "wrong"]
    reasons: List[ReviewReason] = Field(default_factory=list, max_length=7)
    note: Optional[str] = Field(default=None, max_length=2000)
    reason: Reason

    @field_validator("reasons")
    @classmethod
    def unique_reasons(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("reasons must be unique")
        return value


class RevealRequest(BaseModel):
    reason: Reason


def _assistant_message(db: Session, message_id: UUID) -> Message:
    message = db.get(Message, message_id)
    if message is None or message.role != "assistant":
        raise admin_error(404, "message_not_found", "Message not found")
    return message


@router.post("/answers/{message_id}/review", responses={404: {"description": "Message not found"}})
def review_answer(message_id: UUID, body: ReviewRequest, admin: User = Depends(require_admin),
                  db: Session = Depends(get_db)):
    message = _assistant_message(db, message_id)
    note = (body.note or "").strip() or None
    db.add(AnswerReview(message_id=message.id, reviewer_id=admin.id, verdict=body.verdict,
                        reasons=list(body.reasons), note=note))
    db.flush()
    record_admin_action(db, actor=admin, action="answer.reviewed", target_type="message", target_id=message.id,
                        after={"verdict": body.verdict, "reasons": list(body.reasons)}, reason=body.reason)
    db.commit()
    return answer_detail(db, message.id, FeedFilter(period="all"))


@router.post("/answers/{message_id}/reveal-user", responses={404: {"description": "Message not found"}})
def reveal_user(message_id: UUID, body: RevealRequest, admin: User = Depends(require_admin),
                db: Session = Depends(get_db)):
    message = _assistant_message(db, message_id)
    user_id = db.get(Conversation, message.conversation_id).user_id
    record_admin_action(db, actor=admin, action="user.identity_revealed", target_type="message",
                        target_id=message.id, after={"user_id": str(user_id)}, reason=body.reason)
    db.commit()
    return {"user_id": str(user_id)}
```

`api/routes/admin.py` `system_stats`: import `from core.admin_quality import down_unreviewed` and add `"quality": {"down_unreviewed": down_unreviewed(db)}` to the returned dict. In `test_admin_postgres.py` the existing stats test fixture must have `answer_ratings`/`answer_reviews` tables — add `AnswerRating, AnswerReview` to its `TABLES` (and apply nothing else; plain `create_all` is enough there).

- [ ] **Step 4: Run** PG: `rtk python -m pytest tests/test_billing_provider_postgres.py tests/test_admin_postgres.py tests/test_admin_users_postgres.py tests/test_admin_quality_postgres.py tests/test_billing_review_postgres.py -q`; non-PG: `rtk python -m pytest tests/test_admin_audit.py tests/test_public_config.py tests/test_integration.py tests/test_plan_quotas.py -q` → all pass.

- [ ] **Step 5: Commit** — `feat(quality): journaled answer reviews, audited user reveal, dashboard counter`.

---

### Task 6: Admin frontend foundation — types, copy, nav, dashboard, audit labels

**Files:**
- Modify: `frontend/lib/admin-types.ts`, `frontend/lib/admin-i18n.ts`, `frontend/app/admin/layout.tsx`, `frontend/app/admin/page.tsx`, `frontend/app/admin/audit/page.tsx`

**Interfaces:**
- Produces: types `QualityFlag`, `QualityRow`, `QualityPage`, `QualityDetail`, `QualitySummary`, `AdminStats.quality`; constants `QUALITY_FLAGS`, `REVIEW_REASONS`, `VERDICTS`; copy `c.nav.quality`, `c.quality.*`, `c.dashboard.qualityDown(n)`, new `ADMIN_ACTIONS` entries and `c.audit.targets.message`; nav item `{ key: 'quality', href: '/admin/quality' }` between users and payments.

- [ ] **Step 1: Types** (append to `admin-types.ts`):

```ts
export const QUALITY_FLAGS = ['no_precise_citation', 'no_sources', 'not_grounded', 'slow', 'no_evidence'] as const;
export type QualityFlag = (typeof QUALITY_FLAGS)[number];
export const REVIEW_REASONS = ['not_in_corpus', 'wrong_version', 'wrong_citation', 'fabricated', 'incomplete',
  'language', 'other'] as const;
export type ReviewReason = (typeof REVIEW_REASONS)[number];
export const VERDICTS = ['correct', 'partial', 'wrong'] as const;
export type Verdict = (typeof VERDICTS)[number];

export interface QualityRow {
  message_id: string; created_at: string | null; pseudonym: string; question: string; answer: string;
  flags: QualityFlag[]; rating: 1 | -1 | null; verdict: Verdict | null; processing_ms: number | null;
}
export interface QualityPage { total: number; items: QualityRow[] }

export interface QualityEvidence {
  status?: string; basis?: string; coverage?: string; question_class?: string | null; source_count?: number;
  official_sources_only?: boolean; has_precise_citation?: boolean; has_official_provision_link?: boolean;
  retrieved_count?: number;
}
export interface QualityDetail {
  message: {
    id: string; created_at: string | null; content: string;
    sources: { title?: string; url?: string | null; article_ref?: string | null }[];
    evidence: QualityEvidence | null; processing_ms: number | null; flags: QualityFlag[];
  };
  conversation: { pseudonym: string; messages: { id: string; role: 'user' | 'assistant'; content: string; created_at: string | null }[] };
  rating: { value: 1 | -1; comment: string | null; updated_at: string | null } | null;
  reviews: { verdict: Verdict; reasons: ReviewReason[]; note: string | null; created_at: string | null; reviewer: { username: string | null } }[];
  neighbors: { prev_id: string | null; next_id: string | null };
}
export interface QualitySummary {
  answers: number; rated: number; down: number; down_share: number | null; reviewed: number;
  reviewed_share: number | null; verdicts: Record<Verdict, number>; reasons: Record<ReviewReason, number>;
  no_precise_citation_share: number | null; median_processing_ms: number | null; down_unreviewed: number;
}
```

Add `quality: { down_unreviewed: number }` to `AdminStats`.

- [ ] **Step 2: Copy** (`admin-i18n.ts`): add `'answer.reviewed'`, `'user.identity_revealed'` to `ADMIN_ACTIONS`; `'message_not_found'` to `ADMIN_ERROR_CODES`. RU (EN in brackets; KA via the skill):

- `nav.quality`: 'Качество ответов' (Answer quality)
- `audit.actions['answer.reviewed']`: 'Разметка ответа' (Answer review); `['user.identity_revealed']`: 'Раскрытие пользователя' (User revealed); `audit.targets.message`: 'Ответ' (Answer)
- `errors.message_not_found`: 'Ответ не найден.' (Answer not found.)
- `dashboard.qualityDown(n)`: `Ответы с 👎 без разметки: ${n}` (`Thumbs-down answers awaiting review: ${n}`)
- new section `quality`:

```ts
  quality: {
    title: 'Качество ответов', subtitle: 'Ответы пользователям, их оценки и разметка. Пользователи скрыты под псевдонимами.',
    periods: { '7d': '7 дней', '30d': '30 дней', '90d': '90 дней', all: 'Всё время' },
    period: 'Период', ratingFilter: 'Оценка', verdictFilter: 'Вердикт', search: 'Поиск по вопросу',
    ratings: { up: '👍', down: '👎', none: 'Без оценки' },
    verdictFilters: { unreviewed: 'Без разметки', correct: 'Верно', partial: 'Частично', wrong: 'Неверно' },
    verdicts: { correct: 'Верно', partial: 'Частично', wrong: 'Неверно' },
    flags: { no_precise_citation: 'Нет точной ссылки', no_sources: 'Нет источников', not_grounded: 'Не подтверждён',
             slow: 'Долгий ответ', no_evidence: 'Нет данных' },
    reasons: { not_in_corpus: 'Нет в корпусе', wrong_version: 'Не та редакция закона', wrong_citation: 'Ошибка ссылки',
               fabricated: 'Выдумано', incomplete: 'Неполно', language: 'Язык', other: 'Другое' },
    queues: { downUnreviewed: '👎 без разметки', noCitation: 'Без точной ссылки', wrong: 'Неверные' },
    reset: 'Сбросить фильтры', notFound: 'Ничего не найдено.',
    when: 'Когда', user: 'Пользователь', question: 'Вопрос', signals: 'Признаки', rating: 'Оценка', verdict: 'Вердикт',
    summary: { downShare: 'Доля 👎', reviewed: 'Размечено', wrongShare: 'Неверных среди размеченных',
               noCitation: 'Без точной ссылки', median: 'Медианное время ответа',
               ofRated: (n: string) => `из ${n} оценённых`, ofAnswers: (n: string) => `из ${n} ответов` },
    seconds: (s: string) => `${s} с`,
    back: '← К ленте', prev: '← Предыдущий', next: 'Следующий →', reviewing: 'Разбираемый ответ',
    sources: 'Источники', evidence: 'Признаки', noEvidence: 'Нет данных: ответ старше этапа сохранения признаков.',
    ev: { status: 'Статус', coverage: 'Покрытие', questionClass: 'Класс вопроса', sourceCount: 'Источников',
          precise: 'Точная ссылка', time: 'Время ответа', retrieved: 'Найдено фрагментов' },
    userRating: 'Оценка пользователя', noRating: 'Пользователь не оценивал ответ.',
    review: 'Разметка', reviewReasons: 'Причины', note: 'Заметка', saveReview: 'Сохранить разметку',
    reviewSaved: 'Разметка сохранена.', history: 'История разметки', noReviews: 'Ответ ещё не размечен.',
    revealUser: 'Открыть клиента', revealTitle: 'Открыть данные клиента?',
    revealDescription: 'Действие попадёт в журнал: кто, когда и по какому ответу раскрыл пользователя.',
    you: 'Пользователь', assistant: 'Ответ',
  },
```

EN equivalents: 'Answer quality'; 'Answers to users, their ratings and reviews. Users are shown as pseudonyms.'; periods '7 days', '30 days', '90 days', 'All time'; 'Period', 'Rating', 'Verdict', 'Search questions'; ratings none 'Not rated'; verdictFilters 'Not reviewed', 'Correct', 'Partial', 'Wrong'; flags 'No precise citation', 'No sources', 'Not grounded', 'Slow answer', 'No data'; reasons 'Not in corpus', 'Wrong law version', 'Wrong citation', 'Fabricated', 'Incomplete', 'Language', 'Other'; queues '👎 not reviewed', 'No precise citation', 'Wrong'; 'Reset filters', 'Nothing found.'; columns 'When', 'User', 'Question', 'Signals', 'Rating', 'Verdict'; summary 'Thumbs-down share', 'Reviewed', 'Wrong among reviewed', 'No precise citation', 'Median answer time', `of ${n} rated`, `of ${n} answers`; `${s} s`; '← Back to feed', '← Previous', 'Next →', 'Answer under review', 'Sources', 'Signals', 'No data: the answer predates signal storage.'; ev 'Status', 'Coverage', 'Question class', 'Sources', 'Precise citation', 'Answer time', 'Retrieved chunks'; 'User rating', 'The user has not rated this answer.'; 'Review', 'Reasons', 'Note', 'Save review', 'Review saved.', 'Review history', 'Not reviewed yet.'; 'Open client', 'Open client details?', 'This is logged: who revealed the user, when and from which answer.'; 'User', 'Answer'.

Type `quality.flags` with `satisfies Record<QualityFlag, string>`, `quality.reasons` with `satisfies Record<ReviewReason, string>`, `quality.verdicts` with `satisfies Record<Verdict, string>` (import the types from `admin-types.ts`).

- [ ] **Step 3: Nav, dashboard, audit**

- `app/admin/layout.tsx`: add `{ key: 'quality', href: '/admin/quality', icon: <a radix icon e.g. CheckCircledIcon> }` after users.
- `app/admin/page.tsx` `buildAttention`: when `stats.quality.down_unreviewed > 0` push an item linking to `/admin/quality?rating=down&verdict=unreviewed` with `c.dashboard.qualityDown(formatNumber(n, locale))` (follow the existing items' shape exactly).
- `app/admin/audit/page.tsx`: target labels already come from `c.audit.targets` — confirm `message` renders via it; action filter uses `ADMIN_ACTIONS` so the two new actions appear automatically.

- [ ] **Step 4: Verify** from `frontend/`: `rtk npm run type-check`, `rtk npx eslint lib/admin-types.ts lib/admin-i18n.ts app/admin/layout.tsx app/admin/page.tsx app/admin/audit/page.tsx`, `rtk npm run check:admin-styles`.

- [ ] **Step 5: Commit** — `feat(quality): admin quality types, copy, nav and dashboard counter`.

---

### Task 7: Admin feed page `/admin/quality`

**Files:**
- Create: `frontend/app/admin/quality/page.tsx`
- Modify: `frontend/app/admin/admin.module.css` (only if a flag-chip style is missing; reuse `.badge`/`.pills`/`.chip` first)

**Interfaces:**
- Consumes: Task 6 types/copy; `useAdminFetch`, `PageHeader`, `StatTile`, `DataTable`, `Pagination`, `Badge`.
- Produces: URL params `period, rating, verdict, flags (repeated), q, offset`; review link `/admin/quality/<id>` + `?back=<encodeURIComponent('?' + listQuery)>` when the list query is non-empty.

- [ ] **Step 1: Write the page**

Follow `frontend/app/admin/users/page.tsx` (Task 7 of stage 2) as the pattern for URL state: `pick()` validation, `update(patch)` with `router.replace`, offset reset, render-time draft sync with the `pushedQ` state for the 300 ms search debounce, `Suspense` wrapper. Differences:

```tsx
const PERIODS = ['7d', '30d', '90d', 'all'] as const;
const RATINGS = ['up', 'down', 'none'] as const;
const VERDICT_FILTERS = ['unreviewed', 'correct', 'partial', 'wrong'] as const;
const LIMIT = 50;

// flags: params.getAll('flags').filter((f): f is QualityFlag => (QUALITY_FLAGS as readonly string[]).includes(f))
// toggling a flag rewrites all `flags` entries: next.delete('flags'); selected.forEach((f) => next.append('flags', f));
// period default is '7d' and is omitted from the URL when '7d'.

const listQuery = new URLSearchParams({ limit: String(LIMIT), offset: String(offset), period });
// append rating/verdict/q/flags when set
const { data, error, loading, reload } = useAdminFetch<QualityPage>(`/api/v1/admin/quality/answers?${listQuery}`);
const summary = useAdminFetch<QualitySummary>(`/api/v1/admin/quality/summary?period=${period}`).data;
```

Layout:
- `PageHeader` with `c.quality.title` / `c.quality.subtitle`.
- Summary tiles (`styles.tiles`) when `summary` is loaded:
  - `downShare`: value as percent (`formatNumber(Math.round(share*100), locale) + '%'`, `c.common.dash` when null), detail `ofRated(rated)`;
  - `reviewed`: `reviewed` with detail `ofAnswers(answers)`;
  - `wrongShare`: `verdicts.wrong / reviewed` as percent;
  - `noCitation`: share as percent;
  - `median`: `seconds((ms/1000).toFixed(1))` or dash.
- Period select + three queue buttons (`styles.chip`, `aria-pressed` when active) that set exactly `{rating:'down', verdict:'unreviewed'}`, `{flags:['no_precise_citation']}`, `{verdict:'wrong'}` (clearing the others).
- Filter bar: rating select, verdict select, flag checkboxes (labels wrap inputs), search input (`type="search"`, `aria-label={c.quality.search}`), reset when filtered.
- `DataTable` columns:
  - when: `formatDateTime`;
  - user: `<span className={styles.mono}>{pseudonym}</span>`;
  - question: link to the review page;
  - signals: one `Badge tone="warning"` per flag with `c.quality.flags[f]`, `c.common.dash` when none;
  - rating: '👍' / '👎' / dash;
  - verdict: `Badge` (`correct`→success, `partial`→warning, `wrong`→error), dash when null.

  Extract small components (`FlagBadges`, `VerdictBadge`) instead of nested ternaries.
- `emptyText={filtered ? c.quality.notFound : undefined}` plus reset button; `Pagination` with `update({ offset })`.

- [ ] **Step 2: Verify** — `rtk npm run type-check`; `rtk npx eslint app/admin/quality/page.tsx`; `rtk npm run check:admin-styles`.

- [ ] **Step 3: Commit** — `feat(quality): admin answer feed with summary, queues and URL filters`.

---

### Task 8: Admin review page `/admin/quality/[id]`

**Files:**
- Create: `frontend/app/admin/quality/[id]/page.tsx`, `frontend/app/admin/quality/[id]/ReviewPanel.tsx`
- Modify: `frontend/app/admin/admin.module.css` (dialog thread classes)

**Interfaces:**
- Consumes: `QualityDetail`; `useAdminFetch`, `adminSend`, `errorText`, `ConfirmDialog`, `AdminState`, `Badge`; `POST /api/v1/admin/quality/answers/{id}/review` body `{verdict, reasons, note?, reason}` → `QualityDetail`; `POST .../reveal-user` `{reason}` → `{user_id}`.
- Produces: e2e anchors (copy strings): headings `c.quality.evidence`, `c.quality.userRating`, `c.quality.review`, `c.quality.history`; buttons `c.quality.saveReview`, `c.quality.revealUser`, verdict buttons `c.quality.verdicts.*` with `aria-pressed`; reason checkboxes labelled `c.quality.reasons.*`.

- [ ] **Step 1: CSS** (append):

```css
.reviewGrid { display: grid; gap: 1rem; grid-template-columns: minmax(0, 3fr) minmax(0, 2fr); }
@media (max-width: 900px) { .reviewGrid { grid-template-columns: minmax(0, 1fr); } }
.thread { display: grid; gap: 0.75rem; }
.bubble { padding: 0.75rem 1rem; border-radius: var(--radius); border: 1px solid hsl(var(--border)); overflow-wrap: anywhere; white-space: pre-wrap; }
.bubbleFocus { border-color: hsl(var(--primary)); box-shadow: 0 0 0 1px hsl(var(--primary)); }
.bubbleRole { display: block; font-size: 0.75rem; color: hsl(var(--muted-foreground)); margin-bottom: 0.25rem; }
```

(Check how existing admin CSS references tokens — stage 2 found they are HSL channels, so `hsl(var(--x))` — and match it.)

- [ ] **Step 2: `page.tsx`**

- `useParams<{ id: string }>()`; `back = useSearchParams().get('back')`; `backQuery = back && back.startsWith('?') ? back : ''`.
- Detail URL: `/api/v1/admin/quality/answers/${id}${backQuery ? backQuery.replace(/^\?/, '?') : ''}`. The backend accepts the same filter params; drop `limit`/`offset` from the forwarded query (`new URLSearchParams(backQuery)` → delete both → toString).
- `useAdminFetch<QualityDetail>(url)`. Treat `status` 404 or 422 as not found (`AdminState kind="empty"` + back link). Show error/retry otherwise. Guard against stale data with `data.message.id !== id` while loading.
- Header: back link (`/admin/quality${backQuery}`), prev/next links built as `/admin/quality/${neighbors.prev_id}${backQuery ? `?back=${encodeURIComponent(backQuery)}` : ''}`.
- Left column: `.thread` with one `.bubble` per message (`.bubbleFocus` on the reviewed one, role label `c.quality.you` / `c.quality.assistant`), then the sources list (title + article_ref, link when url).
- Right column: `<ReviewPanel detail={data} onUpdated={setData} />`.

- [ ] **Step 3: `ReviewPanel.tsx`**

- **Evidence** section: if `message.evidence` is null, show `c.quality.noEvidence`. Otherwise a `dl.facts` with status, coverage, question_class, source_count, precise (`c.common.yes/no`), time (`seconds`), retrieved. Then flag badges.
- **User rating** section: 👍/👎 and comment (`styles.prewrap`), or `c.quality.noRating`.
- **Review form:**
  - verdict buttons: three `button`s with `aria-pressed` (state `verdict: Verdict | null`);
  - reason checkboxes over `REVIEW_REASONS`;
  - note `textarea` (maxLength 2000);
  - journal reason `textarea` (label `c.common.reasonRequired`, maxLength 1000);
  - submit button `c.quality.saveReview`, disabled until `verdict && reason.trim().length >= 3`.

  On submit: `adminSend<QualityDetail>(.../review, 'POST', { verdict, reasons, note: note.trim() || undefined, reason: reason.trim() })`, then `onUpdated(result)`, reset the form and show the notice `c.quality.reviewSaved`. On error show `errorText(c, e)` in a `role="alert"` paragraph.
- **History:** list of reviews (`formatDateTime`, reviewer username, `VerdictBadge`, reason labels, note), or `c.quality.noReviews`.
- **Reveal:**
  - a `c.quality.revealUser` button opens `ConfirmDialog` with `title={c.quality.revealTitle}`, `description={c.quality.revealDescription}` and `reasonRequired`;
  - `onConfirm`: `const { user_id } = await adminSend<{ user_id: string }>(.../reveal-user, 'POST', { reason })`, then `router.push(`/admin/users/${user_id}`)`;
  - wrap errors with `errorText`.

- [ ] **Step 4: Verify** — type-check, eslint on both files, check:admin-styles, test:admin-styles.

- [ ] **Step 5: Commit** — `feat(quality): admin answer review page with history and audited reveal`.

---

### Task 9: Site rating buttons and privacy policy

**Files:**
- Create: `frontend/components/AnswerRating.tsx`
- Modify: `frontend/lib/api.ts`, `frontend/hooks/useQuery.ts` (type only), `frontend/components/ChatPanel.tsx`, `frontend/app/account/conversations/[conversationId]/page.tsx`, `frontend/lib/i18n.tsx`, `frontend/lib/legal-content.ts`

**Interfaces:**
- Consumes: `PUT/DELETE /api/v1/query/messages/{id}/rating`; `QueryResponse.message_id`; conversation detail `rating`.
- Produces: `AnswerRating({ messageId, initial }: { messageId: string; initial?: { value: 1 | -1; comment: string | null } | null })`; e2e anchors: buttons with `aria-label` = `t('rating.up')` / `t('rating.down')` and `aria-pressed`; textarea labelled `t('rating.comment_label')`; button `t('rating.comment_send')`; text `t('rating.thanks')`; error `t('rating.error')`.

- [ ] **Step 1: Types** — `lib/api.ts` `QueryResponse`: add `message_id?: string | null;`. The conversation page's `ConversationMessage`: add `id: string; rating?: { value: 1 | -1; comment: string | null } | null;` (the backend already returns `id`).

- [ ] **Step 2: Site copy** — add to `DICT` in `lib/i18n.tsx` (`{ ru, ka, en }` entries; KA via the skill):

| key | ru | en |
|---|---|---|
| `rating.up` | Полезный ответ | Helpful answer |
| `rating.down` | Неточный ответ | Inaccurate answer |
| `rating.thanks` | Спасибо, это поможет улучшить ответы | Thank you, this helps us improve answers |
| `rating.comment_label` | Что не так? | What was wrong? |
| `rating.comment_send` | Отправить | Send |
| `rating.error` | Не удалось сохранить оценку. Попробуйте ещё раз. | Could not save your rating. Please try again. |
| `rating.rate_limited` | Слишком много оценок подряд. Попробуйте позже. | Too many ratings in a row. Try again later. |

- [ ] **Step 3: `components/AnswerRating.tsx`**

```tsx
'use client';

import { useState } from 'react';
import { authFetch } from '@/lib/auth';
import { useT } from '@/lib/i18n';

type Rating = { value: 1 | -1; comment: string | null } | null;

export function AnswerRating({ messageId, initial = null }: { messageId: string; initial?: Rating }) {
  const { t } = useT();
  const [rating, setRating] = useState<Rating>(initial);
  const [comment, setComment] = useState(initial?.comment ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const url = `/api/v1/query/messages/${messageId}/rating`;

  const save = async (next: Rating) => {
    const previous = rating;
    setRating(next);
    setBusy(true);
    setError(null);
    try {
      const res = next
        ? await authFetch(url, { method: 'PUT', body: JSON.stringify({ value: next.value, comment: next.comment || undefined }) })
        : await authFetch(url, { method: 'DELETE' });
      if (!res.ok) throw Object.assign(new Error('rating'), { status: res.status });
    } catch (e) {
      setRating(previous);
      setError(t((e as { status?: number }).status === 429 ? 'rating.rate_limited' : 'rating.error'));
    } finally {
      setBusy(false);
    }
  };

  const toggle = (value: 1 | -1) => save(rating?.value === value ? null : { value, comment: value === -1 ? comment.trim() || null : null });

  return (
    <div className="mt-4 flex flex-col gap-2 border-t border-white/10 pt-3 text-xs text-white/60">
      <div className="flex items-center gap-2">
        {([1, -1] as const).map((value) => (
          <button key={value} type="button" disabled={busy} aria-pressed={rating?.value === value}
            aria-label={t(value === 1 ? 'rating.up' : 'rating.down')}
            className={`rounded-full border px-3 py-1 text-base transition ${rating?.value === value
              ? 'border-primary bg-primary/20 text-white' : 'border-white/15 hover:border-white/40'}`}
            onClick={() => toggle(value)}>
            {value === 1 ? '👍' : '👎'}
          </button>
        ))}
        {rating && <span>{t('rating.thanks')}</span>}
      </div>
      {rating?.value === -1 && (
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
          <label className="flex min-w-0 flex-1 flex-col gap-1">
            {t('rating.comment_label')}
            <textarea maxLength={1000} rows={2} value={comment} onChange={(e) => setComment(e.target.value)}
              className="rounded-xl border border-white/15 bg-white/5 p-2 text-sm text-white/90" />
          </label>
          <button type="button" disabled={busy} className="rounded-full border border-white/20 px-4 py-2 text-sm text-white/90 hover:border-white/40"
            onClick={() => save({ value: -1, comment: comment.trim() || null })}>
            {t('rating.comment_send')}
          </button>
        </div>
      )}
      {error && <p role="alert" className="text-red-300">{error}</p>}
    </div>
  );
}
```

Match the class vocabulary to the surrounding chat markup (read `ChatPanel.tsx`/`globals.css`). The red error class should use the site's existing error token class if one exists.

- [ ] **Step 4: Wire it in**

- `ChatPanel.tsx`: inside the answer card, after the sources block, render `{data.message_id && isLoggedIn() && <AnswerRating key={data.message_id} messageId={data.message_id} />}` (import `isLoggedIn` from `@/lib/auth`).
- Conversation page: for `message.role === 'assistant'`, render `<AnswerRating messageId={message.id} initial={message.rating ?? null} />` below the sources.

- [ ] **Step 5: Privacy policy** (`lib/legal-content.ts`, privacy document, RU/KA/EN):
  - **«Цели и основания»:** append the sentence (RU) «Мы также проверяем и улучшаем качество и точность ответов: уполномоченный администратор может выборочно просматривать вопросы и ответы. При таком разборе личность пользователя по умолчанию скрыта, а её раскрытие фиксируется в журнале.» EN: "We also check and improve the quality and accuracy of answers: an authorized administrator may review selected questions and answers. During such review the user's identity is hidden by default, and revealing it is recorded in a log."
  - **«Какие данные обрабатываем»:** extend the questions bullet with «оценки ответов и комментарии к ним» / "answer ratings and their comments".
  - **Version:** set the privacy `updated` string to «Версия 2026-10-12 · действует с даты публикации» / "Version 2026-10-12 · effective on publication" (and KA via the skill). Gela confirms the final wording and effective date before merge; the PR description must say so.
  - Do not change `LEGAL_TERMS_VERSION` (terms of service are unchanged).

- [ ] **Step 6: Verify** — type-check, `rtk npm run lint`, check:admin-styles.

- [ ] **Step 7: Commit** — `feat(quality): rate answers on the site; privacy policy covers answer review`.

---

### Task 10: E2E, baselines, docs, full verification

**Files:**
- Create: `frontend/e2e/admin-quality.spec.ts`, `frontend/e2e/answer-rating.spec.ts`
- Modify: `frontend/e2e/admin.spec.ts` (stats fixture gets `quality: { down_unreviewed: 3 }`; nav PAGES table gains `/admin/quality` with a ready marker), `frontend/playwright.config.ts` (`testMatch` += both new specs)
- Baselines: `admin-quality-ru-desktop.png`, `admin-quality-review-ka-mobile.png`, regenerated `admin-dashboard-ru-desktop.png`
- Modify: `docs/DEVELOPMENT_MEMORY.md`, `docs/PRODUCTION_OPERATIONS.md`

- [ ] **Step 1: `admin-quality.spec.ts`** — self-contained mocks in the style of `admin-users.spec.ts` (copy its `json`, `setup` shape: `addInitScript` with `ta_lang`/`ta_authenticated`, a `page.route('**/api/v1/**')` that records non-GET writes and serves fixtures; `GET /api/v1/admin/quality/answers` via an optional `list(url)` callback). Fixtures:
  - three rows with pseudonyms `U-7F3A2C` / `U-19B0E4`, one `rating:-1, verdict:null, flags:['no_precise_citation']`, one `rating:1, verdict:'correct'`, one `flags:['no_evidence']`;
  - a summary `{answers: 120, rated: 40, down: 10, down_share: 0.25, reviewed: 12, reviewed_share: 0.1, verdicts: {correct: 7, partial: 3, wrong: 2}, reasons: {...all 0 except wrong_citation: 2}, no_precise_citation_share: 0.3, median_processing_ms: 8400, down_unreviewed: 6}`;
  - a detail with a 2-message dialog, evidence, `rating {value:-1, comment:'Статья не та'}`, one prior review, `neighbors {prev_id:'q-prev', next_id:'q-next'}`;
  - `/api/v1/auth/me`.

  Tests (write each fully, with assertions on URL, visible text and the exact `writes` array):
  1. Feed filters live in the URL and survive reload. Clicking the queue "👎 без разметки" gives `?rating=down&verdict=unreviewed`. A flag checkbox appends `flags=no_precise_citation`. The last list request carries them.
  2. Opening a row and "← К ленте" keep the filters (`back` param round-trip).
  3. The review sends `{verdict:'wrong', reasons:['wrong_citation','fabricated'], note:'cites 168', reason:'weekly review'}`. Save stays disabled until a verdict is chosen and the reason has ≥3 characters. After success the notice «Разметка сохранена.» shows.
  4. "Открыть клиента" requires a reason, POSTs `{reason}` to `/reveal-user`, then navigates to `/admin/users/<user_id>` (mock returns `{user_id: 'u-123'}`; add a minimal card fixture or assert the URL only).
  5. "Следующий →" goes to `/admin/quality/q-next` and keeps `back`.
  6. The feed and the review page have no horizontal scroll at 390px.
  7. Visual baseline: feed RU desktop 1440×900 (wait for the summary tiles and the table) → `admin-quality-ru-desktop.png`; review KA mobile 390×844 in a fresh page (wait for the evidence and history headings in KA copy) → `admin-quality-review-ka-mobile.png`.

- [ ] **Step 2: `answer-rating.spec.ts`** — home page with `ta_authenticated='1'`. Mock `POST /api/v1/query` → `{response:'…', sources:[], evidence:{status:'grounded', basis:'', coverage:'', source_count:1, official_sources_only:true, has_precise_citation:true, has_official_provision_link:false, generated_at:'2026-10-12T10:00:00'}, conversation_id:'c1', retrieved_count:1, processing_time:1.2, message_id:'m1'}` and `PUT/DELETE /api/v1/query/messages/m1/rating` (recorded). Tests:
  1. 👍 → PUT `{value:1}`, button `aria-pressed=true`, «Спасибо…» visible. 👍 again → DELETE, unpressed.
  2. 👎 → PUT `{value:-1}`. The comment box appears. Typing "Не та статья" and «Отправить» → PUT `{value:-1, comment:'Не та статья'}`.
  3. The rating request fails with 500 → the button returns to unpressed and «Не удалось сохранить оценку…» shows.
  4. Guest (no `ta_authenticated`; mock `POST /api/v1/public/query` with the same payload minus `message_id`) → no rating buttons.

- [ ] **Step 3: Functional run** — fresh Windows `npm run build` (background, log), then `rtk npx playwright test e2e/admin.spec.ts e2e/admin-users.spec.ts e2e/admin-quality.spec.ts e2e/answer-rating.spec.ts e2e/billing-reconciliation.spec.ts e2e/visual.spec.ts --grep-invert "visual baseline"` → all pass. (`visual.spec.ts` covers the home page; the rating UI appears only after an answer, so its baselines should be unaffected. If any home baseline changes, stop and report.)

- [ ] **Step 4: Baselines in the pinned container** — move `frontend/.next` aside and restore it afterwards. From the repo root in Git Bash:

```bash
MSYS_NO_PATHCONV=1 rtk docker run --rm --ipc=host -v "F:/New_Projects/Warp/Warp_INFOHUB.GE":/work -v /work/frontend/node_modules -w /work/frontend mcr.microsoft.com/playwright@sha256:dcc5531e97840b9b5e794f2814476b21571c5124a3fca2267d73041f56e7580e bash -c "npm ci --ignore-scripts && npm run build && npx playwright test e2e/admin.spec.ts e2e/admin-quality.spec.ts --grep 'visual baseline' --update-snapshots"
```

  - Delete `admin-dashboard-ru-desktop.png` first: a small text change can fall under `maxDiffPixelRatio` and not be rewritten.
  - Then rerun the same command WITHOUT `--update-snapshots` to prove the result is stable.
  - Open the three PNGs and confirm:
    - the dashboard shows «Ответы с 👎 без разметки»;
    - the feed shows the tiles and the table with pseudonyms;
    - the KA review renders without clipped labels.
  - `admin-users-*` and `admin-user-card-*` baselines must be unchanged. No stray `.next` backup may remain.

- [ ] **Step 5: Docs**
  - `docs/DEVELOPMENT_MEMORY.md`: "Admin stage 4 — answer quality". Cover the schema script and its contract, pseudonyms (HMAC over SECRET_KEY), the append-only reviews and cascade rule, that ratings are only for signed-in users, that guests are not stored, and that answers older than this stage have no signals.
  - `docs/PRODUCTION_OPERATIONS.md`: add the new automatic deploy step `add_answer_quality.py`, where the quality feed lives, that "Open client" is journaled, and the privacy-policy change.

- [ ] **Step 6: Full verification** (paste the raw tails):
  - Backend PG in CI order: `rtk python -m pytest tests/test_billing_provider_postgres.py tests/test_admin_postgres.py tests/test_admin_users_postgres.py tests/test_admin_quality_postgres.py tests/test_billing_review_postgres.py -q`.
  - Non-PG: `rtk python -m pytest tests/test_admin_audit.py tests/test_public_config.py tests/test_integration.py tests/test_plan_quotas.py tests/test_security_hardening.py -q`.
  - Frontend: `rtk npm run type-check`, `rtk npm run lint`, `rtk npm run check:admin-styles`, `rtk npm run test:admin-styles`.

- [ ] **Step 7: Commit** — `test(quality): stage 4 e2e, baselines and docs`.
