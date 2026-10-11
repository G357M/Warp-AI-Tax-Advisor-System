# Admin Stage 2 — Clients Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `/admin/users` into a support tool: searchable, filterable list; a per-user card with subscription, payments and activity; and journaled account actions (block, role, grant, record payment, early cancel, password-reset and verification emails).

**Architecture:** Backend moves user management out of `api/routes/admin.py` into a new router `api/routes/admin_users.py` (prefix `/admin/users`), backed by pure helpers in `core/admin_users.py` (SQLAlchemy Core list query, card builder, grant arithmetic, coded errors). The legacy "activate by email" branch in `billing.py` is extracted into `settle_manual_payment`, shared with the new record-payment action. Frontend adds `useAdminFetch` (abortable), `adminSend`/`errorText` (coded errors), rewrites the list page with URL state, and adds the card page `/admin/users/[id]` with action dialogs on an extended `ConfirmDialog`.

**Tech Stack:** FastAPI, SQLAlchemy 2, PostgreSQL 15 + pgvector, pytest; Next.js 16 / React 19 (`output: 'standalone'`), CSS Modules, Radix Dialog via `GlassDialog`, Playwright 1.62.

**Spec:** `docs/superpowers/specs/2026-10-11-admin-stage2-clients-design.md`

## Global Constraints

- One role `admin`; every new route is behind `require_admin` (router-level dependency).
- No DB schema changes. `ADMIN_AUDIT_SCHEMA_CONTRACT_SHA256` and `backend/scripts/add_admin_audit_log.py` stay untouched.
- Every mutating action: user row locked `FOR UPDATE`; change + `record_admin_action` in one transaction; no-op → `changed: false`, no journal row.
- `reason` for every new action and for role change: required, stripped, 3–1000 chars (`core.admin_users.Reason`). Feedback status `reason` stays optional (unchanged).
- Journal `before`/`after` never contain tokens, password hashes or secrets.
- Every `HTTPException` in `admin.py` and `admin_users.py` uses `detail={"code": ..., "message": <English>}` via `admin_error`. Each route documents its codes in a **literal** `responses={...}` dict (SonarCloud recognises a literal dict or a single name reference, not `{**X, **Y}` spreads).
- No f-string SQL in new code (SonarCloud S2077); use SQLAlchemy Core/ORM expressions.
- `/billing/*` behaviour unchanged; only the legacy branch body is moved into `settle_manual_payment`.
- Frontend: no `style={{…}}` in `app/admin/**` and `components/admin/**` except CSS custom properties (`npm run check:admin-styles`). Colours only from `globals.css` tokens plus warning `#d97706`.
- All admin copy in RU/KA/EN in `frontend/lib/admin-i18n.ts`. Georgian strings are written and reviewed with the `georgian-writing-style` skill before the task's commit.
- Visual baselines are generated only in the pinned Playwright container `mcr.microsoft.com/playwright@sha256:dcc5531e97840b9b5e794f2814476b21571c5124a3fca2267d73041f56e7580e`, never on Windows.
- All shell commands prefixed with `rtk` (user rule). Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Backend tests run from `backend/` with:
  `DATABASE_URL=postgresql://test:test@127.0.0.1:5440/test REDIS_URL=redis://localhost:6379/0 SECRET_KEY=test-secret-key-for-ci-minimum-32-characters JWT_SECRET_KEY=test-jwt-secret-for-ci-minimum-32-characters`; PostgreSQL tests also need `BILLING_PROVIDER_POSTGRES_TESTS=1` (pgvector container on 5440 is running locally).
- This machine is slow (pytest collection ≈6 min, Next build ≈15 min, container Playwright ≈40 min): run long commands in the background with a log, poll with bounded `sleep N; tail`.

## Review Focus

1. **Search term containing `%`, `_` or `\`** — expected: matched literally, not as wildcards. Test in Task 1.
2. **Subscription with `period_end IS NULL` (legacy unlimited)** — expected: counts as active in filters/card; same-plan grant returns 409 `plan_unlimited` instead of silently shortening it. Tests in Tasks 1 and 4.
3. **Fast typing in the search box** — expected: a slow earlier response never overwrites the newer result. E2E test in Task 9.
4. **Acting on an admin** — expected: block → 409 `cannot_block_admin`; grant/record-payment → 409 `admin_has_business`; cancel → 409 `no_active_subscription`; the card hides these buttons. Tests in Tasks 3, 4 and 9.
5. **Email cooldown** — expected: 200 with `sent: false`, `changed: false`, no journal row, no background task. Test in Task 5.

---

## File Structure

Backend
- Create `backend/core/admin_users.py` — `Reason`, `admin_error`, list query, card builder, grant window, subscription snapshot.
- Create `backend/api/routes/admin_users.py` — list, card, role (moved), block/unblock, grant, record-payment, cancel, emails.
- Modify `backend/api/routes/admin.py` — remove `list_users`, `RoleUpdate`, `update_user_role`; coded feedback 404.
- Modify `backend/api/routes/billing.py` — extract `settle_manual_payment`.
- Modify `backend/core/plans.py` — `questions_used_today_or_none`.
- Modify `backend/core/admin_audit.py` — new actions.
- Modify `backend/api/main.py` — include the new router.
- Tests: create `backend/tests/test_admin_users_postgres.py`; modify `backend/tests/test_admin_postgres.py` (role tests move out), `backend/tests/test_integration.py` (mount router, 403s), `backend/tests/test_admin_audit.py` if it asserts the action set.
- Modify `.github/workflows/ci.yml` — add the new PG test file.

Frontend
- Create `frontend/lib/use-admin-fetch.ts`, `frontend/lib/admin-api.ts`.
- Modify `frontend/lib/admin-types.ts` — user list/card types.
- Modify `frontend/lib/admin-i18n.ts` — new copy, `errors`, typed action/error keys.
- Modify `frontend/components/admin/ConfirmDialog.tsx` — extra fields, required reason, `canConfirm`.
- Modify `frontend/app/admin/audit/page.tsx` — new actions in filter.
- Rewrite `frontend/app/admin/users/page.tsx`.
- Create `frontend/app/admin/users/[id]/page.tsx`, `frontend/app/admin/users/[id]/UserActions.tsx`.
- Modify `frontend/app/admin/admin.module.css` — card layout classes.
- Modify `frontend/e2e/admin.spec.ts`; create `frontend/e2e/admin-users.spec.ts`; regenerate `admin-users-ka-mobile.png`, add `admin-user-card-ru-desktop.png`, `admin-user-card-ka-mobile.png`.
- Docs: `docs/DEVELOPMENT_MEMORY.md`, `docs/PRODUCTION_OPERATIONS.md`.

---

### Task 1: Core helpers and the searchable user list

**Files:**
- Create: `backend/core/admin_users.py`
- Create: `backend/api/routes/admin_users.py`
- Modify: `backend/api/routes/admin.py` (remove `list_users`, lines ~144–175)
- Modify: `backend/api/main.py` (import + include router)
- Modify: `backend/tests/test_integration.py` (include router in the test app, line ~84)
- Create: `backend/tests/test_admin_users_postgres.py`
- Modify: `.github/workflows/ci.yml` (add the new file after `tests/test_admin_postgres.py`, ~line 255)

**Interfaces:**
- Produces: `core.admin_users.{Reason, PAID_PLANS, admin_error(status_code, code, message) -> HTTPException, escape_like(str) -> str, effective_plan(user, sub, now) -> str, paid_subscription_active(sub, now) -> bool, list_users_page(db, *, q, plan, status, sort, limit, offset) -> dict}`; `api.routes.admin_users.router` (prefix `/admin/users`), `api.routes.admin_users.list_users(q, plan, status, sort, limit, offset, db)`.

- [ ] **Step 1: Write the failing PostgreSQL tests**

Create `backend/tests/test_admin_users_postgres.py`:

```python
"""Admin client management (search, card, account actions) on real PostgreSQL."""
import os
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from api.routes import admin_users as routes
from core.config import settings
from core.database import Base, engine
from core.time_utils import utc_now
from models import (AdminAuditLog, BillingCheckout, Conversation, Feedback, Message, Payment,
                    Subscription, User)
from models.user import AuthActionToken
from scripts.add_admin_audit_log import apply_schema

pytestmark = pytest.mark.skipif(os.getenv("BILLING_PROVIDER_POSTGRES_TESTS") != "1",
                                reason="requires dedicated PostgreSQL")

TABLES = [User, AuthActionToken, Subscription, Payment, BillingCheckout, Feedback, Conversation, Message]


@pytest.fixture
def database():
    schema = "admin_users_test_" + uuid4().hex
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    local = create_engine(settings.DATABASE_URL, connect_args={"options": f"-csearch_path={schema},public"},
                          execution_options={"schema_translate_map": {None: schema}})
    Base.metadata.create_all(local, tables=[m.__table__ for m in TABLES])
    with local.begin() as conn:
        apply_schema(conn)
    sessions = sessionmaker(bind=local, autoflush=False)
    with sessions() as db:
        admin = User(email="boss@example.test", username="boss", password_hash="x", role="admin",
                     email_verified_at=utc_now())
        db.add(admin)
        db.commit()
        ids = SimpleNamespace(admin_id=admin.id)
    yield sessions, ids
    local.dispose()
    # The identifier is generated here, never supplied by an environment/user.
    with engine.begin() as conn:
        conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


def _user(db, username, *, email=None, full_name=None, role="user", active=True, verified=True,
          created_days_ago=0, last_login_days_ago=None):
    now = utc_now()
    user = User(email=email or f"{username}@example.test", username=username, password_hash="x",
                full_name=full_name, role=role, is_active=active,
                email_verified_at=now if verified else None,
                created_at=now - timedelta(days=created_days_ago),
                last_login=None if last_login_days_ago is None else now - timedelta(days=last_login_days_ago))
    db.add(user)
    db.flush()
    return user


def _sub(db, user, plan, *, status="active", days=30, provider="manual"):
    now = utc_now()
    sub = Subscription(user_id=user.id, plan=plan, status=status, period_start=now,
                       period_end=None if days is None else now + timedelta(days=days),
                       payment_provider=provider)
    db.add(sub)
    db.flush()
    return sub


def _list(sessions, **kwargs):
    params = {"q": None, "plan": None, "status": None, "sort": "created_desc", "limit": 50, "offset": 0}
    params.update(kwargs)
    with sessions() as db:
        return routes.list_users(db=db, **params)


def _names(page):
    return [row["username"] for row in page["items"]]


def test_search_matches_email_username_and_full_name_case_insensitively(database):
    sessions, _ = database
    with sessions() as db:
        _user(db, "alpha", email="Owner@Acme.ge")
        _user(db, "beta", full_name="Nino Beridze")
        _user(db, "gamma")
        db.commit()
    assert _names(_list(sessions, q="acme")) == ["alpha"]
    assert _names(_list(sessions, q="  BERIDZE ")) == ["beta"]
    assert _names(_list(sessions, q="gam")) == ["gamma"]
    page = _list(sessions, q="a", limit=1)
    # "a" is in alpha, beta, gamma and boss@example.test
    assert page["total"] == 4 and len(page["items"]) == 1


def test_search_treats_like_wildcards_literally(database):
    sessions, _ = database
    with sessions() as db:
        _user(db, "under_score")
        _user(db, "underXscore")
        _user(db, "pct", full_name="100% done")
        _user(db, "slash", full_name="back\\slash")
        db.commit()
    assert _names(_list(sessions, q="under_")) == ["under_score"]
    assert _names(_list(sessions, q="100%")) == ["pct"]
    assert _names(_list(sessions, q="k\\s")) == ["slash"]


def test_plan_filter_uses_effective_plan(database):
    sessions, _ = database
    with sessions() as db:
        _sub(db, _user(db, "paid-pro"), "pro")
        _sub(db, _user(db, "unlimited-pro"), "pro", days=None)
        _sub(db, _user(db, "expired-pro"), "pro", days=-1)
        _sub(db, _user(db, "canceled-biz"), "business", status="canceled")
        _sub(db, _user(db, "paid-biz"), "business")
        _user(db, "nobody")
        db.commit()
    assert sorted(_names(_list(sessions, plan="pro"))) == ["paid-pro", "unlimited-pro"]
    assert sorted(_names(_list(sessions, plan="business"))) == ["boss", "paid-biz"]
    assert sorted(_names(_list(sessions, plan="free"))) == ["canceled-biz", "expired-pro", "nobody"]
    rows = {r["username"]: r for r in _list(sessions)["items"]}
    assert rows["boss"]["plan"] == "business" and rows["expired-pro"]["plan"] == "free"


def test_expiring_filter_is_paid_non_admin_within_seven_days(database):
    sessions, ids = database
    with sessions() as db:
        _sub(db, _user(db, "soon"), "pro", days=6)
        _sub(db, _user(db, "later"), "pro", days=8)
        _sub(db, _user(db, "gone"), "pro", days=-1)
        _sub(db, _user(db, "free-sub"), "free", days=3)
        _sub(db, db.get(User, ids.admin_id), "business", days=2)
        db.commit()
    assert _names(_list(sessions, plan="expiring")) == ["soon"]


def test_status_filters(database):
    sessions, _ = database
    with sessions() as db:
        _user(db, "blocked-one", active=False)
        _user(db, "unverified-one", verified=False)
        _user(db, "fine")
        db.commit()
    assert _names(_list(sessions, status="blocked")) == ["blocked-one"]
    assert _names(_list(sessions, status="unverified")) == ["unverified-one"]
    assert _names(_list(sessions, status="admin")) == ["boss"]
    assert "blocked-one" not in _names(_list(sessions, status="active"))
    rows = {r["username"]: r for r in _list(sessions)["items"]}
    assert rows["blocked-one"]["is_active"] is False and rows["unverified-one"]["email_verified"] is False


def test_sorts_put_empty_values_last(database):
    sessions, _ = database
    with sessions() as db:
        _user(db, "old", created_days_ago=10, last_login_days_ago=1)
        _user(db, "new", created_days_ago=1, last_login_days_ago=5)
        _user(db, "never", created_days_ago=5)
        _sub(db, db.query(User).filter_by(username="old").one(), "pro", days=40)
        _sub(db, db.query(User).filter_by(username="new").one(), "pro", days=3)
        db.commit()
    by_created = _names(_list(sessions, q="e", sort="created_desc"))
    assert by_created.index("new") < by_created.index("never") < by_created.index("old")
    by_login = _names(_list(sessions, q="e", sort="last_login_desc"))
    assert by_login[:2] == ["old", "new"] and by_login[-1] in {"never"}
    by_end = _names(_list(sessions, q="e", sort="period_end_asc"))
    assert by_end[:2] == ["new", "old"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `backend/`, env above): `rtk python -m pytest tests/test_admin_users_postgres.py -q`
Expected: collection error `cannot import name 'admin_users' from 'api.routes'`.

- [ ] **Step 3: Implement `core/admin_users.py` (list part)**

