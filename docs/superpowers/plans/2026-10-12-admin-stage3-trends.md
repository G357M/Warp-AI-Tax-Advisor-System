# Admin Stage 3 — Trends Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Read-only `/admin/trends` page: revenue, payments, signups, questions, askers, ratings and answer-quality signals as Tbilisi-local time series with a previous-window comparison.

**Architecture:** One admin-only endpoint `GET /api/v1/admin/trends?period=30d|90d|12m` backed by `core/admin_trends.py` (pure window math + grouped SQL aggregates, admins excluded). The frontend page renders tiles and hand-rolled SVG charts via a new `TrendChart` component; period lives in `?period=`.

**Tech Stack:** FastAPI, SQLAlchemy 2 on PostgreSQL, Next.js (app router) + TypeScript, CSS modules, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-12-admin-stage3-trends-design.md`

## Global Constraints

- No schema changes, no new tables, no new deploy step; no new npm/pip dependencies.
- Buckets in Tbilisi local time: naive-UTC `created_at` + 4 h (`TBILISI_OFFSET`), weeks start Monday.
- Periods: `30d` → 30 day buckets, `90d` → 13 week buckets, `12m` → 12 month buckets; default `30d`.
- Users with `role = 'admin'` are excluded from every metric (signups, questions, payments, ratings, answers).
- Revenue = `payments.status = 'succeeded'`, `sum(amount_minor)`; all payments are GEL.
- Previous window: starts `count` buckets before the first current bucket and lasts exactly as long as the elapsed part of the current window (fair comparison with a partial last bucket).
- All admin copy in RU/KA/EN in `lib/admin-i18n.ts`; KA via georgian-writing-style.
- No inline `style={{…}}` in `app/admin/**` except CSS custom properties passed through a `vars()` helper (existing analytics pattern).

## Review Focus

- Activity right after Tbilisi midnight (20:00–23:59 UTC) must land in the next local day — pinned by the window unit test and the postgres seed at 21:00 UTC.
- An empty database / a period with no data must render zeros and "—" deltas, never `NaN%` or `Infinity%` — pinned by the empty postgres test and the e2e empty fixture.
- Quality metrics before stage 4 shipped have no evidence: share must be `null`, not 0% — pinned by `answers_with_evidence == 0` bucket assertions and frontend `share()` returning null.
- A bogus `?period=` in the URL must fall back to `30d` on the page and 422 on the API — pinned by e2e and the route `Literal`.
- Admin test activity must not inflate numbers — pinned by admin seeds in the postgres test.

---

### Task 1: Backend trends core + endpoint

**Files:**
- Modify: `backend/core/admin_quality.py` (rename `_flag_condition` → `flag_condition`, add `has_evidence()`)
- Create: `backend/core/admin_trends.py`
- Create: `backend/api/routes/admin_trends.py`
- Modify: `backend/api/main.py` (import + `include_router`)
- Test: `backend/tests/test_admin_trends.py` (unit, no DB), `backend/tests/test_admin_trends_postgres.py`
- Modify: `.github/workflows/ci.yml` (register both tests)

**Interfaces:**
- Produces: `window(period: str, now: datetime) -> Window`; `Window(bucket, starts: list[date], end: date, previous_start: date)`; `trends(db: Session, period: str, now: datetime) -> dict` (shape = spec §1); route `get_trends(period, db)`.

- [ ] **Step 1: Unit tests for the window** (`test_admin_trends.py`)

```python
from datetime import date, datetime
from pathlib import Path

from core.admin_trends import window

NOW = datetime(2026, 10, 12, 10, 0)  # 14:00 in Tbilisi, a Monday


def test_day_window():
    w = window("30d", NOW)
    assert w.bucket == "day" and len(w.starts) == 30
    assert w.starts[0] == date(2026, 9, 13) and w.starts[-1] == date(2026, 10, 12)
    assert w.end == date(2026, 10, 13) and w.previous_start == date(2026, 8, 14)


def test_local_midnight_moves_the_day():
    assert window("30d", datetime(2026, 10, 11, 20, 30)).starts[-1] == date(2026, 10, 12)
    assert window("30d", datetime(2026, 10, 11, 19, 59)).starts[-1] == date(2026, 10, 11)


def test_week_window_starts_monday():
    w = window("90d", datetime(2026, 10, 15, 10, 0))
    assert w.bucket == "week" and len(w.starts) == 13
    assert w.starts[-1] == date(2026, 10, 12) and w.starts[0] == date(2026, 7, 20)
    assert all(s.weekday() == 0 for s in w.starts)


def test_month_window():
    w = window("12m", NOW)
    assert w.bucket == "month" and len(w.starts) == 12
    assert w.starts[0] == date(2025, 11, 1) and w.starts[-1] == date(2026, 10, 1)
    assert w.end == date(2026, 11, 1) and w.previous_start == date(2024, 11, 1)


def test_router_requires_admin():
    source = (Path(__file__).parents[1] / "api" / "routes" / "admin_trends.py").read_text(encoding="utf-8")
    assert "dependencies=[Depends(require_admin)]" in source
```

- [ ] **Step 2:** `cd backend && python -m pytest tests/test_admin_trends.py -q` → FAIL (module missing).

- [ ] **Step 3: Expose flag helpers in `core/admin_quality.py`**

Rename `_flag_condition` to `flag_condition` (update its callers in the same file) and extract:

```python
def has_evidence():
    # evidence may be SQL NULL or a JSON null (the ORM's JSON type stores None as 'null').
    return func.coalesce(func.jsonb_typeof(cast(Message.evidence, JSONB)), "null") == "object"
```

`flag_condition` uses `has = has_evidence()`.

- [ ] **Step 4: `core/admin_trends.py`**

```python
"""Admin trends: Tbilisi-local time series and the previous-window comparison (read-only)."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import and_, case, distinct, func, or_, select
from sqlalchemy.orm import Session

from core.admin_quality import flag_condition, has_evidence
from models import AnswerRating, Conversation, Message, Payment, Subscription, User

# Georgia has stayed on UTC+4 without daylight saving since 2005; timestamps are naive UTC.
TBILISI_OFFSET = timedelta(hours=4)
PERIODS = {"30d": ("day", 30), "90d": ("week", 13), "12m": ("month", 12)}
TOTAL_KEYS = ("signups", "askers", "questions", "payments", "revenue_minor", "up", "down")
CONTENT_FLAGS = ("no_precise_citation", "no_sources", "not_grounded", "slow")


def _floor(d: date, bucket: str) -> date:
    if bucket == "week":
        return d - timedelta(days=d.weekday())
    if bucket == "month":
        return d.replace(day=1)
    return d


def _step(d: date, bucket: str, n: int) -> date:
    if bucket == "day":
        return d + timedelta(days=n)
    if bucket == "week":
        return d + timedelta(weeks=n)
    month = d.year * 12 + d.month - 1 + n
    return date(month // 12, month % 12 + 1, 1)


def _utc(d: date) -> datetime:
    return datetime.combine(d, datetime.min.time()) - TBILISI_OFFSET


@dataclass(frozen=True)
class Window:
    bucket: str
    starts: list
    end: date
    previous_start: date


def window(period: str, now: datetime) -> Window:
    bucket, count = PERIODS[period]
    last = _floor((now + TBILISI_OFFSET).date(), bucket)
    first = _step(last, bucket, -(count - 1))
    return Window(bucket, [_step(first, bucket, i) for i in range(count)],
                  _step(last, bucket, 1), _step(first, bucket, -count))
```

Sources — each returns `(created_at column, select of aggregate columns with joins/filters)`; `_rows(db, source, lo, hi, bucket)` adds the range filter and optionally `GROUP BY date_trunc(bucket, created_at + offset)`:

```python
def _local_trunc(column, bucket):
    return func.date_trunc(bucket, column + TBILISI_OFFSET)


def _sources():
    owner = and_(Conversation.id == Message.conversation_id, User.id == Conversation.user_id, User.role != "admin")
    flagged = and_(has_evidence(), or_(*(flag_condition(f) for f in CONTENT_FLAGS)))
    return {
        "users": (User.created_at, [func.count(User.id).label("signups")], [User.role != "admin"]),
        "questions": (Message.created_at,
                      [func.count(Message.id).label("questions"),
                       func.count(distinct(Conversation.user_id)).label("askers")],
                      [Message.role == "user", owner]),
        "payments": (Payment.created_at,
                     [func.count(Payment.id).label("payments"),
                      func.coalesce(func.sum(Payment.amount_minor), 0).label("revenue_minor")],
                     [Payment.status == "succeeded", Subscription.id == Payment.subscription_id,
                      User.id == Subscription.user_id, User.role != "admin"]),
        "ratings": (AnswerRating.created_at,
                    [func.coalesce(func.sum(case((AnswerRating.value == 1, 1), else_=0)), 0).label("up"),
                     func.coalesce(func.sum(case((AnswerRating.value == -1, 1), else_=0)), 0).label("down")],
                    [User.id == AnswerRating.user_id, User.role != "admin"]),
        "answers": (Message.created_at,
                    [func.count(Message.id).label("answers"),
                     func.count(Message.id).filter(has_evidence()).label("answers_with_evidence"),
                     func.count(Message.id).filter(flagged).label("flagged"),
                     func.percentile_cont(0.5).within_group(Message.processing_ms).label("median_processing_ms")],
                    [Message.role == "assistant", owner]),
    }


def _query(db, source, lo, hi, bucket=None):
    created, columns, where = source
    stmt = select(*columns).where(*where, created >= lo, created < hi)
    if bucket:
        key = _local_trunc(created, bucket).label("bucket")
        stmt = stmt.add_columns(key).group_by(key)
    return db.execute(stmt).mappings().all()


def _totals(db, sources, lo, hi) -> dict:
    out = {}
    for name in ("users", "questions", "payments", "ratings"):
        out.update({k: int(v or 0) for k, v in _query(db, sources[name], lo, hi)[0].items()})
    return {k: out[k] for k in TOTAL_KEYS}


def _window_median(db, source, lo, hi):
    value = _query(db, source, lo, hi)[0]["median_processing_ms"]
    return None if value is None else int(value)


def trends(db: Session, period: str, now: datetime) -> dict:
    w = window(period, now)
    sources = _sources()
    lo, hi = _utc(w.starts[0]), _utc(w.end)
    buckets = {s: {"start": s.isoformat(), "partial": s == w.starts[-1], "signups": 0, "askers": 0,
                   "questions": 0, "payments": 0, "revenue_minor": 0, "up": 0, "down": 0, "answers": 0,
                   "answers_with_evidence": 0, "flagged": 0, "median_processing_ms": None} for s in w.starts}
    for source in sources.values():
        for row in _query(db, source, lo, hi, w.bucket):
            slot = buckets.get(row["bucket"].date())
            if slot is None:
                continue
            for key, value in row.items():
                if key == "bucket":
                    continue
                slot[key] = None if value is None else int(value)
    previous_lo = _utc(w.previous_start)
    previous_hi = previous_lo + (now - lo)
    first_evidence = db.execute(select(func.min(Message.created_at)).where(
        Message.role == "assistant", has_evidence())).scalar()
    return {
        "period": period, "bucket": w.bucket, "timezone": "Asia/Tbilisi",
        "quality_since": (first_evidence + TBILISI_OFFSET).date().isoformat() if first_evidence else None,
        "median_processing_ms": _window_median(db, sources["answers"], lo, hi),
        "buckets": [buckets[s] for s in w.starts],
        "totals": {"current": _totals(db, sources, lo, min(hi, now + timedelta(seconds=1))),
                   "previous": _totals(db, sources, previous_lo, previous_hi)},
    }
```

(`median_processing_ms` from `percentile_cont` is a float or `None`; `int()` rounds down — acceptable for milliseconds.)

- [ ] **Step 5: Route** `backend/api/routes/admin_trends.py`

```python
"""Admin trends: read-only time series. All endpoints require the admin role."""
from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.admin_trends import trends
from core.database import get_db
from core.security import require_admin
from core.time_utils import utc_now

router = APIRouter(prefix="/admin/trends", tags=["Admin"], dependencies=[Depends(require_admin)])


@router.get("")
def get_trends(period: Literal["30d", "90d", "12m"] = "30d", db: Session = Depends(get_db)):
    return trends(db, period, utc_now())
```

Register in `api/main.py`: add `admin_trends` to the routes import and
`app.include_router(admin_trends.router, prefix=settings.API_PREFIX)  # Admin: trends` after `admin_quality`.

- [ ] **Step 6:** unit tests pass: `python -m pytest tests/test_admin_trends.py tests/test_admin_quality_postgres.py -q` (the latter skips without PG; it guards the rename import).

- [ ] **Step 7: Postgres test** `test_admin_trends_postgres.py` — fixture like `test_admin_quality_postgres.py` (dedicated schema, tables `User, Conversation, Message, Subscription, Payment` + `apply_audit_schema` + `add_answer_quality.apply_schema`), but users get explicit `created_at`. Seeds with `NOW = datetime(2026, 10, 12, 10, 0)`:

| Seed | created_at (UTC) | Expected bucket |
|---|---|---|
| nino signup | 2026-10-11 21:00 | 2026-10-12 |
| levan signup | 2026-10-11 19:00 | 2026-10-11 |
| old signup | 2026-09-01 08:00 | previous window |
| boss (admin) signup | 2026-10-12 08:00 | excluded |
| nino Q+A ×2 (evidence grounded+citation 1000 ms; partial no citation 3000 ms) | 2026-10-12 05:00 | 10-12: questions 2, askers 1, answers 2, with_evidence 2, flagged 1, median 2000 |
| levan Q+A, evidence None, processing None | 2026-10-11 10:00 | 10-11: questions 1, with_evidence 0, median None |
| boss Q+A + up rating + succeeded payment | 2026-10-12 06:00 | excluded |
| nino ratings up (A1), down (A2) | 2026-10-12 07:00 | 10-12: up 1, down 1 |
| nino payment succeeded 4900, failed 4900 | 2026-10-12 06:00 | 10-12: payments 1, revenue 4900 |
| old payment succeeded 2900 | 2026-09-02 08:00 | previous: payments 1, revenue 2900 |

Assertions: 30 buckets, only last `partial`; bucket values above; `totals.current == {signups 2, askers 2, questions 3, payments 1, revenue_minor 4900, up 1, down 1}`; `totals.previous == {signups 1, payments 1, revenue_minor 2900, rest 0}`; `quality_since == "2026-10-12"`; top-level `median_processing_ms == 2000`; `12m` → 12 buckets, last start `2026-10-01`, `totals.current.revenue_minor == 7800` and `signups == 3`. Empty-database test: all bucket metrics 0, medians `None`, `quality_since is None`, totals all 0.

- [ ] **Step 8:** Register in `.github/workflows/ci.yml`: `tests/test_admin_trends.py` after `tests/test_rating_limit.py` (API contracts job); `tests/test_admin_trends_postgres.py` after `tests/test_admin_quality_postgres.py` (PostgreSQL job). Run the postgres test locally if a PG is available (`BILLING_PROVIDER_POSTGRES_TESTS=1`), otherwise rely on CI.

- [ ] **Step 9: Commit** `feat(trends): admin trends endpoint over Tbilisi-local buckets`.

### Task 2: Frontend page, chart, copy

**Files:**
- Modify: `frontend/lib/admin-types.ts` (types below), `frontend/lib/admin-i18n.ts` (`nav.trends`, `trends` block RU/KA/EN), `frontend/app/admin/layout.tsx` (nav item after dashboard), `frontend/app/admin/admin.module.css` (segmented control + chart classes)
- Create: `frontend/components/admin/TrendChart.tsx`, `frontend/app/admin/trends/page.tsx`

**Interfaces:**
- Consumes: API shape from Task 1.
- Produces:

```ts
export const TREND_PERIODS = ['30d', '90d', '12m'] as const;
export type TrendPeriod = (typeof TREND_PERIODS)[number];
export type TrendTotalKey = 'signups' | 'askers' | 'questions' | 'payments' | 'revenue_minor' | 'up' | 'down';
export type TrendTotals = Record<TrendTotalKey, number>;
export interface TrendBucket extends TrendTotals {
  start: string; partial: boolean; answers: number; answers_with_evidence: number; flagged: number;
  median_processing_ms: number | null;
}
export interface Trends {
  period: TrendPeriod; bucket: 'day' | 'week' | 'month'; timezone: string; quality_since: string | null;
  median_processing_ms: number | null;
  buckets: TrendBucket[]; totals: { current: TrendTotals; previous: TrendTotals };
}
```

`TrendChart` props:

```ts
type ChartSeries = { key: string; label: string; color: string; values: (number | null)[] };
interface TrendChartProps {
  title: string; labels: string[]; bars: ChartSeries[]; line?: ChartSeries;
  formatBar: (v: number) => string; formatLine?: (v: number) => string;
  partialLast: boolean; emptyText: string; dataLabel: string; periodLabel: string;
}
```

- [ ] **Step 1:** Load the `dataviz` skill; pick bar/line colors from the validated palette (dark surface) and check contrast against `--admin` panel background.
- [ ] **Step 2:** `TrendChart.tsx`: `<figure>` with `<figcaption>` title, legend, SVG `viewBox="0 0 640 220"` `preserveAspectRatio="none"` width 100%; stacked bars from `bars`, optional polyline on its own scale from `line` (null breaks the line); y max = nice ceiling (1/2/5 × 10ⁿ) of the max stacked total, 0 → 1; gridlines at 0/50/100%; last bar `opacity .45` when `partialLast`; `<title>` per bar `label: value`; x labels thinned to ≤ 8 (`step = ceil(n/8)`), always including the last; `role="img"` + `aria-label` summary (`title`, total, max); `<details><summary>{dataLabel}</summary><table>` with period/series columns. All-zero and all-null → `emptyText` overlay. Colors via CSS custom properties through `vars()`.
- [ ] **Step 3:** `trends/page.tsx` inside `<Suspense>`: `period = pick(params.get('period'), TREND_PERIODS) || '30d'`; segmented `role="group"` of three `aria-pressed` buttons updating `?period=` with `router.replace` (drop param for default); `useAdminFetch<Trends>(`/api/v1/admin/trends?period=${period}`)`; error → `AdminState kind="error" onRetry={reload}`; first load → `AdminState kind="loading"`. Tiles: revenue (`formatNumber(minor/100)` + ` ₾`), payments, signups, questions, askers, 👍 share (`up/(up+down)`), each with delta detail: previous 0 & current 0 → `c.common.dash`; previous 0 → `c.trends.newVsPrev`; else signed rounded % + `c.trends.vsPrev`. Labels: day → `formatDate` short `dd.mm`, week → `dd.mm`, month → month short name + 2-digit year (Intl, locale from `useAdminCopy`). Panels: revenue bars; questions bars + askers line; signups bars; ratings stacked up/down + flagged-share line (`flagged/answers_with_evidence`, null when 0) with note `c.trends.qualitySince(date)` when `quality_since` set and `c.trends.noQuality` when null, plus `c.trends.medianTime` = top-level `median_processing_ms` (seconds, one decimal) or dash.
- [ ] **Step 4:** Copy (RU shown; KA/EN equivalents in the same keys): nav `trends: 'Динамика'`; `trends: { title: 'Динамика', subtitle: 'Как меняются выручка, активность и качество ответов. Время — тбилисское, администраторы не учитываются.', periods: {'30d': '30 дней', '90d': '90 дней', '12m': '12 месяцев'}, period: 'Период', revenue: 'Выручка', payments: 'Оплаты', signups: 'Новые пользователи', questions: 'Вопросы', askers: 'Спрашивающие', upShare: 'Доля 👍', activity: 'Активность', quality: 'Качество ответов', up: '👍', down: '👎', flaggedShare: 'Ответы с признаками', vsPrev: 'к прошлому периоду', newVsPrev: 'в прошлом периоде не было', qualitySince: (d) => `данные о качестве собираются с ${d}`, noQuality: 'данных о качестве пока нет', medianTime: 'Медианное время ответа', seconds: (s) => `${s} с`, showData: 'Показать данные', date: 'Период', empty: 'За период данных нет', partial: 'текущий период ещё идёт' }`.
- [ ] **Step 5:** `npx tsc --noEmit && npm run lint`.
- [ ] **Step 6: Commit** `feat(trends): admin trends page with SVG charts`.

### Task 3: E2E, baselines, docs

**Files:**
- Create: `frontend/e2e/admin-trends.spec.ts`; baselines `admin-trends-ru-desktop.png`, `admin-trends-ka-mobile.png`
- Modify: `frontend/e2e/admin.spec.ts` only if its nav assertions enumerate menu items; `docs/PRODUCTION_OPERATIONS.md` (admin pages list: trends, read-only, no schema step); `docs/DEVELOPMENT_MEMORY.md` (stage 3 entry)

- [ ] **Step 1:** Spec with the same `setup()` pattern as `admin-quality.spec.ts` serving `/api/v1/auth/me` and `/api/v1/admin/trends` from a deterministic 30-bucket fixture (and a 12-bucket one for `12m`). Tests: (a) default load requests `period=30d`, shows tiles «Выручка» with `49 ₾`-style value and delta text; (b) clicking «12 месяцев» sets `?period=12m`, requests `period=12m`, survives reload; (c) `?period=bogus` requests `30d`; (d) «Показать данные» expands a table with 30 rows; (e) 500 → error state, «Повторить» refetches; (f) all-zero fixture → «За период данных нет», no `NaN`/`Infinity` in page text; (g) mobile 390 px has no horizontal scroll; (h) visual baselines ru desktop 1440 and ka mobile 390.
- [ ] **Step 2:** Run `npx playwright test e2e/admin-trends.spec.ts` (non-visual tests must pass on Windows; screenshots are produced in the Linux container per the stage-4 procedure, or by CI artifact if the container is unavailable).
- [ ] **Step 3:** Docs lines; commit `test(trends): e2e, baselines and docs`.
- [ ] **Step 4:** Push, open PR, watch CI + SonarCloud; fix issues.