```python
"""Admin client management: list filters, the user card, plan grants and coded errors."""
from datetime import datetime, timedelta
from typing import Annotated, Optional

from fastapi import HTTPException
from pydantic import StringConstraints
from sqlalchemy import and_, case, func, literal, or_, select
from sqlalchemy.orm import Session

from core.time_utils import utc_now
from models import Subscription, User

Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=1000)]
PAID_PLANS = ("pro", "business")
EXPIRING_DAYS = 7

STATUS_FILTERS = {
    "active": User.is_active.is_(True),
    "blocked": User.is_active.is_(False),
    "unverified": User.email_verified_at.is_(None),
    "admin": User.role == "admin",
}
SORTS = {
    "created_desc": (User.created_at.desc().nulls_last(), User.id),
    "last_login_desc": (User.last_login.desc().nulls_last(), User.id),
    "period_end_asc": (Subscription.period_end.asc().nulls_last(), User.id),
}


def admin_error(status_code: int, code: str, message: str) -> HTTPException:
    """Machine-readable admin error; the frontend localises by `code`."""
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _in_period(sub, now) -> bool:
    return sub.status == "active" and (sub.period_end is None or sub.period_end >= now)


def effective_plan(user, sub, now) -> str:
    """Same rules as core.plans.get_active_plan, without a query."""
    if user.role == "admin":
        return "business"
    if sub is not None and _in_period(sub, now):
        return sub.plan
    return "free"


def paid_subscription_active(sub, now) -> bool:
    return sub is not None and sub.plan in PAID_PLANS and _in_period(sub, now)


def _effective_plan_sql(now):
    return case(
        (User.role == "admin", literal("business")),
        (and_(Subscription.status == "active",
              or_(Subscription.period_end.is_(None), Subscription.period_end >= now)), Subscription.plan),
        else_=literal("free"),
    )


def _conditions(q, plan, status, now) -> list:
    conditions = []
    term = (q or "").strip()
    if term:
        pattern = f"%{escape_like(term)}%"
        conditions.append(or_(User.email.ilike(pattern, escape="\\"),
                              User.username.ilike(pattern, escape="\\"),
                              func.coalesce(User.full_name, "").ilike(pattern, escape="\\")))
    if plan == "expiring":
        conditions += [User.role != "admin", Subscription.status == "active", Subscription.plan.in_(PAID_PLANS),
                       Subscription.period_end >= now,
                       Subscription.period_end < now + timedelta(days=EXPIRING_DAYS)]
    elif plan:
        conditions.append(_effective_plan_sql(now) == plan)
    if status:
        conditions.append(STATUS_FILTERS[status])
    return conditions


def list_users_page(db: Session, *, q, plan, status, sort, limit, offset) -> dict:
    now = utc_now()
    conditions = _conditions(q, plan, status, now)
    join = (Subscription, Subscription.user_id == User.id)
    total = db.execute(
        select(func.count()).select_from(User).outerjoin(*join).where(*conditions)
    ).scalar_one()
    rows = db.execute(
        select(User, Subscription.period_end, _effective_plan_sql(now).label("plan"))
        .outerjoin(*join).where(*conditions)
        .order_by(*SORTS[sort]).limit(limit).offset(offset)
    ).all()
    return {"total": total, "items": [{
        "id": str(user.id), "username": user.username, "email": user.email, "role": user.role,
        "created_at": iso(user.created_at), "last_login": iso(user.last_login),
        "plan": plan_value, "period_end": iso(period_end),
        "is_active": user.is_active, "email_verified": user.email_verified,
    } for user, period_end, plan_value in rows]}
```

- [ ] **Step 4: Create the router with the list endpoint; remove the old one**

`backend/api/routes/admin_users.py`:

```python
"""Admin client management: search, the user card and journaled account actions.
All endpoints require the admin role."""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from core.admin_users import list_users_page
from core.database import get_db
from core.security import require_admin

router = APIRouter(prefix="/admin/users", tags=["Admin"], dependencies=[Depends(require_admin)])

PlanFilter = Literal["free", "pro", "business", "expiring"]
StatusFilter = Literal["active", "blocked", "unverified", "admin"]
UserSort = Literal["created_desc", "last_login_desc", "period_end_asc"]


@router.get("")
def list_users(
    q: Optional[str] = Query(default=None, max_length=100),
    plan: Optional[PlanFilter] = None,
    status: Optional[StatusFilter] = None,
    sort: UserSort = "created_desc",
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    return list_users_page(db, q=q, plan=plan, status=status, sort=sort, limit=limit, offset=offset)
```

In `backend/api/routes/admin.py` delete the whole `@router.get("/users")` `list_users` function. Leave `RoleUpdate`/`update_user_role` for Task 3.

In `backend/api/main.py`: add `admin_users` to the `from api.routes import ...` line (alphabetical, after `admin`) and add after the admin include:
`app.include_router(admin_users.router, prefix=settings.API_PREFIX)  # Admin: clients`

In `backend/tests/test_integration.py`: add `admin_users` to the `from api.routes import ...` import (line ~48) and `app.include_router(admin_users.router, prefix=settings.API_PREFIX)` after line ~84.

In `.github/workflows/ci.yml` add `tests/test_admin_users_postgres.py` on the line after `tests/test_admin_postgres.py` in the "Exercise PostgreSQL immutability and interval triggers" step.

- [ ] **Step 5: Run tests**

`rtk python -m pytest tests/test_admin_users_postgres.py tests/test_admin_postgres.py -q` (PG env) → all pass.
`rtk python -m pytest tests/test_integration.py -q` → pass (no list-users assertion depends on the old function; if one does, update its import to `admin_users`).

- [ ] **Step 6: Commit**

```bash
rtk git add backend/core/admin_users.py backend/api/routes/admin_users.py backend/api/routes/admin.py backend/api/main.py backend/tests/test_admin_users_postgres.py backend/tests/test_integration.py .github/workflows/ci.yml
rtk git commit -m "feat(admin): searchable, filterable, sortable user list

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: The user card endpoint

**Files:**
- Modify: `backend/core/plans.py` (add `questions_used_today_or_none`, reuse in `questions_used_today`)
- Modify: `backend/core/admin_users.py` (card builder)
- Modify: `backend/api/routes/admin_users.py` (`GET /{user_id}`)
- Modify: `backend/tests/test_admin_users_postgres.py`
- Modify: `backend/tests/test_plan_quotas.py` (one test for the new function)

**Interfaces:**
- Consumes: Task 1 helpers.
- Produces: `core.plans.questions_used_today_or_none(user_id) -> Optional[int]`; `core.admin_users.user_card(db, user) -> dict` (shape = spec §2); `core.admin_users.subscription_snapshot(sub) -> Optional[dict]`; `api.routes.admin_users.get_user_card(user_id, db)`; `api.routes.admin_users.locked_user(db, user_id) -> User` (404 `user_not_found`).

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_admin_users_postgres.py`:

```python
from fastapi import HTTPException  # move to the top-level imports


def _card(sessions, user_id):
    with sessions() as db:
        return routes.get_user_card(user_id, db)


def test_card_has_profile_subscription_payments_checkouts_and_activity(database, monkeypatch):
    sessions, _ = database
    from core import admin_users as core_users
    monkeypatch.setattr(core_users, "questions_used_today_or_none", lambda _uid: 2)
    now = utc_now()
    with sessions() as db:
        user = _user(db, "carded", full_name="Card Holder")
        sub = _sub(db, user, "pro", days=10, provider="grant")
        db.add(Payment(subscription_id=sub.id, amount_gel=49, amount_minor=4900, currency="GEL",
                       provider="manual", status="succeeded"))
        db.add(BillingCheckout(user_id=user.id, plan="pro", months=1, amount_minor=4900, currency="GEL",
                               provider="manual", status="pending", idempotency_key=uuid4().hex,
                               expires_at=now + timedelta(hours=1)))
        recent = Conversation(user_id=user.id, created_at=now - timedelta(days=2))
        older = Conversation(user_id=user.id, created_at=now - timedelta(days=20))
        db.add_all([recent, older])
        db.flush()
        db.add_all([Message(conversation_id=recent.id, role="user", content="q1", created_at=now - timedelta(days=2)),
                    Message(conversation_id=recent.id, role="assistant", content="a1", created_at=now - timedelta(days=2)),
                    Message(conversation_id=older.id, role="user", content="q2", created_at=now - timedelta(days=20)),
                    Feedback(user_id=user.id, message="hi")])
        db.commit()
        user_id = user.id
    card = _card(sessions, user_id)
    assert card["profile"]["username"] == "carded" and card["profile"]["full_name"] == "Card Holder"
    assert card["profile"]["effective_plan"] == "pro" and card["profile"]["is_active"] is True
    assert card["subscription"]["source"] == "grant" and card["subscription"]["days_left"] in (9, 10)
    assert len(card["payments"]) == 1 and card["payments"][0]["amount_minor"] == 4900
    assert card["checkouts"][0]["status"] == "pending"
    assert card["activity"] == {"conversations_7d": 1, "conversations_30d": 2, "questions_7d": 1,
                                "questions_30d": 2, "questions_today": 2, "daily_limit": None,
                                "feedback_total": 1}


def test_card_without_subscription_or_redis(database, monkeypatch):
    sessions, ids = database
    from core import admin_users as core_users
    monkeypatch.setattr(core_users, "questions_used_today_or_none", lambda _uid: None)
    with sessions() as db:
        user = _user(db, "freebie")
        db.commit()
        user_id = user.id
    card = _card(sessions, user_id)
    assert card["subscription"] is None and card["profile"]["effective_plan"] == "free"
    assert card["activity"]["questions_today"] is None and card["activity"]["daily_limit"] == 5
    assert _card(sessions, ids.admin_id)["profile"]["effective_plan"] == "business"


def test_card_for_expired_subscription_has_no_days_left(database):
    sessions, _ = database
    with sessions() as db:
        user = _user(db, "lapsed")
        _sub(db, user, "pro", days=-3)
        db.commit()
        user_id = user.id
    card = _card(sessions, user_id)
    assert card["subscription"]["plan"] == "pro" and card["subscription"]["days_left"] is None
    assert card["profile"]["effective_plan"] == "free"


def test_card_for_missing_user_is_coded_404(database):
    sessions, _ = database
    with pytest.raises(HTTPException) as exc:
        _card(sessions, uuid4())
    assert exc.value.status_code == 404 and exc.value.detail["code"] == "user_not_found"
```

`core.admin_users` must look `questions_used_today_or_none` up through its own module namespace (plain `from core.plans import ...` at the top is fine, because the tests patch `core.admin_users.questions_used_today_or_none`).

In `backend/tests/test_plan_quotas.py` add:

```python
def test_questions_used_today_or_none_distinguishes_missing_redis(monkeypatch):
    from core import plans
    monkeypatch.setattr(plans, "_redis", lambda: None)
    assert plans.questions_used_today_or_none("u") is None
    assert plans.questions_used_today("u") == 0
```

- [ ] **Step 2: Run to verify failure**

`rtk python -m pytest tests/test_admin_users_postgres.py -q -k card` → `AttributeError: ... get_user_card`.

- [ ] **Step 3: Implement**

`backend/core/plans.py` — replace `questions_used_today` with:

```python
def questions_used_today_or_none(user_id) -> Optional[int]:
    """Today's question count, or None when Redis is unavailable (unknown, not zero)."""
    client = _redis()
    if client is None:
        return None
    try:
        return int(client.get(quota_key(user_id)) or 0)
    except Exception:
        return None


def questions_used_today(user_id) -> int:
    return questions_used_today_or_none(user_id) or 0
```

Append to `backend/core/admin_users.py` (add imports `from core.plans import FREE_DAILY_QUESTIONS, questions_used_today_or_none` and `from models import BillingCheckout, Conversation, Feedback, Message, Payment, Subscription, User`):

```python
CARD_ROWS = 20


def subscription_snapshot(sub) -> Optional[dict]:
    """Access-relevant subscription fields for the admin journal; no payment data."""
    if sub is None:
        return None
    return {"plan": sub.plan, "status": sub.status, "period_end": iso(sub.period_end),
            "source": "grant" if sub.payment_provider == "grant" else "payment"}


def _activity(db: Session, user, plan: str, now) -> dict:
    d7, d30 = now - timedelta(days=7), now - timedelta(days=30)
    conversations = db.execute(
        select(func.count().filter(Conversation.created_at >= d7),
               func.count().filter(Conversation.created_at >= d30))
        .where(Conversation.user_id == user.id)
    ).one()
    questions = db.execute(
        select(func.count().filter(Message.created_at >= d7), func.count().filter(Message.created_at >= d30))
        .select_from(Message).join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.user_id == user.id, Message.role == "user")
    ).one()
    feedback_total = db.execute(
        select(func.count()).select_from(Feedback).where(Feedback.user_id == user.id)
    ).scalar_one()
    return {
        "conversations_7d": conversations[0], "conversations_30d": conversations[1],
        "questions_7d": questions[0], "questions_30d": questions[1],
        "questions_today": questions_used_today_or_none(user.id),
        "daily_limit": FREE_DAILY_QUESTIONS if plan == "free" else None,
        "feedback_total": feedback_total,
    }


def user_card(db: Session, user) -> dict:
    now = utc_now()
    sub = db.query(Subscription).filter_by(user_id=user.id).first()
    plan = effective_plan(user, sub, now)
    subscription = None
    if sub is not None:
        live = sub.status == "active" and sub.period_end is not None and sub.period_end >= now
        snapshot = subscription_snapshot(sub)
        subscription = {**snapshot, "period_start": iso(sub.period_start),
                        "days_left": max(0, (sub.period_end - now).days) if live else None}
    payments = (db.query(Payment).join(Subscription, Payment.subscription_id == Subscription.id)
                .filter(Subscription.user_id == user.id).order_by(Payment.created_at.desc()).limit(CARD_ROWS).all())
    checkouts = (db.query(BillingCheckout).filter(BillingCheckout.user_id == user.id)
                 .order_by(BillingCheckout.created_at.desc()).limit(CARD_ROWS).all())
    return {
        "profile": {
            "id": str(user.id), "username": user.username, "email": user.email, "full_name": user.full_name,
            "role": user.role, "effective_plan": plan, "is_active": user.is_active,
            "email_verified": user.email_verified, "created_at": iso(user.created_at),
            "last_login": iso(user.last_login),
        },
        "subscription": subscription,
        "payments": [{"id": str(p.id), "created_at": iso(p.created_at), "amount_minor": p.amount_minor,
                      "currency": p.currency, "provider": p.provider, "status": p.status} for p in payments],
        "checkouts": [{"id": str(c.id), "created_at": iso(c.created_at), "plan": c.plan, "months": c.months,
                       "amount_minor": c.amount_minor, "currency": c.currency, "provider": c.provider,
                       "status": c.status, "expires_at": iso(c.expires_at)} for c in checkouts],
        "activity": _activity(db, user, plan, now),
    }
```

`subscription` keys: `plan, status, period_end, source, period_start, days_left` (spec §2).

Append to `backend/api/routes/admin_users.py` (imports: `from uuid import UUID`, `from core.admin_users import admin_error, user_card`, `from models import User`):

```python
def locked_user(db: Session, user_id: UUID) -> User:
    user = db.query(User).filter(User.id == user_id).with_for_update().first()
    if not user:
        raise admin_error(404, "user_not_found", "User not found")
    return user


@router.get("/{user_id}", responses={404: {"description": "User not found"}})
def get_user_card(user_id: UUID, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise admin_error(404, "user_not_found", "User not found")
    return user_card(db, user)
```

- [ ] **Step 4: Run tests**

`rtk python -m pytest tests/test_admin_users_postgres.py tests/test_plan_quotas.py -q` → pass.

- [ ] **Step 5: Commit**

`feat(admin): user card with subscription, payments and activity` (files above).

---

### Task 3: Coded errors, role change move, block and unblock

**Files:**
- Modify: `backend/core/admin_audit.py` (`ADMIN_ACTIONS`)
- Modify: `backend/api/routes/admin.py` (remove `RoleUpdate`, `update_user_role`; coded feedback 404)
- Modify: `backend/api/routes/admin_users.py`
- Modify: `backend/tests/test_admin_postgres.py` (role tests → new module; feedback 404 code)
- Modify: `backend/tests/test_admin_users_postgres.py`
- Modify: `backend/tests/test_admin_audit.py` (only if it asserts the exact action set)

**Interfaces:**
- Produces: `ReasonBody(reason)`, `RoleUpdate(role, reason)`, `update_user_role(user_id, body, admin, db)`, `block_user(user_id, body, admin, db)`, `unblock_user(user_id, body, admin, db)`; helper `finish(db, user, changed, **extra) -> dict` returning `{"changed": changed, **extra, **user_card(db, user)}` after commit.
- `ADMIN_ACTIONS` gains `user.blocked`, `user.unblocked`, `subscription.granted`, `subscription.canceled`, `user.password_reset_sent`, `user.verification_sent` (all six now, so later tasks only use them).

- [ ] **Step 1: Write failing tests**

Move `test_role_change_is_journaled_with_reason`, `test_unchanged_role_is_not_journaled`, `test_self_demotion_is_rejected_without_entry`, `test_journal_failure_rolls_back_role_change` from `test_admin_postgres.py` into `test_admin_users_postgres.py`, adapting them: `admin_routes.update_user_role` → `routes.update_user_role`, `admin_routes.RoleUpdate` → `routes.RoleUpdate`, every `RoleUpdate(...)` gets `reason="promote"` (or similar ≥3 chars), the fixture users come from `_user(db, ...)` inside each test, `result["role"]` → `result["profile"]["role"]`, the self-demotion assertion becomes `exc.value.status_code == 400 and exc.value.detail["code"] == "cannot_demote_self"`. In `test_admin_postgres.py::test_audit_listing_filters_and_paginates` replace the two role-change calls with `admin_users.update_user_role(...)` imported from `api.routes`, with `reason="promote"`/`"demote"`. Add to `test_admin_users_postgres.py`:

```python
from pydantic import ValidationError  # top-level import


def _entries(sessions):
    with sessions() as db:
        return db.query(AdminAuditLog).order_by(AdminAuditLog.created_at).all()


def _act(sessions, func, user_id, body, admin_id, **extra):
    with sessions() as db:
        return func(user_id, body, admin=db.get(User, admin_id), db=db, **extra)


def test_reason_is_required_and_stripped():
    with pytest.raises(ValidationError):
        routes.ReasonBody(reason="  ab  ")
    assert routes.ReasonBody(reason="  spam bot ").reason == "spam bot"


def test_block_ends_sessions_and_is_journaled_once(database):
    sessions, ids = database
    with sessions() as db:
        target = _user(db, "spammer")
        db.commit()
        user_id, before_version = target.id, target.session_version
    body = routes.ReasonBody(reason="spam bot")
    first = _act(sessions, routes.block_user, user_id, body, ids.admin_id)
    second = _act(sessions, routes.block_user, user_id, body, ids.admin_id)
    assert first["changed"] is True and second["changed"] is False
    assert first["profile"]["is_active"] is False
    with sessions() as db:
        assert db.get(User, user_id).session_version == before_version + 1
    [entry] = _entries(sessions)
    assert (entry.action, entry.before, entry.after, entry.reason) == (
        "user.blocked", {"is_active": True}, {"is_active": False}, "spam bot")


def test_block_rejects_old_token_even_after_unblock(database):
    from fastapi.security import HTTPAuthorizationCredentials
    from core.security import create_access_token, get_current_user
    sessions, ids = database
    with sessions() as db:
        target = _user(db, "token-holder")
        db.commit()
        user_id, username, version = target.id, target.username, target.session_version
    old = HTTPAuthorizationCredentials(scheme="Bearer",
                                       credentials=create_access_token({"sub": username, "sv": version}))
    _act(sessions, routes.block_user, user_id, routes.ReasonBody(reason="spam bot"), ids.admin_id)
    with sessions() as db:
        with pytest.raises(HTTPException) as exc:
            get_current_user(request=None, credentials=old, db=db)
    assert exc.value.status_code == 403  # inactive user
    _act(sessions, routes.unblock_user, user_id, routes.ReasonBody(reason="appeal ok"), ids.admin_id)
    with sessions() as db:
        with pytest.raises(HTTPException) as exc:
            get_current_user(request=None, credentials=old, db=db)
    assert exc.value.status_code == 401  # session_version moved on


def test_unblock_restores_access_without_touching_sessions(database):
    sessions, ids = database
    with sessions() as db:
        target = _user(db, "returning", active=False)
        db.commit()
        user_id, version = target.id, target.session_version
    result = _act(sessions, routes.unblock_user, user_id, routes.ReasonBody(reason="appeal ok"), ids.admin_id)
    assert result["changed"] is True and result["profile"]["is_active"] is True
    with sessions() as db:
        assert db.get(User, user_id).session_version == version
    assert [e.action for e in _entries(sessions)] == ["user.unblocked"]


@pytest.mark.parametrize("target, code, status", [("self", "cannot_block_self", 400),
                                                  ("other-admin", "cannot_block_admin", 409)])
def test_block_guards(database, target, code, status):
    sessions, ids = database
    with sessions() as db:
        other = _user(db, "second-admin", role="admin")
        db.commit()
        user_id = ids.admin_id if target == "self" else other.id
    with pytest.raises(HTTPException) as exc:
        _act(sessions, routes.block_user, user_id, routes.ReasonBody(reason="testing"), ids.admin_id)
    assert (exc.value.status_code, exc.value.detail["code"]) == (status, code)
    assert _entries(sessions) == []


def test_block_missing_user_is_404(database):
    sessions, ids = database
    with pytest.raises(HTTPException) as exc:
        _act(sessions, routes.block_user, uuid4(), routes.ReasonBody(reason="testing"), ids.admin_id)
    assert exc.value.detail["code"] == "user_not_found"


def test_blocked_user_cannot_be_promoted(database):
    sessions, ids = database
    with sessions() as db:
        target = _user(db, "blocked-promo", active=False)
        db.commit()
        user_id = target.id
    with pytest.raises(HTTPException) as exc:
        _act(sessions, routes.update_user_role, user_id, routes.RoleUpdate(role="admin", reason="promote"),
             ids.admin_id)
    assert (exc.value.status_code, exc.value.detail["code"]) == (409, "user_blocked")


def test_journal_failure_rolls_back_block(database, monkeypatch):
    sessions, ids = database
    with sessions() as db:
        target = _user(db, "rollback-block")
        db.commit()
        user_id = target.id

    def broken(*_args, **_kwargs):
        raise RuntimeError("journal unavailable")

    monkeypatch.setattr(routes, "record_admin_action", broken)
    with sessions() as db:
        with pytest.raises(RuntimeError):
            routes.block_user(user_id, routes.ReasonBody(reason="spam bot"), admin=db.get(User, ids.admin_id), db=db)
        db.rollback()
    with sessions() as db:
        assert db.get(User, user_id).is_active is True
    assert _entries(sessions) == []
```

In `test_admin_postgres.py` add a feedback 404 code assertion:

```python
def test_missing_feedback_is_coded_404(database):
    sessions, ids = database
    with sessions() as db:
        with pytest.raises(HTTPException) as exc:
            admin_routes.update_feedback_status(uuid4(), admin_routes.FeedbackStatusUpdate(status="fixed"),
                                                db.get(User, ids.admin_id), db)
    assert exc.value.detail == {"code": "feedback_not_found", "message": "Feedback not found"}
```

- [ ] **Step 2: Run to verify failure**

`rtk python -m pytest tests/test_admin_users_postgres.py tests/test_admin_postgres.py -q` → failures on missing `ReasonBody`, `block_user`, etc.

- [ ] **Step 3: Implement**

`backend/core/admin_audit.py`:

```python
ADMIN_ACTIONS = frozenset({
    "user.role_changed", "subscription.activated", "feedback.status_changed",
    "user.blocked", "user.unblocked", "subscription.granted", "subscription.canceled",
    "user.password_reset_sent", "user.verification_sent",
})
```

`backend/api/routes/admin.py`: delete `RoleUpdate` and `update_user_role`; in `update_feedback_status` replace the 404 with `raise admin_error(404, "feedback_not_found", "Feedback not found")` (import `admin_error` from `core.admin_users`). Remove now-unused imports (`Field` if unused, etc.) — run `rtk python -m pyflakes api/routes/admin.py` if available, otherwise read the import list.

Append to `backend/api/routes/admin_users.py` (imports: `from pydantic import BaseModel, Field`, `from core.admin_audit import record_admin_action`, `from core.admin_users import Reason`):

```python
class ReasonBody(BaseModel):
    reason: Reason


class RoleUpdate(BaseModel):
    role: str = Field(pattern="^(user|admin)$")
    reason: Reason


def finish(db: Session, user: User, changed: bool, **extra) -> dict:
    db.commit()
    db.refresh(user)
    return {"changed": changed, **extra, **user_card(db, user)}


@router.patch(
    "/{user_id}/role",
    responses={
        400: {"description": "Admin cannot remove their own admin role"},
        404: {"description": "User not found"},
        409: {"description": "Blocked users cannot be promoted"},
    },
)
def update_user_role(user_id: UUID, body: RoleUpdate, admin: User = Depends(require_admin),
                     db: Session = Depends(get_db)):
    if user_id == admin.id and body.role != "admin":
        raise admin_error(400, "cannot_demote_self", "Administrators cannot remove their own admin role")
    user = locked_user(db, user_id)
    if body.role == "admin" and user.role != "admin" and not user.is_active:
        raise admin_error(409, "user_blocked", "Blocked users cannot be promoted")
    changed = user.role != body.role
    if changed:
        before = {"role": user.role}
        user.role = body.role
        record_admin_action(db, actor=admin, action="user.role_changed", target_type="user", target_id=user.id,
                            before=before, after={"role": user.role}, reason=body.reason)
    return finish(db, user, changed)


@router.post(
    "/{user_id}/block",
    responses={
        400: {"description": "Administrators cannot block themselves"},
        404: {"description": "User not found"},
        409: {"description": "Administrators must be demoted before blocking"},
    },
)
def block_user(user_id: UUID, body: ReasonBody, admin: User = Depends(require_admin),
               db: Session = Depends(get_db)):
    if user_id == admin.id:
        raise admin_error(400, "cannot_block_self", "Administrators cannot block themselves")
    user = locked_user(db, user_id)
    if user.role == "admin":
        raise admin_error(409, "cannot_block_admin", "Remove the admin role before blocking")
    changed = user.is_active
    if changed:
        user.is_active = False
        user.session_version = (user.session_version or 0) + 1
        record_admin_action(db, actor=admin, action="user.blocked", target_type="user", target_id=user.id,
                            before={"is_active": True}, after={"is_active": False}, reason=body.reason)
    return finish(db, user, changed)


@router.post("/{user_id}/unblock", responses={404: {"description": "User not found"}})
def unblock_user(user_id: UUID, body: ReasonBody, admin: User = Depends(require_admin),
                 db: Session = Depends(get_db)):
    user = locked_user(db, user_id)
    changed = not user.is_active
    if changed:
        user.is_active = True
        record_admin_action(db, actor=admin, action="user.unblocked", target_type="user", target_id=user.id,
                            before={"is_active": False}, after={"is_active": True}, reason=body.reason)
    return finish(db, user, changed)
```

Note: route functions are called positionally in tests as `func(user_id, body, admin=..., db=...)`; keep parameter order `user_id, body, [background_tasks], admin, db` in every action.

- [ ] **Step 4: Run tests**

`rtk python -m pytest tests/test_admin_users_postgres.py tests/test_admin_postgres.py tests/test_admin_audit.py -q` (PG env) → pass. Then `rtk python -m pytest tests/test_integration.py -q` → pass.

- [ ] **Step 5: Commit**

`feat(admin): coded errors, block/unblock, role change in the users router`.

---

### Task 4: Grant, record payment and early cancel

**Files:**
- Modify: `backend/api/routes/billing.py` (extract `settle_manual_payment`, legacy branch uses it)
- Modify: `backend/core/admin_users.py` (`grant_window`)
- Modify: `backend/api/routes/admin_users.py`
- Modify: `backend/tests/test_admin_users_postgres.py`

**Interfaces:**
- Produces: `api.routes.billing.settle_manual_payment(db, *, admin, user, plan_id, months, reason) -> tuple[BillingCheckout, Payment]` (adds, settles, journals `subscription.activated` with `target_type="user"`; caller commits); `core.admin_users.grant_window(sub, plan, days, now, replace_active) -> tuple[datetime, datetime]`; routes `grant_plan`, `record_payment`, `cancel_subscription` with bodies `GrantRequest(plan, days, replace_active, reason)`, `PaymentRequest(plan, months, reason)`, `CancelRequest(category, reason)`.

- [ ] **Step 1: Write failing tests**

```python
def test_grant_extends_same_plan_without_payment(database):
    sessions, ids = database
    with sessions() as db:
        user = _user(db, "gifted")
        sub = _sub(db, user, "pro", days=10)
        db.commit()
        user_id, old_end = user.id, sub.period_end
    body = routes.GrantRequest(plan="pro", days=30, reason="compensation")
    result = _act(sessions, routes.grant_plan, user_id, body, ids.admin_id)
    with sessions() as db:
        sub = db.query(Subscription).filter_by(user_id=user_id).one()
        assert sub.period_end == old_end + timedelta(days=30) and sub.payment_provider == "grant"
        assert db.query(Payment).count() == 0 and db.query(BillingCheckout).count() == 0
    assert result["subscription"]["source"] == "grant"
    [entry] = _entries(sessions)
    assert entry.action == "subscription.granted" and entry.after["days"] == 30


def test_grant_without_paid_plan_starts_now(database):
    sessions, ids = database
    with sessions() as db:
        user = _user(db, "fresh")
        db.commit()
        user_id = user.id
    _act(sessions, routes.grant_plan, user_id, routes.GrantRequest(plan="business", days=7, reason="partner"),
         ids.admin_id)
    with sessions() as db:
        sub = db.query(Subscription).filter_by(user_id=user_id).one()
        assert sub.plan == "business" and sub.status == "active"
        assert timedelta(days=6, hours=23) < sub.period_end - utc_now() <= timedelta(days=7)


def test_grant_over_other_active_plan_needs_replace_flag(database):
    sessions, ids = database
    with sessions() as db:
        user = _user(db, "switcher")
        _sub(db, user, "business", days=20)
        db.commit()
        user_id = user.id
    with pytest.raises(HTTPException) as exc:
        _act(sessions, routes.grant_plan, user_id, routes.GrantRequest(plan="pro", days=30, reason="downgrade"),
             ids.admin_id)
    assert (exc.value.status_code, exc.value.detail["code"]) == (409, "active_plan_differs")
    assert _entries(sessions) == []
    _act(sessions, routes.grant_plan, user_id,
         routes.GrantRequest(plan="pro", days=30, replace_active=True, reason="downgrade"), ids.admin_id)
    [entry] = _entries(sessions)
    assert entry.before["plan"] == "business" and entry.after["plan"] == "pro"


def test_grant_same_unlimited_plan_is_rejected(database):
    sessions, ids = database
    with sessions() as db:
        user = _user(db, "forever")
        _sub(db, user, "pro", days=None)
        db.commit()
        user_id = user.id
    with pytest.raises(HTTPException) as exc:
        _act(sessions, routes.grant_plan, user_id, routes.GrantRequest(plan="pro", days=5, reason="extra"),
             ids.admin_id)
    assert exc.value.detail["code"] == "plan_unlimited"


@pytest.mark.parametrize("action, body", [
    ("grant_plan", lambda: routes.GrantRequest(plan="pro", days=5, reason="gift")),
    ("record_payment", lambda: routes.PaymentRequest(plan="pro", months=1, reason="cash")),
])
def test_admins_get_no_plan_actions(database, action, body):
    sessions, ids = database
    with pytest.raises(HTTPException) as exc:
        _act(sessions, getattr(routes, action), ids.admin_id, body(), ids.admin_id)
    assert (exc.value.status_code, exc.value.detail["code"]) == (409, "admin_has_business")


def test_record_payment_creates_settled_checkout_and_payment(database):
    sessions, ids = database
    with sessions() as db:
        user = _user(db, "payer")
        db.commit()
        user_id = user.id
    result = _act(sessions, routes.record_payment, user_id,
                  routes.PaymentRequest(plan="pro", months=3, reason="bank transfer #42"), ids.admin_id)
    with sessions() as db:
        [checkout] = db.query(BillingCheckout).all()
        [payment] = db.query(Payment).all()
        assert checkout.status == "paid" and checkout.settled_payment_id == payment.id
        assert checkout.amount_minor == 4900 * 3 and payment.amount_minor == 4900 * 3
    assert result["subscription"]["source"] == "payment"
    [entry] = _entries(sessions)
    assert (entry.action, entry.target_type, entry.reason) == ("subscription.activated", "user", "bank transfer #42")


def test_cancel_ends_access_now_and_records_category(database):
    sessions, ids = database
    with sessions() as db:
        user = _user(db, "refunded")
        _sub(db, user, "pro", days=12)
        db.commit()
        user_id = user.id
    result = _act(sessions, routes.cancel_subscription, user_id,
                  routes.CancelRequest(category="refund", reason="refund via bank"), ids.admin_id)
    assert result["profile"]["effective_plan"] == "free" and result["subscription"]["status"] == "canceled"
    with sessions() as db:
        sub = db.query(Subscription).filter_by(user_id=user_id).one()
        assert sub.period_end <= utc_now()
    [entry] = _entries(sessions)
    assert entry.action == "subscription.canceled" and entry.after["category"] == "refund"
    assert entry.before["status"] == "active"


def test_cancel_without_active_paid_plan_is_409(database):
    sessions, ids = database
    with sessions() as db:
        user = _user(db, "nothing-to-cancel")
        _sub(db, user, "pro", days=-1)
        db.commit()
        user_id = user.id
    with pytest.raises(HTTPException) as exc:
        _act(sessions, routes.cancel_subscription, user_id,
             routes.CancelRequest(category="other", reason="cleanup"), ids.admin_id)
    assert (exc.value.status_code, exc.value.detail["code"]) == (409, "no_active_subscription")


@pytest.mark.parametrize("action, body, patch_target", [
    ("grant_plan", lambda: routes.GrantRequest(plan="pro", days=5, reason="gift"), "routes"),
    ("cancel_subscription", lambda: routes.CancelRequest(category="fraud", reason="chargeback"), "routes"),
    ("record_payment", lambda: routes.PaymentRequest(plan="pro", months=1, reason="cash"), "billing"),
])
def test_journal_failure_rolls_back_plan_actions(database, monkeypatch, action, body, patch_target):
    from api.routes import billing as billing_routes
    sessions, ids = database
    with sessions() as db:
        user = _user(db, "rollback-plan")
        if action == "cancel_subscription":
            _sub(db, user, "pro", days=10)
        db.commit()
        user_id = user.id

    def broken(*_args, **_kwargs):
        raise RuntimeError("journal unavailable")

    monkeypatch.setattr(routes if patch_target == "routes" else billing_routes, "record_admin_action", broken)
    with sessions() as db:
        with pytest.raises(RuntimeError):
            getattr(routes, action)(user_id, body(), admin=db.get(User, ids.admin_id), db=db)
        db.rollback()
    with sessions() as db:
        subs = db.query(Subscription).filter_by(user_id=user_id).all()
        if action == "cancel_subscription":
            assert subs[0].status == "active"
        else:
            assert subs == []
        assert db.query(Payment).count() == 0 and db.query(BillingCheckout).count() == 0
    assert _entries(sessions) == []
```

Also rerun the existing legacy-activation tests (they must stay green unchanged): `tests/test_integration.py::test_admin_legacy...` (the test near line 351) and `tests/test_admin_postgres.py::test_journal_failure_rolls_back_activation`.

- [ ] **Step 2: Run to verify failure**

`rtk python -m pytest tests/test_admin_users_postgres.py -q -k "grant or payment or cancel"` → missing attributes.

- [ ] **Step 3: Implement**

`backend/api/routes/billing.py` — add above `activate_subscription`:

```python
def settle_manual_payment(db: Session, *, admin: User, user: User, plan_id: str, months: int,
                          reason: Optional[str]) -> tuple[BillingCheckout, Payment]:
    """Record an off-platform payment as a manual checkout settled at once; the caller commits."""
    before = _subscription_snapshot(db, user.id)
    plan = PLAN_CATALOG[plan_id]
    now = utc_now()
    checkout = BillingCheckout(
        user_id=user.id,
        plan=plan.id,
        months=months,
        amount_minor=plan.price_minor * months,
        currency=plan.currency,
        provider="manual",
        status="pending",
        idempotency_key=f"legacy-admin:{now.timestamp()}:{user.id}",
        expires_at=now + timedelta(hours=1),
    )
    db.add(checkout)
    db.flush()
    payment = _settle_checkout(db, user, checkout, "manual", None)
    db.flush()
    record_admin_action(db, actor=admin, action="subscription.activated", target_type="user",
                        target_id=user.id, before=before,
                        after=_subscription_snapshot(db, user.id), reason=reason)
    return checkout, payment
```

and replace the legacy branch body (from `before = _subscription_snapshot(db, user.id)` through the `record_admin_action(...)` call after `_settle_checkout`) with:

```python
    legacy_checkout, payment = settle_manual_payment(db, admin=admin, user=user, plan_id=body.plan or "",
                                                     months=body.months, reason=body.reason)
```

keeping the following `db.commit()` and the response unchanged.

`backend/core/admin_users.py` — append:

```python
def grant_window(sub, plan: str, days: int, now, replace_active: bool) -> tuple:
    """(period_start, period_end) for a free grant; raises coded 409s instead of losing paid time."""
    if paid_subscription_active(sub, now):
        if sub.plan == plan:
            if sub.period_end is None:
                raise admin_error(409, "plan_unlimited", "The active plan has no end date")
            return sub.period_start or now, sub.period_end + timedelta(days=days)
        if not replace_active:
            raise admin_error(409, "active_plan_differs", "Another paid plan is active")
    return now, now + timedelta(days=days)
```

`backend/api/routes/admin_users.py` — append (imports: `from api.routes.billing import settle_manual_payment`, `from core.admin_users import grant_window, paid_subscription_active, subscription_snapshot`, `from core.time_utils import utc_now`, `from models import Subscription`):

```python
class GrantRequest(BaseModel):
    plan: Literal["pro", "business"]
    days: int = Field(ge=1, le=366)
    replace_active: bool = False
    reason: Reason


class PaymentRequest(BaseModel):
    plan: Literal["pro", "business"]
    months: int = Field(ge=1, le=24)
    reason: Reason


class CancelRequest(BaseModel):
    category: Literal["refund", "mistaken_activation", "fraud", "other"]
    reason: Reason


def _locked_subscription(db: Session, user: User):
    return db.query(Subscription).filter_by(user_id=user.id).with_for_update().first()


def _not_admin(user: User) -> None:
    if user.role == "admin":
        raise admin_error(409, "admin_has_business", "Administrators already have the business plan")


@router.post(
    "/{user_id}/grant",
    responses={
        404: {"description": "User not found"},
        409: {"description": "Administrator, another active plan or an unlimited plan"},
    },
)
def grant_plan(user_id: UUID, body: GrantRequest, admin: User = Depends(require_admin),
               db: Session = Depends(get_db)):
    user = locked_user(db, user_id)
    _not_admin(user)
    sub = _locked_subscription(db, user)
    start, end = grant_window(sub, body.plan, body.days, utc_now(), body.replace_active)
    before = subscription_snapshot(sub)
    if sub is None:
        sub = Subscription(user_id=user.id)
        db.add(sub)
    sub.plan, sub.status, sub.period_start, sub.period_end = body.plan, "active", start, end
    sub.payment_provider, sub.auto_renew = "grant", False
    db.flush()
    record_admin_action(db, actor=admin, action="subscription.granted", target_type="user", target_id=user.id,
                        before=before, after={**subscription_snapshot(sub), "days": body.days}, reason=body.reason)
    return finish(db, user, True)


@router.post(
    "/{user_id}/record-payment",
    responses={
        404: {"description": "User not found"},
        409: {"description": "Administrators already have the business plan"},
    },
)
def record_payment(user_id: UUID, body: PaymentRequest, admin: User = Depends(require_admin),
                   db: Session = Depends(get_db)):
    user = locked_user(db, user_id)
    _not_admin(user)
    settle_manual_payment(db, admin=admin, user=user, plan_id=body.plan, months=body.months, reason=body.reason)
    return finish(db, user, True)


@router.post(
    "/{user_id}/cancel-subscription",
    responses={
        404: {"description": "User not found"},
        409: {"description": "No active paid subscription"},
    },
)
def cancel_subscription(user_id: UUID, body: CancelRequest, admin: User = Depends(require_admin),
                        db: Session = Depends(get_db)):
    user = locked_user(db, user_id)
    sub = _locked_subscription(db, user)
    now = utc_now()
    if user.role == "admin" or not paid_subscription_active(sub, now):
        raise admin_error(409, "no_active_subscription", "No active paid subscription")
    before = subscription_snapshot(sub)
    sub.status, sub.period_end = "canceled", now
    db.flush()
    record_admin_action(db, actor=admin, action="subscription.canceled", target_type="user", target_id=user.id,
                        before=before, after={**subscription_snapshot(sub), "category": body.category},
                        reason=body.reason)
    return finish(db, user, True)
```

- [ ] **Step 4: Run tests**

PG: `rtk python -m pytest tests/test_admin_users_postgres.py tests/test_admin_postgres.py tests/test_billing_review_postgres.py -q`; non-PG: `rtk python -m pytest tests/test_integration.py -q` → pass.

- [ ] **Step 5: Commit**

`feat(admin): grant, record payment and early cancel from the user card`.

---

### Task 5: Password-reset and verification emails

**Files:**
- Modify: `backend/api/routes/admin_users.py`
- Modify: `backend/tests/test_admin_users_postgres.py`
- Modify: `backend/tests/test_integration.py` (403 for every new route)

**Interfaces:**
- Produces: `send_password_reset(user_id, body, background_tasks, admin, db)`, `resend_verification(user_id, body, background_tasks, admin, db)`; responses add `"sent": bool`.

- [ ] **Step 1: Write failing tests**

```python
from fastapi import BackgroundTasks  # top-level import


def _email(sessions, func, user_id, admin_id):
    tasks = BackgroundTasks()
    with sessions() as db:
        result = func(user_id, routes.ReasonBody(reason="customer asked"), tasks,
                      admin=db.get(User, admin_id), db=db)
    return result, tasks


def test_password_reset_is_sent_once_then_cooldown(database, monkeypatch):
    sessions, ids = database
    monkeypatch.setattr(settings, "EMAIL_DELIVERY_ENABLED", True)
    with sessions() as db:
        user = _user(db, "forgetful")
        db.commit()
        user_id = user.id
    first, tasks = _email(sessions, routes.send_password_reset, user_id, ids.admin_id)
    assert first["sent"] is True and first["changed"] is True and len(tasks.tasks) == 1
    second, tasks = _email(sessions, routes.send_password_reset, user_id, ids.admin_id)
    assert second["sent"] is False and second["changed"] is False and tasks.tasks == []
    [entry] = _entries(sessions)
    assert entry.action == "user.password_reset_sent" and entry.before is None and entry.after is None


def test_email_guards(database, monkeypatch):
    sessions, ids = database
    monkeypatch.setattr(settings, "EMAIL_DELIVERY_ENABLED", True)
    with sessions() as db:
        blocked = _user(db, "blocked-mail", active=False)
        verified = _user(db, "verified-mail")
        db.commit()
        blocked_id, verified_id = blocked.id, verified.id
    with pytest.raises(HTTPException) as exc:
        _email(sessions, routes.send_password_reset, blocked_id, ids.admin_id)
    assert (exc.value.status_code, exc.value.detail["code"]) == (409, "user_blocked")
    with pytest.raises(HTTPException) as exc:
        _email(sessions, routes.resend_verification, verified_id, ids.admin_id)
    assert (exc.value.status_code, exc.value.detail["code"]) == (409, "email_already_verified")
    monkeypatch.setattr(settings, "EMAIL_DELIVERY_ENABLED", False)
    with pytest.raises(HTTPException) as exc:
        _email(sessions, routes.send_password_reset, verified_id, ids.admin_id)
    assert (exc.value.status_code, exc.value.detail["code"]) == (503, "email_unavailable")
    assert _entries(sessions) == []


def test_verification_email_for_unverified_user(database, monkeypatch):
    sessions, ids = database
    monkeypatch.setattr(settings, "EMAIL_DELIVERY_ENABLED", True)
    with sessions() as db:
        user = _user(db, "unverified-mail", verified=False)
        db.commit()
        user_id = user.id
    result, tasks = _email(sessions, routes.resend_verification, user_id, ids.admin_id)
    assert result["sent"] is True and len(tasks.tasks) == 1
    assert [e.action for e in _entries(sessions)] == ["user.verification_sent"]
```

In `backend/tests/test_integration.py` add:

```python
def test_non_admin_is_forbidden_from_user_management(client):
    register_and_login(client, "plain-user-2")
    some_id = "00000000-0000-0000-0000-000000000001"
    assert client.get("/api/v1/admin/users").status_code == 403
    assert client.get(f"/api/v1/admin/users/{some_id}").status_code == 403
    assert client.patch(f"/api/v1/admin/users/{some_id}/role",
                        json={"role": "admin", "reason": "self-promotion"}).status_code == 403
    for action, body in (("block", {}), ("unblock", {}), ("grant", {"plan": "pro", "days": 5}),
                         ("record-payment", {"plan": "pro", "months": 1}),
                         ("cancel-subscription", {"category": "other"}),
                         ("send-password-reset", {}), ("resend-verification", {})):
        response = client.post(f"/api/v1/admin/users/{some_id}/{action}", json={**body, "reason": "trying"})
        assert response.status_code == 403, action
```

- [ ] **Step 2: Run to verify failure** — `-k "email or forbidden_from_user"` → missing attributes / 404s.

- [ ] **Step 3: Implement**

Append to `backend/api/routes/admin_users.py` (imports: `from datetime import timedelta`, `from fastapi import BackgroundTasks`, `from core.auth_tokens import EMAIL_VERIFICATION, PASSWORD_RESET, issue_action_token`, `from core.config import settings`, `from core.email_delivery import send_auth_email`):

```python
def _send_action_email(db: Session, background_tasks: BackgroundTasks, *, admin: User, user: User,
                       purpose: str, lifetime: timedelta, action: str, reason: str) -> dict:
    if not settings.EMAIL_DELIVERY_ENABLED:
        raise admin_error(503, "email_unavailable", "Email delivery is not configured")
    raw_token = issue_action_token(db, user=user, purpose=purpose, lifetime=lifetime,
                                   cooldown_seconds=settings.AUTH_EMAIL_RESEND_COOLDOWN_SECONDS)
    if raw_token:
        record_admin_action(db, actor=admin, action=action, target_type="user", target_id=user.id, reason=reason)
        db.commit()
        background_tasks.add_task(send_auth_email, purpose, user.email, raw_token)
    return finish(db, user, bool(raw_token), sent=bool(raw_token))


@router.post(
    "/{user_id}/send-password-reset",
    responses={
        404: {"description": "User not found"},
        409: {"description": "User is blocked"},
        503: {"description": "Email delivery is not configured"},
    },
)
def send_password_reset(user_id: UUID, body: ReasonBody, background_tasks: BackgroundTasks,
                        admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = locked_user(db, user_id)
    if not user.is_active:
        raise admin_error(409, "user_blocked", "User is blocked")
    return _send_action_email(db, background_tasks, admin=admin, user=user, purpose=PASSWORD_RESET,
                              lifetime=timedelta(minutes=settings.AUTH_PASSWORD_RESET_MINUTES),
                              action="user.password_reset_sent", reason=body.reason)


@router.post(
    "/{user_id}/resend-verification",
    responses={
        404: {"description": "User not found"},
        409: {"description": "Email is already verified"},
        503: {"description": "Email delivery is not configured"},
    },
)
def resend_verification(user_id: UUID, body: ReasonBody, background_tasks: BackgroundTasks,
                        admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = locked_user(db, user_id)
    if user.email_verified:
        raise admin_error(409, "email_already_verified", "Email is already verified")
    return _send_action_email(db, background_tasks, admin=admin, user=user, purpose=EMAIL_VERIFICATION,
                              lifetime=timedelta(hours=settings.AUTH_EMAIL_VERIFICATION_HOURS),
                              action="user.verification_sent", reason=body.reason)
```

Note: if the user is unchanged in `finish` after an earlier `db.commit()`, `db.commit()` again is a harmless no-op.

- [ ] **Step 4: Run the whole backend gate**

PG (one call, CI order): `rtk python -m pytest tests/test_billing_provider_postgres.py tests/test_admin_postgres.py tests/test_admin_users_postgres.py tests/test_billing_review_postgres.py -q`
Non-PG: `rtk python -m pytest tests/test_admin_audit.py tests/test_public_config.py tests/test_integration.py tests/test_plan_quotas.py tests/test_security_hardening.py -q`
Also `rtk python -c "from api.main import app; import json; paths=app.openapi()['paths']; print(sorted(p for p in paths if '/admin/users' in p))"` lists the 9 routes.

- [ ] **Step 5: Commit**

`feat(admin): password-reset and verification emails from the user card`.

---

### Task 6: Frontend foundation — fetch hook, coded errors, copy, dialog

**Files:**
- Create: `frontend/lib/use-admin-fetch.ts`, `frontend/lib/admin-api.ts`
- Modify: `frontend/lib/admin-types.ts`, `frontend/lib/admin-i18n.ts`, `frontend/components/admin/ConfirmDialog.tsx`, `frontend/app/admin/audit/page.tsx`

**Interfaces:**
- Produces:
  - `useAdminFetch<T>(url: string | null): { data: T | null; error: boolean; status: number | null; loading: boolean; reload: () => void; setData: (d: T) => void }`
  - `adminSend<T>(url, method: 'POST' | 'PATCH', body: object): Promise<T>` throwing `AdminApiError { status; code: string | null; message }`; `errorText(c, error): string`
  - Types `PlanId = 'free' | 'pro' | 'business'`, `AdminUserRow`, `UsersPage`, `UserCard`, `UserCardResponse = UserCard & { changed: boolean; sent?: boolean }`
  - `ADMIN_ACTIONS` (const tuple of the 9 action strings), `actionLabel(c, action)`, copy sections `c.users`, `c.card`, `c.errors`, `c.common.reasonRequired`
  - `ConfirmDialog` new optional props: `reasonRequired?: boolean`, `canConfirm?: boolean`, `children?: ReactNode` (rendered between description and reason).

- [ ] **Step 1: `use-admin-fetch.ts`**

```ts
'use client';

import { useCallback, useEffect, useState } from 'react';
import { authFetch } from '@/lib/auth';

type Loaded<T> = { key: string | null; data: T | null; error: boolean; status: number | null };

/** GET `url` with the admin token; a newer url (or reload) aborts the older request so a slow
 *  stale response can never overwrite fresh data. `null` skips the request. */
export function useAdminFetch<T>(url: string | null) {
  const [nonce, setNonce] = useState(0);
  const [loaded, setLoaded] = useState<Loaded<T>>({ key: null, data: null, error: false, status: null });
  const key = url === null ? null : `${nonce}|${url}`;

  useEffect(() => {
    if (url === null) return;
    const controller = new AbortController();
    const requestKey = `${nonce}|${url}`;
    authFetch(url, { signal: controller.signal })
      .then(async (res) => {
        if (!res.ok) throw Object.assign(new Error('http'), { status: res.status });
        const data = (await res.json()) as T;
        if (!controller.signal.aborted) setLoaded({ key: requestKey, data, error: false, status: res.status });
      })
      .catch((e: { status?: number }) => {
        if (controller.signal.aborted) return;
        setLoaded((prev) => ({ key: requestKey, data: prev.data, error: true, status: e.status ?? 0 }));
      });
    return () => controller.abort();
  }, [url, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  const setData = useCallback((data: T) => setLoaded((prev) => ({ ...prev, data, error: false })), []);
  const current = loaded.key === key;
  return {
    data: loaded.data,
    error: current && loaded.error,
    status: current ? loaded.status : null,
    loading: key !== null && !current,
    reload,
    setData,
  };
}
```

- [ ] **Step 2: `admin-api.ts`**

```ts
import { authFetch } from '@/lib/auth';
import type { AdminCopy, AdminErrorCode } from '@/lib/admin-i18n';

export class AdminApiError extends Error {
  constructor(readonly status: number, readonly code: string | null, message: string) {
    super(message);
  }
}

function detailCode(detail: unknown): string | null {
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    const code = (detail as { code?: unknown }).code;
    return typeof code === 'string' ? code : null;
  }
  return null;
}

export async function adminSend<T>(url: string, method: 'POST' | 'PATCH', body: object): Promise<T> {
  const res = await authFetch(url, { method, body: JSON.stringify(body) });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (data as { detail?: unknown }).detail;
    throw new AdminApiError(res.status, detailCode(detail), typeof detail === 'string' ? detail : '');
  }
  return data as T;
}

/** Localised text for a failed admin request: coded errors first, then a plain string detail. */
export function errorText(c: AdminCopy, error: unknown): string {
  if (error instanceof AdminApiError) {
    if (error.code && error.code in c.errors) return c.errors[error.code as AdminErrorCode];
    if (error.message) return error.message;
  }
  return c.common.saveError;
}
```

- [ ] **Step 3: Types in `admin-types.ts`** (append)

```ts
export type PlanId = 'free' | 'pro' | 'business';

export interface AdminUserRow {
  id: string; username: string; email: string; role: 'user' | 'admin';
  created_at: string | null; last_login: string | null; plan: PlanId; period_end: string | null;
  is_active: boolean; email_verified: boolean;
}

export interface UsersPage { total: number; items: AdminUserRow[] }

export interface UserCard {
  profile: {
    id: string; username: string; email: string; full_name: string | null; role: 'user' | 'admin';
    effective_plan: PlanId; is_active: boolean; email_verified: boolean;
    created_at: string | null; last_login: string | null;
  };
  subscription: {
    plan: PlanId; status: 'active' | 'past_due' | 'canceled'; period_start: string | null;
    period_end: string | null; days_left: number | null; source: 'grant' | 'payment';
  } | null;
  payments: { id: string; created_at: string | null; amount_minor: number; currency: string; provider: string; status: string }[];
  checkouts: {
    id: string; created_at: string | null; plan: PlanId; months: number; amount_minor: number; currency: string;
    provider: string; status: string; expires_at: string | null;
  }[];
  activity: {
    conversations_7d: number; conversations_30d: number; questions_7d: number; questions_30d: number;
    questions_today: number | null; daily_limit: number | null; feedback_total: number;
  };
}

export type UserCardResponse = UserCard & { changed: boolean; sent?: boolean };
```

- [ ] **Step 4: Copy in `admin-i18n.ts`**

Add exported constants near the top:

```ts
export const ADMIN_ACTIONS = [
  'user.role_changed', 'subscription.activated', 'feedback.status_changed', 'user.blocked', 'user.unblocked',
  'subscription.granted', 'subscription.canceled', 'user.password_reset_sent', 'user.verification_sent',
] as const;
export type AdminAction = (typeof ADMIN_ACTIONS)[number];

export const ADMIN_ERROR_CODES = [
  'user_not_found', 'feedback_not_found', 'cannot_block_self', 'cannot_block_admin', 'cannot_demote_self',
  'user_blocked', 'admin_has_business', 'active_plan_differs', 'plan_unlimited', 'no_active_subscription',
  'email_already_verified', 'email_unavailable',
] as const;
export type AdminErrorCode = (typeof ADMIN_ERROR_CODES)[number];
```

In `ru`:
- `common`: add `reasonRequired: 'Причина (обязательно, не короче 3 символов)'`.
- `audit.actions`: replace `{...} as Record<string, string>` with `{...} satisfies Record<AdminAction, string>` containing the existing three plus `'user.blocked': 'Блокировка', 'user.unblocked': 'Разблокировка', 'subscription.granted': 'Подарок тарифа', 'subscription.canceled': 'Досрочное прекращение', 'user.password_reset_sent': 'Письмо сброса пароля', 'user.verification_sent': 'Письмо подтверждения'`.
- `users`: keep `title, settleTitle, checkoutPlaceholder, settle, settled, replayed, confirmSettle, months, login, email, role, plan, until, lastLogin`; delete `legacyTitle, emailPlaceholder, activate, activated, period, confirmRole, confirmActivate`; add:

```ts
    status: 'Статус', search: 'Поиск по email, логину или имени', planFilter: 'Тариф', statusFilter: 'Статус',
    sortLabel: 'Сортировка', reset: 'Сбросить фильтры', notFound: 'Никого не найдено.',
    plans: { free: 'Free', pro: 'Pro', business: 'Business', expiring: 'Истекает в течение 7 дней' },
    statuses: { active: 'Активен', blocked: 'Заблокирован', unverified: 'Email не подтверждён', admin: 'Администратор' },
    sorts: { created_desc: 'Сначала новые', last_login_desc: 'По последнему входу', period_end_asc: 'По окончанию подписки' },
```

- New section `card`:

```ts
  card: {
    back: '← К списку', notFound: 'Пользователь не найден.',
    profile: 'Профиль', fullName: 'Полное имя', registered: 'Регистрация', lastLogin: 'Последний вход', role: 'Роль',
    subscription: 'Подписка', noSubscription: 'Подписки нет.', plan: 'Тариф', status: 'Статус', until: 'До',
    daysLeft: (n: number) => `осталось ${n} дн.`, source: 'Источник',
    sources: { grant: 'подарок', payment: 'оплата' },
    subStatuses: { active: 'активна', past_due: 'просрочена', canceled: 'прекращена' },
    payments: 'Платежи', checkouts: 'Заявки', date: 'Дата', amount: 'Сумма', provider: 'Способ', state: 'Статус',
    settle: 'Провести', none: 'Записей нет.',
    activity: 'Активность', questions7d: 'Вопросов за 7 дней', questions30d: 'Вопросов за 30 дней',
    conversations: (n: string) => `диалогов: ${n}`, today: 'Вопросов сегодня',
    todayValue: (n: string, m: string) => `${n} из ${m}`, noData: 'нет данных', feedback: 'Обращений',
    actions: 'Действия', access: 'Доступ', subscriptionGroup: 'Подписка', emails: 'Письма',
    block: 'Заблокировать', unblock: 'Разблокировать', changeRole: 'Сменить роль',
    demoteFirst: 'Чтобы заблокировать администратора, сначала снимите роль.',
    grant: 'Подарить или продлить', recordPayment: 'Записать оплату', cancel: 'Прекратить досрочно',
    sendReset: 'Отправить сброс пароля', sendVerification: 'Отправить подтверждение email',
    confirmBlock: (u: string) => `Заблокировать ${u}? Все активные сессии будут завершены.`,
    confirmUnblock: (u: string) => `Разблокировать ${u}?`,
    confirmRole: (u: string) => `Сменить роль ${u}?`, newRole: 'Новая роль',
    grantTitle: (u: string) => `Подарить или продлить тариф для ${u}`, daysLabel: 'Дней', customDays: 'Своё число',
    activeUntil: (d: string) => `Будет активно до ${d}`,
    replaceWarning: (p: string) => `Сейчас активен тариф ${p}. Оставшееся время по нему будет потеряно.`,
    replaceConfirm: 'Заменить текущий тариф',
    paymentTitle: (u: string) => `Записать оплату от ${u}`, monthsLabel: 'Месяцев', amountLabel: 'Сумма по тарифу',
    cancelTitle: (u: string) => `Прекратить подписку ${u} досрочно`, category: 'Причина прекращения',
    categories: { refund: 'Возврат средств', mistaken_activation: 'Ошибочная активация', fraud: 'Мошенничество или chargeback', other: 'Другое' },
    cancelWarning: (n: number) => `Оплачено ещё ${n} дн. Доступ закроется сразу. Возврат денег делается вне системы.`,
    confirmReset: (e: string) => `Отправить письмо для сброса пароля на ${e}?`,
    confirmVerification: (e: string) => `Отправить письмо подтверждения на ${e}?`,
    done: 'Готово.', unchanged: 'Изменений нет: состояние уже такое.',
    emailSent: 'Письмо отправлено.', emailCooldown: 'Письмо уже отправлялось недавно, попробуйте позже.',
  },
```

- New section `errors` (`satisfies Record<AdminErrorCode, string>`):

```ts
  errors: {
    user_not_found: 'Пользователь не найден.', feedback_not_found: 'Обращение не найдено.',
    cannot_block_self: 'Нельзя заблокировать самого себя.', cannot_block_admin: 'Сначала снимите роль администратора.',
    cannot_demote_self: 'Нельзя снять права администратора с самого себя.', user_blocked: 'Пользователь заблокирован.',
    admin_has_business: 'У администратора и так тариф Business.',
    active_plan_differs: 'Активен другой тариф — подтвердите замену.',
    plan_unlimited: 'У текущего тарифа нет даты окончания.', no_active_subscription: 'Нет активной платной подписки.',
    email_already_verified: 'Email уже подтверждён.', email_unavailable: 'Отправка почты не настроена.',
  } satisfies Record<AdminErrorCode, string>,
```

`en` (same keys):
- `common.reasonRequired: 'Reason (required, at least 3 characters)'`
- audit actions: `'user.blocked': 'Block', 'user.unblocked': 'Unblock', 'subscription.granted': 'Plan gift', 'subscription.canceled': 'Early cancellation', 'user.password_reset_sent': 'Password reset email', 'user.verification_sent': 'Verification email'`
- users: `status: 'Status', search: 'Search by email, login or name', planFilter: 'Plan', statusFilter: 'Status', sortLabel: 'Sort', reset: 'Reset filters', notFound: 'No one found.'`, plans `{ free: 'Free', pro: 'Pro', business: 'Business', expiring: 'Expires within 7 days' }`, statuses `{ active: 'Active', blocked: 'Blocked', unverified: 'Email not verified', admin: 'Administrator' }`, sorts `{ created_desc: 'Newest first', last_login_desc: 'By last login', period_end_asc: 'By subscription end' }`
- card: `back: '← Back to list', notFound: 'User not found.', profile: 'Profile', fullName: 'Full name', registered: 'Registered', lastLogin: 'Last login', role: 'Role', subscription: 'Subscription', noSubscription: 'No subscription.', plan: 'Plan', status: 'Status', until: 'Until', daysLeft: (n) => `${n} days left`, source: 'Source', sources: { grant: 'gift', payment: 'payment' }, subStatuses: { active: 'active', past_due: 'past due', canceled: 'ended' }, payments: 'Payments', checkouts: 'Orders', date: 'Date', amount: 'Amount', provider: 'Method', state: 'Status', settle: 'Settle', none: 'No records.', activity: 'Activity', questions7d: 'Questions, 7 days', questions30d: 'Questions, 30 days', conversations: (n) => `conversations: ${n}`, today: 'Questions today', todayValue: (n, m) => `${n} of ${m}`, noData: 'no data', feedback: 'Feedback', actions: 'Actions', access: 'Access', subscriptionGroup: 'Subscription', emails: 'Emails', block: 'Block', unblock: 'Unblock', changeRole: 'Change role', demoteFirst: 'To block an administrator, remove the admin role first.', grant: 'Gift or extend', recordPayment: 'Record payment', cancel: 'End early', sendReset: 'Send password reset', sendVerification: 'Send verification email', confirmBlock: (u) => `Block ${u}? All active sessions will end.`, confirmUnblock: (u) => `Unblock ${u}?`, confirmRole: (u) => `Change ${u}'s role?`, newRole: 'New role', grantTitle: (u) => `Gift or extend a plan for ${u}`, daysLabel: 'Days', customDays: 'Custom', activeUntil: (d) => `Active until ${d}`, replaceWarning: (p) => `${p} is active now. Its remaining time will be lost.`, replaceConfirm: 'Replace the current plan', paymentTitle: (u) => `Record a payment from ${u}`, monthsLabel: 'Months', amountLabel: 'Plan price', cancelTitle: (u) => `End ${u}'s subscription early`, category: 'Reason for ending', categories: { refund: 'Refund', mistaken_activation: 'Mistaken activation', fraud: 'Fraud or chargeback', other: 'Other' }, cancelWarning: (n) => `${n} paid days remain. Access ends now. Refunds are handled outside the system.`, confirmReset: (e) => `Send a password reset email to ${e}?`, confirmVerification: (e) => `Send a verification email to ${e}?`, done: 'Done.', unchanged: 'No change: already in that state.', emailSent: 'Email sent.', emailCooldown: 'An email was sent recently; try again later.'`
- errors: `user_not_found: 'User not found.', feedback_not_found: 'Feedback not found.', cannot_block_self: 'You cannot block yourself.', cannot_block_admin: 'Remove the admin role first.', cannot_demote_self: 'You cannot remove your own admin role.', user_blocked: 'The user is blocked.', admin_has_business: 'Administrators already have Business.', active_plan_differs: 'Another plan is active — confirm the replacement.', plan_unlimited: 'The current plan has no end date.', no_active_subscription: 'No active paid subscription.', email_already_verified: 'Email is already verified.', email_unavailable: 'Email delivery is not configured.'`

`ka`: the same keys, written in Georgian with the `georgian-writing-style` skill (load it, write all new `ka` strings, review them with it before commit). Because `ka: AdminCopy` and `en: AdminCopy` are typed from `ru`, and `audit.actions`/`errors` use `satisfies`, any missing key is a compile error.

Add helper:

```ts
export function actionLabel(c: AdminCopy, action: string): string {
  return (c.audit.actions as Record<string, string>)[action] ?? action;
}
```

Update `frontend/app/admin/audit/page.tsx`: delete the local `ACTIONS` array, import `ADMIN_ACTIONS, actionLabel`, and use `actionLabel(c, …)` in both places that read `c.audit.actions[...]`. Grep the rest of `frontend/app/admin` for `c.audit.actions[` (the dashboard "recent" list) and switch those to `actionLabel` too.

- [ ] **Step 5: Extend `ConfirmDialog`**

Change the signature and body:

```tsx
export function ConfirmDialog({ open, onOpenChange, title, description, confirmLabel, withReason = true,
  reasonRequired = false, canConfirm = true, children, onConfirm }: {
  open: boolean; onOpenChange: (open: boolean) => void; title: string; description?: string;
  confirmLabel?: string; withReason?: boolean; reasonRequired?: boolean; canConfirm?: boolean;
  children?: ReactNode; onConfirm: (reason: string) => Promise<void>;
}) {
```

- import `type ReactNode` from `react`;
- render `{children}` right after the description paragraph;
- the reason label text is `reasonRequired ? c.common.reasonRequired : c.common.reason`; add `required={reasonRequired}` and `minLength={reasonRequired ? 3 : undefined}` to the textarea;
- the confirm button: `disabled={busy || !canConfirm || (reasonRequired && reason.trim().length < 3)}`.

Existing callers (feedback status, billing) are unaffected because all new props are optional.

- [ ] **Step 6: Verify**

From `frontend/`: `rtk npm run type-check`, `rtk npx eslint lib/use-admin-fetch.ts lib/admin-api.ts lib/admin-types.ts lib/admin-i18n.ts components/admin/ConfirmDialog.tsx app/admin/audit/page.tsx`, `rtk npm run check:admin-styles`. The users page still compiles only if it no longer references deleted copy keys — if type-check fails only on `app/admin/users/page.tsx`, temporarily keep the deleted `users.*` keys and delete them in Task 7 (state this in the report).

- [ ] **Step 7: Commit**

`feat(admin): abortable admin fetch, coded error text, stage 2 copy and dialog fields`.

---

### Task 7: The users list page

**Files:**
- Rewrite: `frontend/app/admin/users/page.tsx`
- Modify: `frontend/app/admin/admin.module.css` (filter bar wrap, if needed)
- Modify: `frontend/lib/admin-i18n.ts` (delete leftover legacy `users.*` keys if Task 6 kept them)

**Interfaces:**
- Consumes: `useAdminFetch`, `adminSend`, `errorText`, `AdminUserRow`, `UsersPage`, copy `c.users.*`.
- Produces: link format to the card: `/admin/users/<id>` plus `?back=<encodeURIComponent('?' + listQuery)>` when the list query is non-empty.

- [ ] **Step 1: Write the page**

```tsx
'use client';

import Link from 'next/link';
import { Suspense, useCallback, useEffect, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { adminSend, errorText } from '@/lib/admin-api';
import { formatDate, formatDateTime, formatNumber, useAdminCopy } from '@/lib/admin-i18n';
import type { AdminUserRow, UsersPage } from '@/lib/admin-types';
import { useAdminFetch } from '@/lib/use-admin-fetch';
import { PageHeader } from '@/components/admin/PageHeader';
import { DataTable, type Column } from '@/components/admin/DataTable';
import { Pagination } from '@/components/admin/Pagination';
import { ConfirmDialog } from '@/components/admin/ConfirmDialog';
import { Badge } from '@/components/admin/Badge';
import styles from '../admin.module.css';

const PLAN_FILTERS = ['free', 'pro', 'business', 'expiring'] as const;
const STATUS_FILTERS = ['active', 'blocked', 'unverified', 'admin'] as const;
const SORTS = ['created_desc', 'last_login_desc', 'period_end_asc'] as const;
const LIMIT = 50;

function pick<T extends string>(value: string | null, allowed: readonly T[]): T | '' {
  return value !== null && (allowed as readonly string[]).includes(value) ? (value as T) : '';
}

interface SettleResult { email: string; plan: string; period_end: string | null; replayed: boolean }

function UsersList() {
  const { c, locale } = useAdminCopy();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const q = (params.get('q') ?? '').trim().slice(0, 100);
  const plan = pick(params.get('plan'), PLAN_FILTERS);
  const status = pick(params.get('status'), STATUS_FILTERS);
  const sort = pick(params.get('sort'), SORTS);
  const offset = Math.max(0, Math.floor(Number(params.get('offset')) || 0));

  const update = useCallback((patch: Record<string, string>) => {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(patch)) { if (v) next.set(k, v); else next.delete(k); }
    if (!('offset' in patch)) next.delete('offset');
    const s = next.toString();
    router.replace(s ? `${pathname}?${s}` : pathname, { scroll: false });
  }, [params, pathname, router]);

  // The box follows the URL (back/forward, reset) without clobbering what the user is typing.
  const [draft, setDraft] = useState(q);
  const [seenQ, setSeenQ] = useState(q);
  if (q !== seenQ) { setSeenQ(q); if (draft.trim() !== q) setDraft(q); }
  useEffect(() => {
    if (draft.trim().slice(0, 100) === q) return;
    const t = setTimeout(() => update({ q: draft.trim().slice(0, 100) }), 300);
    return () => clearTimeout(t);
  }, [draft, q, update]);

  const query = new URLSearchParams({ limit: String(LIMIT), offset: String(offset) });
  if (q) query.set('q', q);
  if (plan) query.set('plan', plan);
  if (status) query.set('status', status);
  if (sort) query.set('sort', sort);
  const { data, error, loading, reload } = useAdminFetch<UsersPage>(`/api/v1/admin/users?${query}`);
  const users = data?.items ?? [];
  const total = data?.total ?? 0;
  const filtered = Boolean(q || plan || status || sort);
  const listQuery = params.toString();
  const cardHref = (id: string) => `/admin/users/${id}${listQuery ? `?back=${encodeURIComponent(`?${listQuery}`)}` : ''}`;
  const reset = () => { setDraft(''); router.replace(pathname, { scroll: false }); };

  const [checkoutId, setCheckoutId] = useState('');
  const [settling, setSettling] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const settle = async (reason: string) => {
    if (!settling) return;
    let d: SettleResult;
    try {
      d = await adminSend<SettleResult>('/api/v1/billing/admin/activate', 'POST', { checkout_id: settling, reason });
    } catch (e) {
      throw new Error(errorText(c, e));
    }
    setMessage((d.replayed ? c.users.replayed : c.users.settled)(d.email, d.plan, formatDate(d.period_end, locale)));
    setCheckoutId('');
    reload();
  };

  const columns: Column<AdminUserRow>[] = [
    { key: 'login', header: c.users.login, render: (u) => <Link href={cardHref(u.id)}><strong>{u.username}</strong></Link> },
    { key: 'email', header: c.users.email, render: (u) => u.email },
    { key: 'plan', header: c.users.plan, render: (u) => <Badge tone={u.plan === 'free' ? 'neutral' : 'success'}>{c.users.plans[u.plan]}</Badge> },
    { key: 'until', header: c.users.until, render: (u) => formatDate(u.period_end, locale) },
    { key: 'status', header: c.users.status, render: (u) => !u.is_active
      ? <Badge tone="error">{c.users.statuses.blocked}</Badge>
      : !u.email_verified ? <Badge tone="warning">{c.users.statuses.unverified}</Badge>
      : u.role === 'admin' ? <Badge tone="neutral">{c.users.statuses.admin}</Badge> : c.common.dash },
    { key: 'last', header: c.users.lastLogin, render: (u) => <span className={styles.muted}>{formatDateTime(u.last_login, locale)}</span> },
  ];

  return <div className={styles.page}>
    <PageHeader title={`${c.users.title} (${formatNumber(total, locale)})`} />

    <section className={`liquid-glass ${styles.panel}`}>
      <div className={styles.toolbar}>
        <input className={styles.input} type="search" aria-label={c.users.search} placeholder={c.users.search}
          maxLength={100} value={draft} onChange={(e) => setDraft(e.target.value)} />
        <select className={styles.select} aria-label={c.users.planFilter} value={plan} onChange={(e) => update({ plan: e.target.value })}>
          <option value="">{c.users.planFilter}: {c.common.all}</option>
          {PLAN_FILTERS.map((p) => <option key={p} value={p}>{c.users.plans[p]}</option>)}
        </select>
        <select className={styles.select} aria-label={c.users.statusFilter} value={status} onChange={(e) => update({ status: e.target.value })}>
          <option value="">{c.users.statusFilter}: {c.common.all}</option>
          {STATUS_FILTERS.map((s) => <option key={s} value={s}>{c.users.statuses[s]}</option>)}
        </select>
        <select className={styles.select} aria-label={c.users.sortLabel} value={sort || 'created_desc'}
          onChange={(e) => update({ sort: e.target.value === 'created_desc' ? '' : e.target.value })}>
          {SORTS.map((s) => <option key={s} value={s}>{c.users.sorts[s]}</option>)}
        </select>
        {filtered && <button type="button" className={styles.button} onClick={reset}>{c.users.reset}</button>}
      </div>
    </section>

    <DataTable columns={columns} rows={users} rowKey={(u) => u.id} loading={loading} error={error} onRetry={reload}
      emptyText={filtered ? c.users.notFound : undefined} />
    {!loading && !error && filtered && users.length === 0 &&
      <button type="button" className={styles.button} onClick={reset}>{c.users.reset}</button>}
    <Pagination offset={offset} limit={LIMIT} total={total} onChange={(next) => update({ offset: next ? String(next) : '' })} />

    <section className={`liquid-glass ${styles.panel}`}>
      <h2 className={styles.panelTitle}>{c.users.settleTitle}</h2>
      <div className={styles.toolbar}>
        <input className={styles.input} aria-label={c.users.checkoutPlaceholder} placeholder={c.users.checkoutPlaceholder}
          value={checkoutId} onChange={(e) => setCheckoutId(e.target.value)} />
        <button type="button" className={`${styles.button} ${styles.buttonPrimary}`} disabled={!checkoutId.trim()}
          onClick={() => setSettling(checkoutId.trim())}>{c.users.settle}</button>
      </div>
      {message && <p className={styles.notice} role="status">{message}</p>}
    </section>

    <ConfirmDialog open={settling !== null} onOpenChange={(open) => { if (!open) setSettling(null); }}
      title={c.users.confirmSettle} onConfirm={settle} />
  </div>;
}

export default function AdminUsers() {
  return <Suspense><UsersList /></Suspense>;
}
```

If ESLint flags the nested ternary in the `status` column (SonarCloud also does), extract it into `function StatusBadge({ user, c })` in the same file.

Delete leftover legacy `users.*` copy keys in all three languages if Task 6 kept them.

- [ ] **Step 2: Verify**

`rtk npm run type-check`; `rtk npx eslint app/admin/users/page.tsx lib/admin-i18n.ts`; `rtk npm run check:admin-styles`.

- [ ] **Step 3: Commit**

`feat(admin): users list with search, filters, sort and URL state`.

---

### Task 8: The user card page and action dialogs

**Files:**
- Create: `frontend/app/admin/users/[id]/page.tsx`
- Create: `frontend/app/admin/users/[id]/UserActions.tsx`
- Modify: `frontend/app/admin/admin.module.css`

**Interfaces:**
- Consumes: `useAdminFetch<UserCard>`, `adminSend<UserCardResponse>`, `errorText`, `ConfirmDialog` (`children`, `reasonRequired`, `canConfirm`), `StatTile`, `DataTable`, `Badge`, `AdminState`, `PageHeader`; `GET /api/v1/billing/catalog` → `{ plans: { id: string; price_minor: number; currency: string }[] }`.
- Produces: e2e anchors: section headings use copy `c.card.profile|subscription|activity|actions`; buttons use copy labels.

- [ ] **Step 1: CSS additions** (append to `admin.module.css`)

```css
.cardGrid { display: grid; gap: 1rem; grid-template-columns: repeat(auto-fit, minmax(min(100%, 22rem), 1fr)); }
.facts { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: 0.4rem 1rem; margin: 0; }
.facts dt { color: var(--muted-foreground); }
.facts dd { margin: 0; overflow-wrap: anywhere; }
.badges { display: flex; flex-wrap: wrap; gap: 0.4rem; }
.actionGroup { display: grid; gap: 0.5rem; }
.actionGroup h3 { margin: 0; font-size: 0.85rem; color: var(--muted-foreground); text-transform: uppercase; letter-spacing: 0.04em; }
.checkbox { display: flex; gap: 0.5rem; align-items: center; }
.warning { color: #d97706; }
```

- [ ] **Step 2: `page.tsx`**

```tsx
'use client';

import Link from 'next/link';
import { Suspense, useState } from 'react';
import { useParams, useSearchParams } from 'next/navigation';
import { formatDate, formatDateTime, formatNumber, useAdminCopy } from '@/lib/admin-i18n';
import type { UserCard } from '@/lib/admin-types';
import { useAdminFetch } from '@/lib/use-admin-fetch';
import { PageHeader } from '@/components/admin/PageHeader';
import { AdminState } from '@/components/admin/AdminState';
import { Badge } from '@/components/admin/Badge';
import { StatTile } from '@/components/admin/StatTile';
import { DataTable, type Column } from '@/components/admin/DataTable';
import { UserActions } from './UserActions';
import styles from '../../admin.module.css';

function money(minor: number, currency: string, locale: string | string[]) {
  return new Intl.NumberFormat(locale, { style: 'currency', currency }).format(minor / 100);
}

function Card() {
  const { c, locale } = useAdminCopy();
  const { id } = useParams<{ id: string }>();
  const back = useSearchParams().get('back');
  const backHref = `/admin/users${back && back.startsWith('?') ? back : ''}`;
  const { data, error, status, loading, reload, setData } = useAdminFetch<UserCard>(`/api/v1/admin/users/${id}`);
  const [notice, setNotice] = useState<string | null>(null);

  const backLink = <Link href={backHref} className={styles.back}>{c.card.back}</Link>;
  if (error && status === 404) return <div className={styles.page}>{backLink}<AdminState kind="empty" message={c.card.notFound} /></div>;
  if (error) return <div className={styles.page}>{backLink}<AdminState kind="error" onRetry={reload} /></div>;
  if (!data || (loading && data.profile.id !== id)) return <div className={styles.page}>{backLink}<AdminState kind="loading" /></div>;

  const { profile, subscription, payments, checkouts, activity } = data;
  const n = (v: number) => formatNumber(v, locale);
  const paymentColumns: Column<UserCard['payments'][number]>[] = [
    { key: 'date', header: c.card.date, render: (p) => formatDateTime(p.created_at, locale) },
    { key: 'amount', header: c.card.amount, render: (p) => money(p.amount_minor, p.currency, locale) },
    { key: 'provider', header: c.card.provider, render: (p) => p.provider },
    { key: 'state', header: c.card.state, render: (p) => p.status },
  ];
  const checkoutColumns: Column<UserCard['checkouts'][number]>[] = [
    { key: 'date', header: c.card.date, render: (o) => formatDateTime(o.created_at, locale) },
    { key: 'plan', header: c.card.plan, render: (o) => `${o.plan} · ${c.users.months(o.months)}` },
    { key: 'amount', header: c.card.amount, render: (o) => money(o.amount_minor, o.currency, locale) },
    { key: 'state', header: c.card.state, render: (o) => <span className={styles.mono}>{o.status}</span> },
  ];

  return <div className={styles.page}>
    {backLink}
    <PageHeader title={profile.username} subtitle={profile.email} />
    <div className={styles.badges}>
      {profile.role === 'admin' && <Badge tone="neutral">{c.users.statuses.admin}</Badge>}
      {!profile.is_active && <Badge tone="error">{c.users.statuses.blocked}</Badge>}
      {!profile.email_verified && <Badge tone="warning">{c.users.statuses.unverified}</Badge>}
      <Badge tone={profile.effective_plan === 'free' ? 'neutral' : 'success'}>{c.users.plans[profile.effective_plan]}</Badge>
    </div>
    {notice && <p className={styles.notice} role="status">{notice}</p>}

    <div className={styles.cardGrid}>
      <section className={`liquid-glass ${styles.panel}`}>
        <h2 className={styles.panelTitle}>{c.card.profile}</h2>
        <dl className={styles.facts}>
          <dt>{c.card.fullName}</dt><dd>{profile.full_name ?? c.common.dash}</dd>
          <dt>{c.card.registered}</dt><dd>{formatDateTime(profile.created_at, locale)}</dd>
          <dt>{c.card.lastLogin}</dt><dd>{formatDateTime(profile.last_login, locale)}</dd>
          <dt>{c.card.role}</dt><dd>{profile.role}</dd>
        </dl>
      </section>

      <section className={`liquid-glass ${styles.panel}`}>
        <h2 className={styles.panelTitle}>{c.card.subscription}</h2>
        {subscription ? <dl className={styles.facts}>
          <dt>{c.card.plan}</dt><dd>{c.users.plans[subscription.plan]}</dd>
          <dt>{c.card.status}</dt><dd>{c.card.subStatuses[subscription.status]}</dd>
          <dt>{c.card.until}</dt><dd>{formatDate(subscription.period_end, locale)}
            {subscription.days_left !== null && <span className={styles.muted}> · {c.card.daysLeft(subscription.days_left)}</span>}</dd>
          <dt>{c.card.source}</dt><dd>{c.card.sources[subscription.source]}</dd>
        </dl> : <p className={styles.muted}>{c.card.noSubscription}</p>}
      </section>
    </div>

    <section>
      <h2 className={styles.panelTitle}>{c.card.activity}</h2>
      <div className={styles.tiles}>
        <StatTile label={c.card.questions7d} value={n(activity.questions_7d)} detail={c.card.conversations(n(activity.conversations_7d))} />
        <StatTile label={c.card.questions30d} value={n(activity.questions_30d)} detail={c.card.conversations(n(activity.conversations_30d))} />
        {activity.daily_limit !== null && <StatTile label={c.card.today}
          value={activity.questions_today === null ? c.common.dash : c.card.todayValue(n(activity.questions_today), n(activity.daily_limit))}
          detail={activity.questions_today === null ? c.card.noData : undefined} />}
        <StatTile label={c.card.feedback} value={n(activity.feedback_total)} />
      </div>
    </section>

    <UserActions card={data} onUpdated={(next, text) => { setData(next); setNotice(text); }} onReload={reload} />

    <section>
      <h2 className={styles.panelTitle}>{c.card.payments}</h2>
      <DataTable columns={paymentColumns} rows={payments} rowKey={(p) => p.id} emptyText={c.card.none} />
    </section>
    <section>
      <h2 className={styles.panelTitle}>{c.card.checkouts}</h2>
      <DataTable columns={checkoutColumns} rows={checkouts} rowKey={(o) => o.id} emptyText={c.card.none} />
    </section>
  </div>;
}

export default function AdminUserCard() {
  return <Suspense><Card /></Suspense>;
}
```

The pending manual checkout "Провести" button lives in `UserActions` (it lists `card.checkouts` filtered to `provider === 'manual' && status === 'pending' && expires_at > now`), so the table stays read-only.

- [ ] **Step 3: `UserActions.tsx`**

```tsx
'use client';

import { useEffect, useState } from 'react';
import { adminSend, errorText } from '@/lib/admin-api';
import { formatDate, useAdminCopy } from '@/lib/admin-i18n';
import type { PlanId, UserCard, UserCardResponse } from '@/lib/admin-types';
import { authFetch } from '@/lib/auth';
import { useAdminFetch } from '@/lib/use-admin-fetch';
import { ConfirmDialog } from '@/components/admin/ConfirmDialog';
import styles from '../../admin.module.css';

type Paid = Exclude<PlanId, 'free'>;
type Category = 'refund' | 'mistaken_activation' | 'fraud' | 'other';
type Dialog = 'block' | 'unblock' | 'role' | 'grant' | 'payment' | 'cancel' | 'reset' | 'verify' | { settle: string } | null;
const DAY = 86_400_000;

/** Client-side preview of core.admin_users.grant_window (the server stays authoritative). */
function grantUntil(card: UserCard, plan: Paid, days: number): Date {
  const sub = card.subscription;
  const sameActive = sub && card.profile.effective_plan === plan && sub.plan === plan && sub.period_end;
  const base = sameActive ? new Date(`${sub.period_end}Z`).getTime() : Date.now();
  return new Date(base + days * DAY);
}

export function UserActions({ card, onUpdated, onReload }: {
  card: UserCard; onUpdated: (card: UserCard, notice: string) => void; onReload: () => void;
}) {
  const { c, locale } = useAdminCopy();
  const { profile, subscription } = card;
  const [dialog, setDialog] = useState<Dialog>(null);
  const [role, setRole] = useState<'user' | 'admin'>(profile.role);
  const [plan, setPlan] = useState<Paid>('pro');
  const [days, setDays] = useState(30);
  const [replace, setReplace] = useState(false);
  const [months, setMonths] = useState(1);
  const [category, setCategory] = useState<Category>('refund');
  const [prices, setPrices] = useState<Record<string, { price_minor: number; currency: string }>>({});
  const me = useAdminFetch<{ username: string }>('/api/v1/auth/me').data;

  useEffect(() => {
    authFetch('/api/v1/billing/catalog').then((r) => (r.ok ? r.json() : null)).then((d) => {
      if (d) setPrices(Object.fromEntries(d.plans.map((p: { id: string; price_minor: number; currency: string }) => [p.id, p])));
    }).catch(() => undefined);
  }, []);

  const isAdmin = profile.role === 'admin';
  const paidActive = !isAdmin && profile.effective_plan !== 'free';
  const otherPlanActive = paidActive && profile.effective_plan !== plan;
  const now = Date.now();
  const settleable = card.checkouts.filter((o) => o.provider === 'manual' && o.status === 'pending'
    && o.expires_at !== null && new Date(`${o.expires_at}Z`).getTime() > now);

  const open = (next: Dialog) => {
    setRole(profile.role); setPlan('pro'); setDays(30); setReplace(false); setMonths(1); setCategory('refund');
    setDialog(next);
  };

  const call = async (path: string, body: object, method: 'POST' | 'PATCH' = 'POST') => {
    let result: UserCardResponse;
    try {
      result = await adminSend<UserCardResponse>(`/api/v1/admin/users/${profile.id}/${path}`, method, body);
    } catch (e) {
      throw new Error(errorText(c, e));
    }
    const text = result.sent === false ? c.card.emailCooldown
      : result.sent ? c.card.emailSent : result.changed ? c.card.done : c.card.unchanged;
    onUpdated(result, text);
  };

  const confirm = async (reason: string) => {
    if (dialog === null) return;
    if (typeof dialog === 'object') {
      try {
        await adminSend('/api/v1/billing/admin/activate', 'POST', { checkout_id: dialog.settle, reason });
      } catch (e) {
        throw new Error(errorText(c, e));
      }
      onReload();
      return;
    }
    const bodies: Record<Exclude<Dialog, null | { settle: string }>, [string, object, ('POST' | 'PATCH')?]> = {
      block: ['block', { reason }], unblock: ['unblock', { reason }], role: ['role', { role, reason }, 'PATCH'],
      grant: ['grant', { plan, days, replace_active: replace, reason }],
      payment: ['record-payment', { plan, months, reason }],
      cancel: ['cancel-subscription', { category, reason }],
      reset: ['send-password-reset', { reason }], verify: ['resend-verification', { reason }],
    };
    const [path, body, method] = bodies[dialog];
    await call(path, body, method);
  };

  const u = profile.username;
  const titles: Record<Exclude<Dialog, null | { settle: string }>, string> = {
    block: c.card.confirmBlock(u), unblock: c.card.confirmUnblock(u), role: c.card.confirmRole(u),
    grant: c.card.grantTitle(u), payment: c.card.paymentTitle(u), cancel: c.card.cancelTitle(u),
    reset: c.card.confirmReset(profile.email), verify: c.card.confirmVerification(profile.email),
  };
  const title = dialog === null ? '' : typeof dialog === 'object' ? c.users.confirmSettle : titles[dialog];
  const price = prices[plan];

  return <section className={`liquid-glass ${styles.panel}`}>
    <h2 className={styles.panelTitle}>{c.card.actions}</h2>
    <div className={styles.cardGrid}>
      <div className={styles.actionGroup}>
        <h3>{c.card.access}</h3>
        {isAdmin ? <p className={styles.muted}>{c.card.demoteFirst}</p>
          : profile.is_active ? <button type="button" className={styles.button} onClick={() => open('block')}>{c.card.block}</button>
          : <button type="button" className={styles.button} onClick={() => open('unblock')}>{c.card.unblock}</button>}
        {me !== null && me.username !== profile.username && <button type="button" className={styles.button} onClick={() => open('role')}>{c.card.changeRole}</button>}
      </div>
      {!isAdmin && <div className={styles.actionGroup}>
        <h3>{c.card.subscriptionGroup}</h3>
        <button type="button" className={styles.button} onClick={() => open('grant')}>{c.card.grant}</button>
        <button type="button" className={styles.button} onClick={() => open('payment')}>{c.card.recordPayment}</button>
        {paidActive && <button type="button" className={styles.button} onClick={() => open('cancel')}>{c.card.cancel}</button>}
        {settleable.map((o) => <button key={o.id} type="button" className={`${styles.button} ${styles.buttonPrimary}`}
          onClick={() => open({ settle: o.id })}>{c.card.settle} · {o.plan} · {c.users.months(o.months)}</button>)}
      </div>}
      <div className={styles.actionGroup}>
        <h3>{c.card.emails}</h3>
        {profile.is_active && <button type="button" className={styles.button} onClick={() => open('reset')}>{c.card.sendReset}</button>}
        {!profile.email_verified && <button type="button" className={styles.button} onClick={() => open('verify')}>{c.card.sendVerification}</button>}
      </div>
    </div>

    <ConfirmDialog open={dialog !== null} onOpenChange={(o) => { if (!o) setDialog(null); }} title={title}
      reasonRequired={typeof dialog !== 'object'}
      canConfirm={!(dialog === 'grant' && otherPlanActive && !replace) && !(dialog === 'role' && role === profile.role)}
      onConfirm={confirm}>
      {dialog === 'role' && <label className={styles.field}>{c.card.newRole}
        <select className={styles.select} value={role} onChange={(e) => setRole(e.target.value as 'user' | 'admin')}>
          <option value="user">user</option><option value="admin">admin</option>
        </select></label>}
      {(dialog === 'grant' || dialog === 'payment') && <label className={styles.field}>{c.card.plan}
        <select className={styles.select} value={plan} onChange={(e) => setPlan(e.target.value as Paid)}>
          <option value="pro">Pro</option><option value="business">Business</option>
        </select></label>}
      {dialog === 'grant' && <>
        <label className={styles.field}>{c.card.daysLabel}
          <input className={styles.input} type="number" min={1} max={366} value={days}
            onChange={(e) => setDays(Math.min(366, Math.max(1, Math.floor(Number(e.target.value) || 1))))} /></label>
        <div className={styles.pills}>{[7, 30, 90].map((d) => <button key={d} type="button" className={styles.chip}
          aria-pressed={days === d} onClick={() => setDays(d)}>{c.users.days(d)}</button>)}</div>
        <p className={styles.muted}>{c.card.activeUntil(formatDate(grantUntil(card, plan, days).toISOString().slice(0, 19), locale))}</p>
        {otherPlanActive && <>
          <p className={styles.warning}>{c.card.replaceWarning(c.users.plans[profile.effective_plan])}</p>
          <label className={styles.checkbox}><input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} />
            {c.card.replaceConfirm}</label>
        </>}
      </>}
      {dialog === 'payment' && <>
        <label className={styles.field}>{c.card.monthsLabel}
          <select className={styles.select} value={months} onChange={(e) => setMonths(Number(e.target.value))}>
            {[1, 3, 6, 12].map((m) => <option key={m} value={m}>{c.users.months(m)}</option>)}
          </select></label>
        {price && <p>{c.card.amountLabel}: <strong>{new Intl.NumberFormat(locale, { style: 'currency', currency: price.currency })
          .format(price.price_minor * months / 100)}</strong></p>}
      </>}
      {dialog === 'cancel' && <>
        <label className={styles.field}>{c.card.category}
          <select className={styles.select} value={category} onChange={(e) => setCategory(e.target.value as Category)}>
            {(['refund', 'mistaken_activation', 'fraud', 'other'] as const).map((k) => <option key={k} value={k}>{c.card.categories[k]}</option>)}
          </select></label>
        <p className={styles.warning}>{c.card.cancelWarning(subscription?.days_left ?? 0)}</p>
      </>}
    </ConfirmDialog>
  </section>;
}
```

Notes:
- `c.users.days` is added in this task: RU `` (n: number) => `${n} дн.` ``, EN `` `${n} days` ``, KA via the `georgian-writing-style` skill.
- "Сменить роль" is hidden on the current admin's own card (`/api/v1/auth/me` username), so self-demotion is impossible from the UI.
- If ESLint or SonarCloud flags the nested ternary in the access group, extract it into a small component in the same file.
- The settle dialog keeps the optional reason (existing settle behaviour): `reasonRequired={typeof dialog !== 'object'}`.

- [ ] **Step 4: Verify**

`rtk npm run type-check`; `rtk npx eslint "app/admin/users/[id]/page.tsx" "app/admin/users/[id]/UserActions.tsx" app/admin/admin.module.css`; `rtk npm run check:admin-styles`; `rtk npm run test:admin-styles`.

- [ ] **Step 5: Commit**

`feat(admin): user card page with journaled action dialogs`.

---

### Task 9: E2E, visual baselines, docs and full verification

**Files:**
- Modify: `frontend/e2e/admin.spec.ts` (fixtures, users-list tests, role-change test moves)
- Create: `frontend/e2e/admin-users.spec.ts`
- Regenerate: `frontend/e2e/__screenshots__/admin-users-ka-mobile.png`; add `admin-user-card-ru-desktop.png`, `admin-user-card-ka-mobile.png`
- Modify: `docs/DEVELOPMENT_MEMORY.md`, `docs/PRODUCTION_OPERATIONS.md`

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Update `admin.spec.ts`**

- Add `is_active: true, email_verified: true` to the `users` fixture row.
- The `/admin/users` entry in the overflow `PAGES` table keeps `ready: text(longEmail)`.
- Delete `role change requires confirmation and sends the reason` (moves to the card spec).
- Keep `Georgian dates render as dd.mm.yyyy` (the list still shows `period_end`).
- Visual test: `admin-users-ka-mobile.png` will change (filter bar, no legacy panel, no role column) — regenerate it in Step 4.

- [ ] **Step 2: Write `admin-users.spec.ts`**

Self-contained (its fixtures differ from `admin.spec.ts`). Mirror the visual test settings of `admin.spec.ts` (fresh page for the second shot, same screenshot options).

```ts
import { expect, Page, Route, test } from '@playwright/test';

const ID = '20000000-0000-0000-0000-000000000001';
const ADMIN_ID = '20000000-0000-0000-0000-000000000009';
const longEmail = `very.long.customer.address.${'x'.repeat(30)}@example-company-domain.ge`;
const row = {
  id: ID, username: 'customer', email: longEmail, role: 'user', created_at: '2026-10-01T10:00:00',
  last_login: '2026-10-10T18:00:00', plan: 'pro', period_end: '2026-11-01T00:00:00', is_active: true, email_verified: true,
};
const card = {
  profile: {
    id: ID, username: 'customer', email: longEmail, full_name: 'Nino Beridze', role: 'user', effective_plan: 'pro',
    is_active: true, email_verified: true, created_at: '2026-10-01T10:00:00', last_login: '2026-10-10T18:00:00',
  },
  subscription: {
    plan: 'pro', status: 'active', period_start: '2026-10-01T00:00:00', period_end: '2026-11-01T00:00:00',
    days_left: 12, source: 'payment',
  },
  payments: [{ id: 'p1', created_at: '2026-10-01T10:05:00', amount_minor: 4900, currency: 'GEL', provider: 'manual', status: 'succeeded' }],
  checkouts: [{
    id: 'c1', created_at: '2026-10-11T08:00:00', plan: 'pro', months: 1, amount_minor: 4900, currency: 'GEL',
    provider: 'manual', status: 'pending', expires_at: '2099-01-01T00:00:00',
  }],
  activity: {
    conversations_7d: 2, conversations_30d: 5, questions_7d: 9, questions_30d: 31,
    questions_today: null, daily_limit: null, feedback_total: 1,
  },
};
const adminCard = {
  ...card, subscription: null, payments: [], checkouts: [],
  profile: { ...card.profile, id: ADMIN_ID, username: 'admin', role: 'admin', effective_plan: 'business' },
};
const catalog = { plans: [{ id: 'pro', price_minor: 4900, currency: 'GEL' }, { id: 'business', price_minor: 14900, currency: 'GEL' }] };
const SEARCH = 'Поиск по email, логину или имени';

type Write = { method: string; path: string; body: unknown };
type Options = {
  lang?: 'ru' | 'ka' | 'en';
  card?: unknown;
  list?: (url: URL) => unknown;
  failWrite?: unknown;
};

async function json(route: Route, data: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
}

async function setup(page: Page, options: Options = {}) {
  const current = options.card ?? card;
  await page.addInitScript((language) => {
    localStorage.setItem('ta_lang', language);
    localStorage.setItem('ta_authenticated', '1');
  }, options.lang ?? 'ru');
  const writes: Write[] = [];
  const listQueries: string[] = [];
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() !== 'GET') {
      writes.push({ method: request.method(), path: url.pathname, body: request.postDataJSON() });
      return options.failWrite
        ? json(route, options.failWrite, 409)
        : json(route, { ...(current as object), changed: true });
    }
    if (url.pathname === '/api/v1/admin/users') {
      listQueries.push(url.search);
      return json(route, options.list ? await options.list(url) : { total: 1, items: [row] });
    }
    const fixtures: Record<string, unknown> = {
      '/api/v1/auth/me': { username: 'admin', role: 'admin' },
      [`/api/v1/admin/users/${ID}`]: current,
      [`/api/v1/admin/users/${ADMIN_ID}`]: adminCard,
      '/api/v1/billing/catalog': catalog,
    };
    return url.pathname in fixtures ? json(route, fixtures[url.pathname]) : json(route, { detail: 'No fixture' }, 404);
  });
  return { writes, listQueries };
}

async function openCardDialog(page: Page, button: string) {
  await page.goto(`/admin/users/${ID}`);
  await page.getByRole('button', { name: button, exact: true }).click();
  const dialog = page.getByRole('dialog');
  return {
    dialog,
    reason: dialog.getByRole('textbox', { name: /Причина/ }),
    confirm: dialog.getByRole('button', { name: 'Подтвердить' }),
  };
}

test('search and filters live in the URL and survive reload', async ({ page }) => {
  const { listQueries } = await setup(page);
  await page.goto('/admin/users');
  await page.getByRole('searchbox', { name: SEARCH }).fill('cust');
  await expect(page).toHaveURL(/\?q=cust$/);
  await page.getByRole('combobox', { name: 'Тариф' }).selectOption('pro');
  await expect(page).toHaveURL(/\?q=cust&plan=pro$/);
  await page.reload();
  await expect(page.getByRole('searchbox', { name: SEARCH })).toHaveValue('cust');
  await expect(page.getByRole('combobox', { name: 'Тариф' })).toHaveValue('pro');
  await expect.poll(() => listQueries.at(-1)).toContain('q=cust');
  expect(listQueries.at(-1)).toContain('plan=pro');
});

test('opening a card and going back keeps the filters', async ({ page }) => {
  await setup(page);
  await page.goto('/admin/users?plan=pro&q=cust');
  await page.getByRole('link', { name: 'customer' }).click();
  await expect(page).toHaveURL(`/admin/users/${ID}?back=${encodeURIComponent('?plan=pro&q=cust')}`);
  await page.getByRole('link', { name: '← К списку' }).click();
  await expect(page).toHaveURL('/admin/users?plan=pro&q=cust');
});

test('a slow stale search response never overwrites the newer result', async ({ page }) => {
  await setup(page, {
    list: async (url) => {
      const q = url.searchParams.get('q');
      if (q === 'a') {
        await new Promise((resolve) => setTimeout(resolve, 1500));
        return { total: 1, items: [{ ...row, id: 'a', username: 'slow-a' }] };
      }
      if (q === 'ab') return { total: 1, items: [{ ...row, id: 'b', username: 'fast-b' }] };
      return { total: 1, items: [row] };
    },
  });
  await page.goto('/admin/users');
  const box = page.getByRole('searchbox', { name: SEARCH });
  await box.fill('a');
  await expect(page).toHaveURL(/\?q=a$/);
  await box.fill('ab');
  await expect(page.getByRole('link', { name: 'fast-b' })).toBeVisible();
  await page.waitForTimeout(2000);
  await expect(page.getByRole('link', { name: 'slow-a' })).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'fast-b' })).toBeVisible();
});

test('empty search result offers a reset', async ({ page }) => {
  await setup(page, {
    list: (url) => (url.searchParams.get('q') === 'zzz' ? { total: 0, items: [] } : { total: 1, items: [row] }),
  });
  await page.goto('/admin/users?q=zzz');
  await expect(page.getByText('Никого не найдено.')).toBeVisible();
  await page.getByRole('button', { name: 'Сбросить фильтры' }).first().click();
  await expect(page).toHaveURL(/\/admin\/users$/);
  await expect(page.getByRole('link', { name: 'customer' })).toBeVisible();
});

test('grant over another active plan requires the replace checkbox', async ({ page }) => {
  const business = {
    ...card,
    profile: { ...card.profile, effective_plan: 'business' },
    subscription: { ...card.subscription, plan: 'business' },
  };
  const { writes } = await setup(page, { card: business });
  const { dialog, reason, confirm } = await openCardDialog(page, 'Подарить или продлить');
  await dialog.getByRole('combobox', { name: 'Тариф' }).selectOption('pro');
  await reason.fill('downgrade on request');
  await expect(confirm).toBeDisabled();
  await dialog.getByRole('checkbox', { name: 'Заменить текущий тариф' }).check();
  await confirm.click();
  await expect(dialog).toBeHidden();
  expect(writes).toEqual([{
    method: 'POST', path: `/api/v1/admin/users/${ID}/grant`,
    body: { plan: 'pro', days: 30, replace_active: true, reason: 'downgrade on request' },
  }]);
});

test('blocking requires a reason of at least 3 characters', async ({ page }) => {
  const { writes } = await setup(page);
  const { reason, confirm } = await openCardDialog(page, 'Заблокировать');
  await reason.fill('ab');
  await expect(confirm).toBeDisabled();
  await reason.fill('spam bot');
  await confirm.click();
  await expect(page.getByText('Готово.')).toBeVisible();
  expect(writes).toEqual([{ method: 'POST', path: `/api/v1/admin/users/${ID}/block`, body: { reason: 'spam bot' } }]);
});

test('early cancel sends the chosen category and warns about paid days', async ({ page }) => {
  const { writes } = await setup(page);
  const { dialog, reason, confirm } = await openCardDialog(page, 'Прекратить досрочно');
  await expect(dialog).toContainText('Оплачено ещё 12 дн.');
  await dialog.getByRole('combobox', { name: 'Причина прекращения' }).selectOption('fraud');
  await reason.fill('chargeback from bank');
  await confirm.click();
  await expect(dialog).toBeHidden();
  expect(writes).toEqual([{
    method: 'POST', path: `/api/v1/admin/users/${ID}/cancel-subscription`,
    body: { category: 'fraud', reason: 'chargeback from bank' },
  }]);
});

test('role change lives in the card and sends PATCH with the reason', async ({ page }) => {
  const { writes } = await setup(page);
  const { dialog, reason, confirm } = await openCardDialog(page, 'Сменить роль');
  await dialog.getByRole('combobox', { name: 'Новая роль' }).selectOption('admin');
  await reason.fill('promote accountant');
  await confirm.click();
  await expect(dialog).toBeHidden();
  expect(writes).toEqual([{
    method: 'PATCH', path: `/api/v1/admin/users/${ID}/role`, body: { role: 'admin', reason: 'promote accountant' },
  }]);
});

test('admin card hides block, role and subscription actions', async ({ page }) => {
  await setup(page);
  await page.goto(`/admin/users/${ADMIN_ID}`);
  await expect(page.getByText('Чтобы заблокировать администратора, сначала снимите роль.')).toBeVisible();
  for (const name of ['Заблокировать', 'Подарить или продлить', 'Записать оплату', 'Сменить роль']) {
    await expect(page.getByRole('button', { name, exact: true })).toHaveCount(0);
  }
});

test('a coded backend error is shown inside the open dialog', async ({ page }) => {
  await setup(page, { failWrite: { detail: { code: 'cannot_block_admin', message: 'Remove the admin role before blocking' } } });
  const { dialog, reason, confirm } = await openCardDialog(page, 'Заблокировать');
  await reason.fill('spam bot');
  await confirm.click();
  await expect(dialog.getByRole('alert')).toHaveText('Сначала снимите роль администратора.');
  await expect(dialog).toBeVisible();
});

test('card has no horizontal scroll on a 390px phone with a long email', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await setup(page);
  await page.goto(`/admin/users/${ID}`);
  await expect(page.getByText('Nino Beridze')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Платежи' })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test('user card visual baseline', async ({ page, browser }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await setup(page);
  await page.goto(`/admin/users/${ID}`);
  await expect(page.getByText('Вопросов за 30 дней')).toBeVisible();
  await expect(page).toHaveScreenshot('admin-user-card-ru-desktop.png', { fullPage: true });
  const mobile = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await setup(mobile, { lang: 'ka' });
  await mobile.goto(`/admin/users/${ID}`);
  await expect(mobile.getByText('Nino Beridze')).toBeVisible();
  await expect(mobile).toHaveScreenshot('admin-user-card-ka-mobile.png', { fullPage: true });
  await mobile.close();
});
```

If a locator's accessible name differs from the copy (for example a label that wraps a select also includes the selected option's text), keep the copy and adjust only the locator (substring match or `getByLabel`).

- [ ] **Step 3: Functional run (Windows, needs a fresh build)**

The local `frontend/.next` is stale. From `frontend/`, in the background with a log: `rtk npm run build > ../.superpowers/build.log 2>&1` (≈15 min; remove a stale `.next/lock` if the build hangs), then
`rtk npx playwright test e2e/admin.spec.ts e2e/admin-users.spec.ts e2e/billing-reconciliation.spec.ts --grep-invert "visual baseline"` → all pass.

- [ ] **Step 4: Baselines in the pinned container**

Move `frontend/.next` aside first (the container writes a Linux build), restore it afterwards. From the repo root in Git Bash, in the background with a log:

```bash
MSYS_NO_PATHCONV=1 rtk docker run --rm --ipc=host -v "F:/New_Projects/Warp/Warp_INFOHUB.GE":/work -v /work/frontend/node_modules -w /work/frontend mcr.microsoft.com/playwright@sha256:dcc5531e97840b9b5e794f2814476b21571c5124a3fca2267d73041f56e7580e bash -c "npm ci --ignore-scripts && npm run build && npx playwright test e2e/admin.spec.ts e2e/admin-users.spec.ts --grep 'visual baseline' --update-snapshots"
```

Append `; echo EXIT=$?` to the log, poll with bounded `sleep 240; tail -5`. Then open the three PNGs with the Read tool and confirm: KA dates `dd.mm.yyyy`, no clipped Georgian labels, card sections present. `admin-dashboard-ru-desktop.png` must be unchanged (`rtk git status` shows it unmodified). No stray backup directory remains; Windows `rtk npm run type-check` still works.

- [ ] **Step 5: Docs**

- `docs/DEVELOPMENT_MEMORY.md`: a short "Admin stage 2 — clients" entry: router `admin_users.py`, coded errors `{code, message}`, grants use `payment_provider='grant'` and create no payments, cancel is immediate, `useAdminFetch` is the pattern for new admin pages.
- `docs/PRODUCTION_OPERATIONS.md`: in the admin section, list the card actions and note "no schema step; normal `deploy.sh`"; blocking ends sessions immediately; refunds stay outside the system.

- [ ] **Step 6: Full verification (paste raw tails in the report)**

Backend non-PG: `rtk python -m pytest tests/test_admin_audit.py tests/test_public_config.py tests/test_integration.py tests/test_plan_quotas.py tests/test_security_hardening.py -q`
Backend PG (CI order): `rtk python -m pytest tests/test_billing_provider_postgres.py tests/test_admin_postgres.py tests/test_admin_users_postgres.py tests/test_billing_review_postgres.py -q`
Frontend: `rtk npm run type-check`, `rtk npm run lint`, `rtk npm run check:admin-styles`, `rtk npm run test:admin-styles`.

- [ ] **Step 7: Commit**

`test(admin): stage 2 e2e, card baselines and docs`.
