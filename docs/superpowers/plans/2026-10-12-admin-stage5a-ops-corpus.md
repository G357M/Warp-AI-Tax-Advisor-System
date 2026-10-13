# Admin Stage 5a (System health + Corpus) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Read-only admin pages `/admin/system` (latest status of host cron jobs) and `/admin/corpus` (document base contents and growth), plus removal of the dead `/admin/scraper` page, `GET /admin/ops` and the legacy `/api/v1/scraper/*` router.

**Architecture:** Host cron jobs (`run_scraper.sh`, `ops/backup-infohub-db.sh`, `ops/restore-drill-infohub-db.sh`) call a small Python writer that atomically writes `ops-status/<job>.json` in the repo dir on the host; that dir is bind-mounted read-only into the backend at `/app/ops-status`. The backend computes a state per job from those files; the corpus page is plain SQL over `documents`/`document_chunks`. Frontend pages follow stage 3 patterns (`useAdminFetch`, `StatTile`, `TrendChart`, `DataTable`, `Badge`).

**Tech Stack:** FastAPI + SQLAlchemy (PostgreSQL/pgvector), Python 3.11 stdlib on host, bash, Next.js 16 / React client components, Playwright e2e.

**Spec:** `docs/superpowers/specs/2026-10-12-admin-stage5-ops-corpus-design.md` (part 5a, sections 1–5). Part 5b is a separate plan.

## Global Constraints

- No DB schema change, no new step in `deploy_production.sh` other than creating the `ops-status` dir.
- Jobs are exactly `scraper`, `canary`, `backup`, `restore_drill`, always returned in that order.
- Freshness thresholds: scraper, canary, backup — 26 h; restore_drill — 35 days.
- Log tail: last 40 lines, each truncated to 300 chars, secrets redacted.
- Status file read limit: 64 KB.
- Status writer never changes the calling script's exit code.
- Weekly corpus chart: 12 Monday-start weeks in Tbilisi time (UTC+4, no DST); last week `partial: true`.
- All admin endpoints use `dependencies=[Depends(require_admin)]`.
- All admin copy exists in RU/KA/EN; KA strings checked with the `anthropic-skills:georgian-writing-style` skill and flagged for Gela's review in the PR.
- No `style={{…}}` attributes in `frontend/app/admin/**` (stage 1 rule); no new UI libraries.
- Shell commands in this repo are run with the `rtk` prefix (user rule), e.g. `rtk git commit`.
- Visual baselines are generated only in the pinned Playwright container (CI image `mcr.microsoft.com/playwright@sha256:dcc5531e…`), never on Windows.

## Deviations from the spec (decided while planning)

- The writer is `ops/write_job_status.py` (Python, stdlib) instead of a bash script with `python3 -c`: same contract, directly unit-testable.
- `ops/backup-infohub-db.sh` exits **0** (not 75) when its lock is busy. "Skipped" is therefore an explicit `skipped: true` field in the status file (env `INFOHUB_JOB_SKIPPED=1`), not an exit-code convention. The state table uses `skipped`, not exit code 75.
- Relative "N h ago" text is kept; it is computed on the client from `finished_at`.
- Dashboard attention links that pointed to `/admin/scraper` now point to `/admin/system` (ingest stale) and `/admin/corpus` (decisions queue).

The spec file is updated in Task 8 to match.

## Review Focus

1. **Status file written mid-read** — the backend must never see a half-written JSON: writer uses temp file + `os.replace` in the same dir (Task 1 test `test_write_is_atomic_and_leaves_no_temp`).
2. **Secrets in logs** — a line like `TELEGRAM_BOT_TOKEN=123:abc` or `Authorization: Bearer x` must not reach the page (Task 1 `test_redacts_secrets`).
3. **Corrupt / foreign / huge status file** — page must show "no data" for that job, not 500 (Task 3 `test_bad_files_are_unknown`).
4. **Failed old run** — a failed run stays `failed` even when stale; operator must see the error, not "overdue" (Task 3 `test_failed_wins_over_stale`).
5. **Week boundary in Tbilisi** — a document created Sunday 21:00 UTC (= Monday 01:00 Tbilisi) belongs to the new week (Task 4 `test_weekly_uses_tbilisi_weeks`).

---

### Task 1: Host status writer

**Files:**
- Create: `ops/write_job_status.py`
- Create: `backend/tests/test_ops_job_status.py`
- Modify: `.github/workflows/ci.yml` (backend pytest list, after `tests/test_admin_trends.py`)
- Modify: `.gitignore` (add `ops-status/`)

**Interfaces:**
- Produces: CLI `python3 ops/write_job_status.py JOB STARTED_AT EXIT_CODE SUMMARY LOG_FILE`; env `INFOHUB_OPS_STATUS_DIR` (default `<repo>/ops-status`), `INFOHUB_JOB_TRIGGER` (`cron`|`manual`, default `cron`), `INFOHUB_JOB_SKIPPED` (`1` = skipped). Exit 2 on bad usage/unknown job, else 0.
- Produces: file `<dir>/<job>.json` = `{"schema_version":1,"job","started_at","finished_at","exit_code","summary","trigger","skipped","log_tail"}`; timestamps `YYYY-MM-DDTHH:MM:SSZ`.
- Produces (importable for tests): `redact(line: str) -> str`, `tail(path: str, n: int = 40) -> list[str]`, `main(argv: list[str]) -> int`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_ops_job_status.py`:

```python
"""Host ops status writer: atomic JSON for the admin System page."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("write_job_status", ROOT / "ops" / "write_job_status.py")
writer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(writer)


@pytest.fixture
def status_dir(tmp_path, monkeypatch):
    out = tmp_path / "ops-status"
    monkeypatch.setenv("INFOHUB_OPS_STATUS_DIR", str(out))
    monkeypatch.delenv("INFOHUB_JOB_TRIGGER", raising=False)
    monkeypatch.delenv("INFOHUB_JOB_SKIPPED", raising=False)
    return out


def _log(tmp_path, lines):
    path = tmp_path / "job.log"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def test_writes_status_json(status_dir, tmp_path):
    log = _log(tmp_path, [f"line {i}" for i in range(100)])
    assert writer.main(["w", "scraper", "2026-10-12T03:00:02Z", "0", "+3 new docs (full)", log]) == 0
    data = json.loads((status_dir / "scraper.json").read_text(encoding="utf-8"))
    assert data["schema_version"] == 1 and data["job"] == "scraper"
    assert data["started_at"] == "2026-10-12T03:00:02Z"
    assert data["finished_at"].endswith("Z") and data["exit_code"] == 0
    assert data["summary"] == "+3 new docs (full)"
    assert data["trigger"] == "cron" and data["skipped"] is False
    assert data["log_tail"] == [f"line {i}" for i in range(60, 100)]


def test_trigger_and_skipped_come_from_env(status_dir, tmp_path, monkeypatch):
    monkeypatch.setenv("INFOHUB_JOB_TRIGGER", "manual")
    monkeypatch.setenv("INFOHUB_JOB_SKIPPED", "1")
    writer.main(["w", "backup", "2026-10-12T01:30:00Z", "0", "", _log(tmp_path, ["skipped"])])
    data = json.loads((status_dir / "backup.json").read_text(encoding="utf-8"))
    assert data["trigger"] == "manual" and data["skipped"] is True


def test_unknown_trigger_falls_back_to_cron(status_dir, tmp_path, monkeypatch):
    monkeypatch.setenv("INFOHUB_JOB_TRIGGER", "evil")
    writer.main(["w", "canary", "", "1", "CANARY: 8/10", _log(tmp_path, [])])
    data = json.loads((status_dir / "canary.json").read_text(encoding="utf-8"))
    assert data["trigger"] == "cron" and data["started_at"] is None and data["exit_code"] == 1


def test_unknown_job_and_bad_usage_exit_2(status_dir, tmp_path):
    assert writer.main(["w", "rm -rf", "", "0", "", "/dev/null"]) == 2
    assert writer.main(["w", "scraper"]) == 2
    assert not status_dir.exists()


def test_non_numeric_exit_code_is_minus_one(status_dir, tmp_path):
    writer.main(["w", "scraper", "", "?", "", _log(tmp_path, [])])
    assert json.loads((status_dir / "scraper.json").read_text(encoding="utf-8"))["exit_code"] == -1


def test_redacts_secrets():
    assert writer.redact("TELEGRAM_BOT_TOKEN=123:abcDEF") == "TELEGRAM_BOT_TOKEN=[redacted]"
    assert writer.redact("Authorization: Bearer abc.def") == "Authorization=[redacted]"
    assert writer.redact("password = hunter2 rest") == "password=[redacted] rest"
    assert writer.redact("url https://api.telegram.org/bot123456:AAH-x_y/sendMessage") == \
        "url https://api.telegram.org/bot[redacted]/sendMessage"
    assert writer.redact("duplicate key violates unique constraint") == "duplicate key violates unique constraint"


def test_long_lines_truncated_and_missing_log_is_empty(tmp_path):
    log = _log(tmp_path, ["x" * 1000])
    assert writer.tail(log) == ["x" * 300]
    assert writer.tail(str(tmp_path / "missing.log")) == []


def test_write_is_atomic_and_leaves_no_temp(status_dir, tmp_path):
    log = _log(tmp_path, ["a"])
    for _ in range(3):
        writer.main(["w", "restore_drill", "", "0", "ok", log])
    assert sorted(p.name for p in status_dir.iterdir()) == ["restore_drill.json"]
    assert oct((status_dir / "restore_drill.json").stat().st_mode & 0o777) in ("0o644", "0o666")


def test_write_failure_never_fails_caller(tmp_path, monkeypatch):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("INFOHUB_OPS_STATUS_DIR", str(blocker / "sub"))
    assert writer.main(["w", "scraper", "", "0", "", "/dev/null"]) == 0
```

(The `0o666` alternative in the mode assertion only covers Windows dev machines, where chmod is a no-op; CI on Linux checks `0o644`.)

- [ ] **Step 2: Run tests to verify they fail**

Run (from `backend/`): `rtk python -m pytest tests/test_ops_job_status.py -q`
Expected: FAIL / collection error — `ops/write_job_status.py` does not exist.

- [ ] **Step 3: Write the implementation**

`ops/write_job_status.py`:

```python
#!/usr/bin/env python3
"""Write the latest-run status of a host ops job for the admin "System" page.

Usage: write_job_status.py JOB STARTED_AT EXIT_CODE SUMMARY LOG_FILE

JOB is one of scraper, canary, backup, restore_drill. The file
<status dir>/<JOB>.json is replaced atomically, so the backend (which mounts
the dir read-only) never reads a half-written status.

Env: INFOHUB_OPS_STATUS_DIR (default: <repo>/ops-status),
     INFOHUB_JOB_TRIGGER (cron | manual; default cron),
     INFOHUB_JOB_SKIPPED=1 when the run was skipped on a busy lock.

Never fails the calling job: write errors are reported on stderr and the
exit code stays 0. Only bad usage or an unknown JOB exits 2.
"""
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

JOBS = ("scraper", "canary", "backup", "restore_drill")
TAIL_LINES = 40
LINE_MAX = 300
READ_BYTES = 65536
DEFAULT_DIR = Path(__file__).resolve().parents[1] / "ops-status"

_ASSIGNED = re.compile(
    r"(?i)\b([\w-]*(?:token|key|secret|password|authorization))\s*[:=]\s*(?:bearer\s+)?\S+")
_BOT = re.compile(r"bot\d+:[\w-]+")


def redact(line: str) -> str:
    """Logs are aggregate-only already; this is a second guard for assigned secrets."""
    line = _BOT.sub("bot[redacted]", line)
    return _ASSIGNED.sub(lambda m: f"{m.group(1)}=[redacted]", line)


def tail(path: str, n: int = TAIL_LINES) -> list:
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - READ_BYTES))
            text = f.read().decode("utf-8", "replace")
    except OSError:
        return []
    return [redact(line)[:LINE_MAX] for line in text.splitlines()[-n:]]


def _write(directory: Path, payload: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=f".{payload['job']}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.chmod(tmp, 0o644)
        os.replace(tmp, directory / f"{payload['job']}.json")
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def main(argv: list) -> int:
    if len(argv) != 6 or argv[1] not in JOBS:
        print(f"usage: {Path(argv[0]).name} {{{'|'.join(JOBS)}}} STARTED_AT EXIT_CODE SUMMARY LOG_FILE",
              file=sys.stderr)
        return 2
    job, started_at, exit_code, summary, log_file = argv[1:]
    try:
        code = int(exit_code)
    except ValueError:
        code = -1
    trigger = os.environ.get("INFOHUB_JOB_TRIGGER", "cron")
    payload = {
        "schema_version": 1,
        "job": job,
        "started_at": started_at or None,
        "finished_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "exit_code": code,
        "summary": redact(summary)[:LINE_MAX],
        "trigger": trigger if trigger in ("cron", "manual") else "cron",
        "skipped": os.environ.get("INFOHUB_JOB_SKIPPED") == "1",
        "log_tail": tail(log_file),
    }
    try:
        _write(Path(os.environ.get("INFOHUB_OPS_STATUS_DIR") or DEFAULT_DIR), payload)
    except Exception as exc:  # the job's own outcome matters more than its status file
        print(f"[ops-status] could not write {job} status: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `backend/`): `rtk python -m pytest tests/test_ops_job_status.py -q`
Expected: 9 passed. If `test_redacts_secrets` fails on one case, fix the regex, not the test.

- [ ] **Step 5: Register in CI and ignore the runtime dir**

In `.github/workflows/ci.yml`, in the backend pytest file list, add a line `tests/test_ops_job_status.py` directly after `tests/test_admin_trends.py`. In `.gitignore` add a line `ops-status/` next to `.state/`.

- [ ] **Step 6: Commit**

```bash
rtk git add ops/write_job_status.py backend/tests/test_ops_job_status.py .github/workflows/ci.yml .gitignore
rtk git commit -m "feat(ops): atomic job status writer for the admin system page"
```

---

### Task 2: Wire the writer into host jobs, mount, deploy

**Files:**
- Modify: `run_scraper.sh`
- Modify: `ops/backup-infohub-db.sh`
- Modify: `ops/restore-drill-infohub-db.sh`
- Modify: `docker-compose.yml` (backend `volumes`)
- Modify: `scripts/deploy_production.sh` (install block near `install -d -m 0755 certbot/www`)
- Test: `backend/tests/test_ops_job_status.py` (append contract tests)

**Interfaces:**
- Consumes: Task 1 CLI.
- Produces: on the host `ops-status/{scraper,canary,backup,restore_drill}.json`; in the backend container the same files under `/app/ops-status` (read-only).

- [ ] **Step 1: Write the failing contract tests** (append to `backend/tests/test_ops_job_status.py`)

```python
def _text(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def test_scraper_writes_scraper_and_canary_status():
    text = _text("run_scraper.sh")
    assert 'STATUS_WRITER="$SCRIPT_DIR/ops/write_job_status.py"' in text
    assert "trap write_scraper_status EXIT" in text
    assert 'python3 "$STATUS_WRITER" canary "$CANARY_STARTED_AT" "$CANARY_EXIT"' in text
    # The trap is installed only after the lock: a skipped overlapping run must not overwrite the status.
    assert text.index("flock -n 9") < text.index("trap write_scraper_status EXIT")


def test_backup_and_drill_write_status_from_exit_trap():
    for rel, job in (("ops/backup-infohub-db.sh", "backup"), ("ops/restore-drill-infohub-db.sh", "restore_drill")):
        text = _text(rel)
        finish = text[text.index("finish() {"):text.index("trap finish EXIT")]
        assert f'"$STATUS_WRITER" {job} "$started_at" "$rc"' in finish, rel
        assert 'INFOHUB_JOB_SKIPPED="$skipped"' in finish, rel
        assert "|| true" in finish, rel


def test_status_dir_is_mounted_read_only_and_created_on_deploy():
    assert "- ./ops-status:/app/ops-status:ro" in _text("docker-compose.yml")
    deploy = _text("scripts/deploy_production.sh")
    assert "install -d -m 0755 ops-status" in deploy
    assert deploy.index("install -d -m 0755 ops-status") < deploy.index("docker compose config --quiet")
```

- [ ] **Step 2: Run to verify they fail**

Run (from `backend/`): `rtk python -m pytest tests/test_ops_job_status.py -q`
Expected: the 3 new tests FAIL (strings not found).

- [ ] **Step 3: `run_scraper.sh`**

Directly after the line `chmod 0600 "$LOG_FILE"` insert:

```bash
# Latest-run status for the admin System page (ops-status/scraper.json). The
# trap is set after the lock, so an overlapping run that was skipped above
# never overwrites the status of the run that holds the lock.
STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
STATUS_WRITER="$SCRIPT_DIR/ops/write_job_status.py"
write_scraper_status() {
    local rc=$?
    local mode="full"
    [ "$INGEST_ONLY" -eq 1 ] && mode="ingest-only"
    python3 "$STATUS_WRITER" scraper "$STARTED_AT" "${EXIT_CODE:-$rc}" \
        "+${NEW_DOCS:-?} new docs (${mode})" "$LOG_FILE" || true
}
trap write_scraper_status EXIT
```

Replace the canary block

```bash
echo "Running RAG canary..." | tee -a "$LOG_FILE"
CANARY_EXIT=0
```

with

```bash
echo "Running RAG canary..." | tee -a "$LOG_FILE"
CANARY_STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
CANARY_EXIT=0
```

and directly after the existing `bash "$(dirname "$0")/canary_alert.sh" ...` line add:

```bash
python3 "$STATUS_WRITER" canary "$CANARY_STARTED_AT" "$CANARY_EXIT" \
    "$(echo "$CANARY_OUT" | grep '^CANARY:' | tail -1)" "$LOG_FILE" || true
```

- [ ] **Step 4: `ops/backup-infohub-db.sh`**

After the `ALERT=...` line add:

```bash
STATUS_WRITER="${INFOHUB_OPS_STATUS_WRITER:-$(dirname "${BASH_SOURCE[0]}")/write_job_status.py}"
STATUS_LOG="${INFOHUB_DB_BACKUP_LOG:-/root/infohub/logs/db-backup.log}"
started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
skipped=0
summary=""
```

Replace the whole `finish()` function with:

```bash
finish() {
    local rc=$?
    rm -f ${partial:+"$partial"} ${toc:+"$toc"}
    if (( rc != 0 )); then
        bash "$ALERT" "nightly DB backup" "exit $rc: ${reason:-unknown error}
Log: /root/infohub/logs/db-backup.log" || true
    fi
    INFOHUB_JOB_SKIPPED="$skipped" python3 "$STATUS_WRITER" backup "$started_at" "$rc" \
        "${summary:-${reason:-}}" "$STATUS_LOG" || true
}
```

In the lock branch, set `skipped=1` and a summary before `exit 0`:

```bash
if ! flock -n 9; then
    log "another backup is running; skipped"
    skipped=1
    summary="skipped: another backup is running"
    exit 0
fi
```

After the existing `log "ok $(basename "$target") ..."` line add:

```bash
summary="ok $(basename "$target") $(( $(stat -c %s "$target") / 1048576 )) MiB"
```

- [ ] **Step 5: `ops/restore-drill-infohub-db.sh`**

After its `ALERT=...` line add:

```bash
STATUS_WRITER="${INFOHUB_OPS_STATUS_WRITER:-$(dirname "${BASH_SOURCE[0]}")/write_job_status.py}"
STATUS_LOG="${INFOHUB_RESTORE_DRILL_LOG:-/root/infohub/logs/restore-drill.log}"
started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
skipped=0
summary=""
```

Replace its `finish()` with:

```bash
finish() {
    local rc=$?
    cleanup
    if (( rc != 0 )); then
        bash "$ALERT" "monthly restore drill" "exit $rc: ${reason:-unknown error}
Log: /root/infohub/logs/restore-drill.log" || true
    fi
    INFOHUB_JOB_SKIPPED="$skipped" python3 "$STATUS_WRITER" restore_drill "$started_at" "$rc" \
        "${summary:-${reason:-}}" "$STATUS_LOG" || true
}
```

In the lock branch (the one ending in `exit 75`, around line 89–92) add `skipped=1` and `summary="skipped: lock held by the backup"` before `exit 75`. After the existing `log "ok $dump_name restored and verified in ${duration}s"` line add:

```bash
summary="ok $dump_name in ${duration}s"
```

- [ ] **Step 6: Mount and deploy**

`docker-compose.yml`, backend service, `volumes:` becomes:

```yaml
    volumes:
      - ai_models:/root/.cache/huggingface
      # Latest-run status of host cron jobs, written by ops/write_job_status.py.
      - ./ops-status:/app/ops-status:ro
```

`scripts/deploy_production.sh`: directly after `install -d -m 0755 certbot/www` add:

```bash
install -d -m 0755 ops-status
```

- [ ] **Step 7: Run tests and shell syntax checks**

Run (from `backend/`): `rtk python -m pytest tests/test_ops_job_status.py -q` → 12 passed.
Run (repo root, Git Bash): `bash -n run_scraper.sh ops/backup-infohub-db.sh ops/restore-drill-infohub-db.sh scripts/deploy_production.sh` → no output.
Run: `rtk docker compose config --quiet` → exit 0 (if Docker is unavailable locally, rely on CI's `containers` job).

- [ ] **Step 8: Commit**

```bash
rtk git add run_scraper.sh ops/backup-infohub-db.sh ops/restore-drill-infohub-db.sh docker-compose.yml scripts/deploy_production.sh backend/tests/test_ops_job_status.py
rtk git commit -m "feat(ops): nightly jobs write their latest status; mount it read-only into the backend"
```

---

### Task 3: Backend `GET /admin/system`

**Files:**
- Create: `backend/core/admin_system.py`
- Create: `backend/api/routes/admin_system.py`
- Modify: `backend/api/main.py` (import + `include_router`)
- Create: `backend/tests/test_admin_system.py`
- Modify: `.github/workflows/ci.yml` (add `tests/test_admin_system.py` after `tests/test_ops_job_status.py`)

**Interfaces:**
- Consumes: status files from Task 1/2.
- Produces: `system_status(directory: Path, now: datetime) -> dict` (naive-UTC `now`), `JOBS`, `FRESH_FOR`.
- Produces HTTP: `GET /api/v1/admin/system` →
  `{"generated_at": str, "jobs": [{"job", "state", "started_at", "finished_at", "exit_code", "summary", "trigger", "skipped", "log_tail"}]}`; `state` ∈ `ok|stale|failed|skipped|unknown`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_admin_system.py`:

```python
"""Admin System page: job state from host status files (no database)."""
import json
from datetime import datetime

from api.routes.admin_system import router
from core.admin_system import system_status
from core.security import require_admin

NOW = datetime(2026, 10, 12, 10, 0)  # naive UTC


def _write(directory, job, **fields):
    data = {"schema_version": 1, "job": job, "started_at": "2026-10-12T03:00:00Z",
            "finished_at": "2026-10-12T03:40:00Z", "exit_code": 0, "summary": "ok",
            "trigger": "cron", "skipped": False, "log_tail": ["a", "b"]}
    data.update(fields)
    (directory / f"{job}.json").write_text(json.dumps(data), encoding="utf-8")


def _states(directory):
    return {j["job"]: j["state"] for j in system_status(directory, NOW)["jobs"]}


def test_missing_dir_gives_four_unknown_in_order(tmp_path):
    result = system_status(tmp_path / "nope", NOW)
    assert [j["job"] for j in result["jobs"]] == ["scraper", "canary", "backup", "restore_drill"]
    assert all(j["state"] == "unknown" and j["log_tail"] == [] and j["exit_code"] is None for j in result["jobs"])


def test_ok_and_fields_pass_through(tmp_path):
    _write(tmp_path, "scraper", summary="+3 new docs (full)", trigger="manual")
    job = system_status(tmp_path, NOW)["jobs"][0]
    assert job["state"] == "ok" and job["summary"] == "+3 new docs (full)"
    assert job["trigger"] == "manual" and job["log_tail"] == ["a", "b"]
    assert job["finished_at"] == "2026-10-12T03:40:00Z"


def test_freshness_thresholds_on_the_boundary(tmp_path):
    _write(tmp_path, "scraper", finished_at="2026-10-11T08:00:00Z")   # exactly 26 h
    _write(tmp_path, "canary", finished_at="2026-10-11T07:59:59Z")    # 26 h + 1 s
    _write(tmp_path, "restore_drill", finished_at="2026-09-07T10:00:00Z")  # exactly 35 days
    states = _states(tmp_path)
    assert states["scraper"] == "ok" and states["canary"] == "stale" and states["restore_drill"] == "ok"
    _write(tmp_path, "restore_drill", finished_at="2026-09-07T09:59:59Z")
    assert _states(tmp_path)["restore_drill"] == "stale"


def test_failed_wins_over_stale(tmp_path):
    _write(tmp_path, "backup", exit_code=1, finished_at="2026-01-01T00:00:00Z")
    assert _states(tmp_path)["backup"] == "failed"


def test_skipped_then_stale(tmp_path):
    _write(tmp_path, "backup", skipped=True)
    assert _states(tmp_path)["backup"] == "skipped"
    _write(tmp_path, "restore_drill", skipped=True, exit_code=75)
    assert _states(tmp_path)["restore_drill"] == "skipped"
    _write(tmp_path, "backup", skipped=True, finished_at="2026-10-01T00:00:00Z")
    assert _states(tmp_path)["backup"] == "stale"


def test_bad_files_are_unknown(tmp_path):
    (tmp_path / "scraper.json").write_text("{not json", encoding="utf-8")
    _write(tmp_path, "canary", job="backup")                    # foreign job
    _write(tmp_path, "backup", schema_version=2)                 # unknown schema
    _write(tmp_path, "restore_drill", log_tail=["x" * 70000])    # over 64 KB
    assert set(_states(tmp_path).values()) == {"unknown"}


def test_bad_field_types_are_unknown_or_dropped(tmp_path):
    _write(tmp_path, "scraper", exit_code="0")
    _write(tmp_path, "canary", finished_at="yesterday")
    _write(tmp_path, "backup", trigger="root", log_tail="not a list", summary=5)
    states = _states(tmp_path)
    assert states["scraper"] == "unknown" and states["canary"] == "unknown"
    backup = system_status(tmp_path, NOW)["jobs"][2]
    assert backup["state"] == "ok" and backup["trigger"] is None
    assert backup["log_tail"] == [] and backup["summary"] is None


def test_router_requires_admin():
    assert any(d.dependency is require_admin for d in router.dependencies)
```

- [ ] **Step 2: Run to verify they fail**

Run (from `backend/`): `rtk python -m pytest tests/test_admin_system.py -q`
Expected: collection error, `core.admin_system` missing.

- [ ] **Step 3: Implement `backend/core/admin_system.py`**

```python
"""Admin System page: latest status of host cron jobs (read-only).

The host writes ops-status/<job>.json (ops/write_job_status.py); the backend
mounts that dir read-only. Anything unreadable or unexpected becomes
"unknown" rather than an error, so one bad file never hides the others.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

JOBS = ("scraper", "canary", "backup", "restore_drill")
FRESH_FOR = {
    "scraper": timedelta(hours=26),
    "canary": timedelta(hours=26),
    "backup": timedelta(hours=26),
    "restore_drill": timedelta(days=35),
}
MAX_BYTES = 64 * 1024


def _naive_utc(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed


def _load(path: Path, job: str) -> dict | None:
    try:
        if path.stat().st_size > MAX_BYTES:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("schema_version") != 1 or data.get("job") != job:
        return None
    if type(data.get("exit_code")) is not int or _naive_utc(data.get("finished_at")) is None:
        return None
    return data


def _state(data: dict | None, job: str, now: datetime) -> str:
    if data is None:
        return "unknown"
    fresh = now - _naive_utc(data["finished_at"]) <= FRESH_FOR[job]
    if data["exit_code"] != 0 and data.get("skipped") is not True:
        return "failed"
    if data.get("skipped") is True:
        return "skipped" if fresh else "stale"
    return "ok" if fresh else "stale"


def _text(data: dict | None, key: str) -> str | None:
    value = data.get(key) if data else None
    return value if isinstance(value, str) else None


def _entry(job: str, data: dict | None, now: datetime) -> dict:
    tail = data.get("log_tail") if data else None
    trigger = _text(data, "trigger")
    return {
        "job": job,
        "state": _state(data, job, now),
        "started_at": _text(data, "started_at"),
        "finished_at": _text(data, "finished_at"),
        "exit_code": data["exit_code"] if data else None,
        "summary": _text(data, "summary"),
        "trigger": trigger if trigger in ("cron", "manual") else None,
        "skipped": bool(data and data.get("skipped") is True),
        "log_tail": [line for line in tail if isinstance(line, str)] if isinstance(tail, list) else [],
    }


def system_status(directory: Path, now: datetime) -> dict:
    return {
        "generated_at": now.isoformat(),
        "jobs": [_entry(job, _load(directory / f"{job}.json", job), now) for job in JOBS],
    }
```

(The restore drill exits 75 on a busy lock with `skipped: true`; that is `skipped`, not `failed` — hence the `skipped` check inside the failed branch.)

- [ ] **Step 4: Implement the route**

`backend/api/routes/admin_system.py`:

```python
"""Admin System page: latest status of host cron jobs. Requires the admin role."""
import os
from pathlib import Path

from fastapi import APIRouter, Depends

from core.admin_system import system_status
from core.security import require_admin
from core.time_utils import utc_now

router = APIRouter(prefix="/admin/system", tags=["Admin"], dependencies=[Depends(require_admin)])


@router.get("")
def get_system():
    return system_status(Path(os.environ.get("ADMIN_OPS_STATUS_DIR", "/app/ops-status")), utc_now())
```

`backend/api/main.py`: add `admin_system` to the `from api.routes import ...` line (alphabetical, after `admin_quality`), and after the `admin_trends` include add:

```python
app.include_router(admin_system.router, prefix=settings.API_PREFIX)  # Admin: system health
```

- [ ] **Step 5: Run tests**

Run (from `backend/`): `rtk python -m pytest tests/test_admin_system.py -q` → 8 passed.

- [ ] **Step 6: Register in CI and commit**

Add `tests/test_admin_system.py` after `tests/test_ops_job_status.py` in the CI backend list.

```bash
rtk git add backend/core/admin_system.py backend/api/routes/admin_system.py backend/api/main.py backend/tests/test_admin_system.py .github/workflows/ci.yml
rtk git commit -m "feat(admin): system endpoint with per-job state from host status files"
```

---

### Task 4: Backend `GET /admin/corpus`; remove `/admin/ops` and the legacy scraper router

**Files:**
- Modify: `backend/core/admin_trends.py` (extract `window_of`, rename `_utc` → `tbilisi_midnight_utc`)
- Create: `backend/core/admin_corpus.py`
- Create: `backend/api/routes/admin_corpus.py`
- Modify: `backend/api/main.py` (include corpus router; remove `scraper` import + include)
- Modify: `backend/api/routes/admin.py` (delete `LOG_DIR`, `_tail`, `ops_status`, now-unused imports `os`, `tempfile`, `Path`)
- Delete: `backend/api/routes/scraper.py`
- Modify: `backend/tests/load_test.py` (remove the `/api/v1/scraper/tasks` task)
- Create: `backend/tests/test_admin_corpus_postgres.py`
- Modify: `backend/tests/test_admin_trends.py` (one test for `window_of`)
- Modify: `.github/workflows/ci.yml` (postgres list: add `tests/test_admin_corpus_postgres.py` after `tests/test_admin_trends_postgres.py`)

**Interfaces:**
- Produces: `window_of(bucket: str, count: int, now: datetime) -> Window`; `tbilisi_midnight_utc(d: date) -> datetime` in `core.admin_trends` (`window(period, now)` unchanged).
- Produces: `corpus(db: Session, now: datetime) -> dict`.
- Produces HTTP: `GET /api/v1/admin/corpus` →
  `{"totals": {"documents", "chunks", "added_7d", "added_30d", "last_ingest"}, "by_type": [{"document_type", "documents", "added_30d", "without_date", "without_chunks"}], "weekly": [{"week_start", "added", "partial"}], "pending": {"decision_facts", "law_amendments"}}`.

- [ ] **Step 1: Refactor `core/admin_trends.py` (keep trends tests green)**

Rename `_utc` to `tbilisi_midnight_utc` (definition and its 3 call sites inside `trends()`), and replace `window` with:

```python
def window_of(bucket: str, count: int, now: datetime) -> Window:
    last = _floor((now + TBILISI_OFFSET).date(), bucket)
    first = _step(last, bucket, -(count - 1))
    return Window(bucket, [_step(first, bucket, i) for i in range(count)],
                  _step(last, bucket, 1), _step(first, bucket, -count))


def window(period: str, now: datetime) -> Window:
    return window_of(*PERIODS[period], now)
```

Append to `backend/tests/test_admin_trends.py`:

```python
def test_window_of_twelve_weeks():
    from core.admin_trends import window_of
    w = window_of("week", 12, NOW)
    assert len(w.starts) == 12 and w.starts[-1] == date(2026, 10, 12) and w.starts[0] == date(2026, 7, 27)
```

Run (from `backend/`): `rtk python -m pytest tests/test_admin_trends.py -q` → all pass.

- [ ] **Step 2: Write the failing corpus test**

`backend/tests/test_admin_corpus_postgres.py`:

```python
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
```

Run with a local test DB if available (`BILLING_PROVIDER_POSTGRES_TESTS=1`); otherwise expect it to be skipped locally and executed in CI's `temporal-postgres` job. Without the DB, at least verify collection fails: `rtk python -m pytest tests/test_admin_corpus_postgres.py -q` → ImportError on `core.admin_corpus`.

- [ ] **Step 3: Implement `backend/core/admin_corpus.py`**

```python
"""Admin Corpus page: what the document base holds and how it grows (read-only)."""
from datetime import datetime, timedelta

from sqlalchemy import exists, func, select, text
from sqlalchemy.orm import Session

from core.admin_trends import TBILISI_OFFSET, tbilisi_midnight_utc, window_of
from models import Document, DocumentChunk

WEEKS = 12

# Same queue definitions the nightly extractors work through.
_PENDING = text("""
    SELECT
      (SELECT count(*) FROM documents d LEFT JOIN decision_facts f ON f.document_id = d.id
         WHERE d.document_type='court_decision' AND f.id IS NULL
           AND (d.metadata->>'kind') IS DISTINCT FROM 'digest') AS decision_facts,
      (SELECT count(*) FROM documents d LEFT JOIN law_amendments a ON a.amendment_doc_id = d.id
         WHERE d.document_type='law' AND d.title ILIKE '%ცვლილებ%' AND a.id IS NULL) AS law_amendments
""")


def _by_type(db: Session, since_30d: datetime) -> list:
    has_chunks = exists().where(DocumentChunk.document_id == Document.id)
    total = func.count(Document.id)
    rows = db.execute(
        select(Document.document_type, total.label("documents"),
               total.filter(Document.created_at >= since_30d).label("added_30d"),
               total.filter(Document.date_published.is_(None)).label("without_date"),
               total.filter(~has_chunks).label("without_chunks"))
        .group_by(Document.document_type)
        .order_by(total.desc(), Document.document_type)
    ).mappings().all()
    return [dict(r) for r in rows]


def _weekly(db: Session, now: datetime) -> list:
    w = window_of("week", WEEKS, now)
    key = func.date_trunc("week", Document.created_at + TBILISI_OFFSET).label("week")
    rows = db.execute(
        select(key, func.count(Document.id).label("added"))
        .where(Document.created_at >= tbilisi_midnight_utc(w.starts[0]),
               Document.created_at < tbilisi_midnight_utc(w.end))
        .group_by(key)
    ).all()
    counts = {r.week.date(): r.added for r in rows}
    return [{"week_start": s.isoformat(), "added": counts.get(s, 0), "partial": s == w.starts[-1]}
            for s in w.starts]


def corpus(db: Session, now: datetime) -> dict:
    by_type = _by_type(db, now - timedelta(days=30))
    added_7d = db.execute(select(func.count(Document.id)).where(Document.created_at >= now - timedelta(days=7))).scalar()
    last_ingest = db.execute(select(func.max(Document.created_at))).scalar()
    pending = db.execute(_PENDING).one()
    return {
        "totals": {
            "documents": sum(r["documents"] for r in by_type),
            "chunks": db.execute(select(func.count(DocumentChunk.id))).scalar(),
            "added_7d": added_7d,
            "added_30d": sum(r["added_30d"] for r in by_type),
            "last_ingest": last_ingest.isoformat() if last_ingest else None,
        },
        "by_type": by_type,
        "weekly": _weekly(db, now),
        "pending": {"decision_facts": pending.decision_facts, "law_amendments": pending.law_amendments},
    }
```

`backend/api/routes/admin_corpus.py`:

```python
"""Admin Corpus page: document base contents and growth. Requires the admin role."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.admin_corpus import corpus
from core.database import get_db
from core.security import require_admin
from core.time_utils import utc_now

router = APIRouter(prefix="/admin/corpus", tags=["Admin"], dependencies=[Depends(require_admin)])


@router.get("")
def get_corpus(db: Session = Depends(get_db)):
    return corpus(db, utc_now())
```

- [ ] **Step 4: Remove `/admin/ops` and the legacy scraper router**

First confirm there are no other callers:

Run: Grep tool, pattern `admin/ops|/scraper/(start|status|tasks)|routes\.scraper|import.*\bscraper\b` over `backend`, `frontend/app`, `frontend/lib`, `frontend/components`, `scripts`, `nginx*`, `*.conf`. Expected hits only: `backend/api/routes/admin.py`, `backend/api/routes/scraper.py`, `backend/api/main.py`, `backend/tests/load_test.py`, `frontend/app/admin/scraper/page.tsx`, `frontend/e2e/admin.spec.ts` (the frontend ones are handled in Tasks 5/8). If anything else turns up, stop and report it.

Then:
- In `backend/api/routes/admin.py` delete the comment + `LOG_DIR = ...` lines, the whole `_tail` function and the whole `ops_status` endpoint; remove the now-unused imports `os`, `tempfile`, `from pathlib import Path` (keep anything still referenced — check with `rtk python -m pyflakes api/routes/admin.py` or by grepping each name). Update the module docstring's first line to `Admin API: real system stats, document/user management.`
- Delete `backend/api/routes/scraper.py` (`rtk git rm backend/api/routes/scraper.py`).
- In `backend/api/main.py` remove `scraper` from the import list and delete the line `app.include_router(scraper.router, prefix=settings.API_PREFIX)`; add `admin_corpus` to the import list and `app.include_router(admin_corpus.router, prefix=settings.API_PREFIX)  # Admin: corpus` next to the system include.
- In `backend/tests/load_test.py` delete the task method that calls `self.client.get("/api/v1/scraper/tasks")` (the whole `@task`-decorated method containing line ~191).

- [ ] **Step 5: Run tests**

Run (from `backend/`): `rtk python -m pytest tests/test_admin_trends.py tests/test_admin_system.py tests/test_ops_job_status.py -q` → all pass.
Run: `rtk python -c "import api.main"` (from `backend/`, with the usual local env) → no ImportError.
If a local PostgreSQL test DB is configured: `BILLING_PROVIDER_POSTGRES_TESTS=1 rtk python -m pytest tests/test_admin_corpus_postgres.py tests/test_admin_trends_postgres.py tests/test_admin_postgres.py -q` → all pass. Otherwise CI covers it.

- [ ] **Step 6: Register in CI and commit**

Add `tests/test_admin_corpus_postgres.py` after `tests/test_admin_trends_postgres.py` in the CI postgres list.

```bash
rtk git add -A backend/core/admin_trends.py backend/core/admin_corpus.py backend/api/routes/admin_corpus.py backend/api/routes/admin.py backend/api/routes/scraper.py backend/api/main.py backend/tests/load_test.py backend/tests/test_admin_corpus_postgres.py backend/tests/test_admin_trends.py .github/workflows/ci.yml
rtk git commit -m "feat(admin): corpus endpoint; drop dead /admin/ops and legacy /scraper router"
```

---

### Task 5: Frontend shared pieces — types, copy, navigation, Documents filter from URL

**Files:**
- Modify: `frontend/lib/admin-types.ts`
- Modify: `frontend/lib/admin-i18n.ts` (nav keys; delete `scraper` blocks; add `system` and `corpus` blocks in ru/ka/en)
- Modify: `frontend/app/admin/layout.tsx` (navigation)
- Modify: `frontend/app/admin/page.tsx` (two attention links)
- Delete: `frontend/app/admin/scraper/page.tsx`
- Modify: `frontend/app/admin/documents/page.tsx` (initial `doc_type` from URL)

**Interfaces:**
- Produces types:

```ts
export const SYSTEM_JOBS = ['scraper', 'canary', 'backup', 'restore_drill'] as const;
export type SystemJobName = (typeof SYSTEM_JOBS)[number];
export type SystemJobState = 'ok' | 'stale' | 'failed' | 'skipped' | 'unknown';
export interface SystemJob {
  job: SystemJobName; state: SystemJobState;
  started_at: string | null; finished_at: string | null; exit_code: number | null;
  summary: string | null; trigger: 'cron' | 'manual' | null; skipped: boolean; log_tail: string[];
}
export interface SystemStatus { generated_at: string; jobs: SystemJob[] }
export interface CorpusTypeRow { document_type: string; documents: number; added_30d: number; without_date: number; without_chunks: number }
export interface CorpusWeek { week_start: string; added: number; partial: boolean }
export interface Corpus {
  totals: { documents: number; chunks: number; added_7d: number; added_30d: number; last_ingest: string | null };
  by_type: CorpusTypeRow[]; weekly: CorpusWeek[];
  pending: { decision_facts: number; law_amendments: number };
}
```

- Produces copy keys: `c.nav.system`, `c.nav.corpus`; `c.system.*` and `c.corpus.*` exactly as below.

- [ ] **Step 1: Types** — append the block above to `frontend/lib/admin-types.ts`.

- [ ] **Step 2: Copy**

In all three locales, in `nav` replace `scraper: '…'` with `system` and `corpus` keys:
- ru: `system: 'Состояние системы', corpus: 'Корпус',`
- ka: `system: 'სისტემის მდგომარეობა', corpus: 'კორპუსი',`
- en: `system: 'System health', corpus: 'Corpus',`

Delete the `scraper: { … }` block in all three locales. Add after `documents: { … }`:

ru:

```ts
  system: {
    title: 'Состояние системы',
    subtitle: 'Ночные задачи на сервере: когда последний раз отработали и чем закончились. Время тбилисское.',
    jobs: { scraper: 'Скрапер', canary: 'Канарейка', backup: 'Бэкап базы', restore_drill: 'Проверка восстановления' } satisfies Record<SystemJobName, string>,
    expected: { scraper: 'запускается каждую ночь и днём', canary: 'запускается каждую ночь', backup: 'запускается каждую ночь', restore_drill: 'запускается раз в месяц' } satisfies Record<SystemJobName, string>,
    states: { ok: 'В порядке', stale: 'Просрочено', failed: 'Ошибка', skipped: 'Пропущено (занято)', unknown: 'Нет данных' } satisfies Record<SystemJobState, string>,
    lastRun: (d: string) => `Последний запуск: ${d}`,
    justNow: 'только что', hoursAgo: (n: string) => `${n} ч назад`, daysAgo: (n: string) => `${n} дн. назад`,
    manual: 'запущено вручную', exitCode: (n: string) => `код выхода ${n}`,
    showLog: 'Показать лог', logEmpty: 'Лог пуст.',
    noData: 'Статус ещё не записан. Он появится после ближайшего запуска задачи.',
  },
  corpus: {
    title: 'Корпус',
    subtitle: 'Что лежит в базе документов и как она пополняется. Время тбилисское.',
    documents: 'Документов', chunks: 'Фрагментов (чанков)', added7d: 'Добавлено за 7 дней', added30d: 'Добавлено за 30 дней',
    lastIngest: 'Последнее поступление', decisionsQueue: 'Решения ждут извлечения фактов', amendmentsQueue: 'Поправки ждут извлечения',
    byType: 'По типам документов', type: 'Тип', total: 'Документов', new30: 'Новых за 30 дней',
    withoutDate: 'Без даты публикации', withoutChunks: 'Без чанков',
    weekly: 'Поступления по неделям', added: 'Добавлено', week: 'Неделя',
  },
```

en:

```ts
  system: {
    title: 'System health',
    subtitle: 'Nightly server jobs: when each last ran and how it ended. Tbilisi time.',
    jobs: { scraper: 'Scraper', canary: 'Canary', backup: 'Database backup', restore_drill: 'Restore drill' },
    expected: { scraper: 'runs nightly and during the day', canary: 'runs nightly', backup: 'runs nightly', restore_drill: 'runs monthly' },
    states: { ok: 'OK', stale: 'Overdue', failed: 'Failed', skipped: 'Skipped (busy)', unknown: 'No data' },
    lastRun: (d: string) => `Last run: ${d}`,
    justNow: 'just now', hoursAgo: (n: string) => `${n} h ago`, daysAgo: (n: string) => `${n} d ago`,
    manual: 'started manually', exitCode: (n: string) => `exit code ${n}`,
    showLog: 'Show log', logEmpty: 'Log is empty.',
    noData: 'No status recorded yet. It appears after the job next runs.',
  },
  corpus: {
    title: 'Corpus',
    subtitle: 'What the document base holds and how it grows. Tbilisi time.',
    documents: 'Documents', chunks: 'Chunks', added7d: 'Added in 7 days', added30d: 'Added in 30 days',
    lastIngest: 'Last ingest', decisionsQueue: 'Decisions awaiting fact extraction', amendmentsQueue: 'Amendments awaiting extraction',
    byType: 'By document type', type: 'Type', total: 'Documents', new30: 'New in 30 days',
    withoutDate: 'No publication date', withoutChunks: 'No chunks',
    weekly: 'Ingest by week', added: 'Added', week: 'Week',
  },
```

ka (draft; run the `anthropic-skills:georgian-writing-style` skill over these strings before committing and apply its fixes; list them in the PR for Gela):

```ts
  system: {
    title: 'სისტემის მდგომარეობა',
    subtitle: 'სერვერის ღამის ამოცანები: როდის შესრულდა ბოლოს და რით დასრულდა. დრო თბილისისაა.',
    jobs: { scraper: 'მონაცემების შეგროვება', canary: 'საკონტროლო შემოწმება', backup: 'ბაზის სარეზერვო ასლი', restore_drill: 'აღდგენის შემოწმება' },
    expected: { scraper: 'ეშვება ყოველ ღამე და დღისით', canary: 'ეშვება ყოველ ღამე', backup: 'ეშვება ყოველ ღამე', restore_drill: 'ეშვება თვეში ერთხელ' },
    states: { ok: 'წესრიგშია', stale: 'დაგვიანებულია', failed: 'შეცდომა', skipped: 'გამოტოვებულია (დაკავებულია)', unknown: 'მონაცემები არ არის' },
    lastRun: (d: string) => `ბოლო გაშვება: ${d}`,
    justNow: 'ახლახან', hoursAgo: (n: string) => `${n} სთ-ის წინ`, daysAgo: (n: string) => `${n} დღის წინ`,
    manual: 'გაშვებულია ხელით', exitCode: (n: string) => `დასრულების კოდი ${n}`,
    showLog: 'ჟურნალის ჩვენება', logEmpty: 'ჟურნალი ცარიელია.',
    noData: 'სტატუსი ჯერ არ ჩაწერილა. ის გამოჩნდება ამოცანის შემდეგი გაშვების შემდეგ.',
  },
  corpus: {
    title: 'კორპუსი',
    subtitle: 'რა ინახება დოკუმენტების ბაზაში და როგორ ივსება ის. დრო თბილისისაა.',
    documents: 'დოკუმენტები', chunks: 'ფრაგმენტები', added7d: 'დაემატა 7 დღეში', added30d: 'დაემატა 30 დღეში',
    lastIngest: 'ბოლო შევსება', decisionsQueue: 'გადაწყვეტილებები ელოდება ფაქტების ამოღებას', amendmentsQueue: 'ცვლილებები ელოდება დამუშავებას',
    byType: 'დოკუმენტების ტიპების მიხედვით', type: 'ტიპი', total: 'დოკუმენტები', new30: 'ახალი 30 დღეში',
    withoutDate: 'გამოქვეყნების თარიღის გარეშე', withoutChunks: 'ფრაგმენტების გარეშე',
    weekly: 'შევსება კვირების მიხედვით', added: 'დაემატა', week: 'კვირა',
  },
```

Add `import type { SystemJobName, SystemJobState } from './admin-types';` at the top of `admin-i18n.ts` if those types are not yet imported there (follow how `Verdict`/`QualityFlag` are imported).

- [ ] **Step 3: Navigation and dashboard links**

`frontend/app/admin/layout.tsx`: replace the `scraper` entry with two entries, keeping order (after `analytics`):

```ts
  { key: 'corpus', href: '/admin/corpus', icon: ArchiveIcon },
  { key: 'system', href: '/admin/system', icon: ActivityLogIcon },
```

and add `ArchiveIcon` to the `@radix-ui/react-icons` import.

`frontend/app/admin/page.tsx` lines 23–24: change `'/admin/scraper'` to `'/admin/system'` for `ingest_stale` and to `'/admin/corpus'` for `decisionsQueue`.

Delete `frontend/app/admin/scraper/page.tsx` (`rtk git rm`).

- [ ] **Step 4: Documents filter from URL**

In `frontend/app/admin/documents/page.tsx`:
- import `Suspense` from `react` and `useSearchParams` from `next/navigation`;
- rename the component to `DocumentsPage` (not exported), and initialise `docType` from the URL only if it is a known type:

```ts
  const params = useSearchParams();
  const initialType = params.get('doc_type') ?? '';
  const [docType, setDocType] = useState(TYPES.includes(initialType) ? initialType : '');
```

- add at the bottom:

```tsx
export default function AdminDocuments() {
  return <Suspense><DocumentsPage /></Suspense>;
}
```

- [ ] **Step 5: Type-check and lint**

Run (from `frontend/`): `rtk npx tsc --noEmit` → no errors. (Pages for `/admin/system` and `/admin/corpus` don't exist yet; that is fine — only the nav links point there.)
Run: `rtk npm run lint` → no errors.

- [ ] **Step 6: Commit**

```bash
rtk git add -A frontend/lib/admin-types.ts frontend/lib/admin-i18n.ts frontend/app/admin/layout.tsx frontend/app/admin/page.tsx frontend/app/admin/scraper frontend/app/admin/documents/page.tsx
rtk git commit -m "feat(admin): system/corpus copy and navigation; documents filter from URL; drop scraper page"
```

---

### Task 6: `/admin/system` page

**Files:**
- Create: `frontend/app/admin/system/page.tsx`
- Modify: `frontend/app/admin/admin.module.css` (job card classes)
- Create: `frontend/e2e/admin-system.spec.ts`
- Modify: `frontend/playwright.config.ts` (`testMatch` add `'admin-system.spec.ts'`)

**Interfaces:**
- Consumes: `GET /api/v1/admin/system` (Task 3), `SystemStatus` types and `c.system` copy (Task 5), `Badge` (`tone: 'success' | 'warning' | 'error' | 'neutral'`), `PageHeader`, `AdminState`, `useAdminFetch`, `formatDateTime`, `formatNumber`.

- [ ] **Step 1: Write the failing e2e spec**

`frontend/e2e/admin-system.spec.ts`:

```ts
import { expect, Page, Route, test } from '@playwright/test';

const NOW = Date.parse('2026-10-12T10:00:00Z');
const job = (name: string, state: string, extra: Record<string, unknown> = {}) => ({
  job: name, state, started_at: '2026-10-12T03:00:00Z', finished_at: '2026-10-12T03:40:00Z', exit_code: 0,
  summary: 'ok', trigger: 'cron', skipped: false, log_tail: ['first line', 'last line'], ...extra,
});
const STATUS = {
  generated_at: '2026-10-12T10:00:00',
  jobs: [
    job('scraper', 'ok', { summary: '+3 new docs (full)', trigger: 'manual' }),
    job('canary', 'failed', { exit_code: 1, summary: 'CANARY: 7/10 failed=pit_rate' }),
    job('backup', 'stale', { finished_at: '2026-10-10T01:37:00Z', summary: 'ok infohub_ai-20261010T013001Z.dump 2710 MiB' }),
    { job: 'restore_drill', state: 'unknown', started_at: null, finished_at: null, exit_code: null, summary: null,
      trigger: null, skipped: false, log_tail: [] },
  ],
};

async function json(route: Route, data: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
}

async function setup(page: Page, lang = 'ru', failFirst = false) {
  await page.clock.setFixedTime(NOW);
  await page.addInitScript((language) => {
    localStorage.setItem('ta_lang', language);
    localStorage.setItem('ta_authenticated', '1');
  }, lang);
  let failures = failFirst ? 1 : 0;
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === '/api/v1/auth/me') return json(route, { username: 'admin', role: 'admin' });
    if (url.pathname === '/api/v1/admin/system') {
      if (failures > 0) { failures -= 1; return json(route, { detail: 'boom' }, 500); }
      return json(route, STATUS);
    }
    return json(route, { detail: 'No fixture' }, 404);
  });
}

const card = (page: Page, name: string) => page.getByRole('article').filter({ has: page.getByRole('heading', { name }) });

test('each job shows its state, summary and age', async ({ page }) => {
  await setup(page);
  await page.goto('/admin/system');
  await expect(page.getByRole('heading', { level: 1, name: 'Состояние системы' })).toBeVisible();
  await expect(card(page, 'Скрапер')).toContainText('В порядке');
  await expect(card(page, 'Скрапер')).toContainText('+3 new docs (full)');
  await expect(card(page, 'Скрапер')).toContainText('запущено вручную');
  await expect(card(page, 'Скрапер')).toContainText('6 ч назад');
  await expect(card(page, 'Канарейка')).toContainText('Ошибка');
  await expect(card(page, 'Канарейка')).toContainText('код выхода 1');
  await expect(card(page, 'Бэкап базы')).toContainText('Просрочено');
  await expect(card(page, 'Бэкап базы')).toContainText('2 дн. назад');
  await expect(card(page, 'Проверка восстановления')).toContainText('Нет данных');
  await expect(card(page, 'Проверка восстановления')).toContainText('Статус ещё не записан');
});

test('log is collapsed until asked for', async ({ page }) => {
  await setup(page);
  await page.goto('/admin/system');
  const scraper = card(page, 'Скрапер');
  await expect(scraper.getByText('last line')).toBeHidden();
  await scraper.getByText('Показать лог').click();
  await expect(scraper.getByText('last line')).toBeVisible();
  await expect(card(page, 'Проверка восстановления').getByText('Показать лог')).toHaveCount(0);
});

test('load error offers a retry', async ({ page }) => {
  await setup(page, 'ru', true);
  await page.goto('/admin/system');
  await expect(page.getByRole('alert')).toBeVisible();
  await page.getByRole('button', { name: 'Повторить' }).click();
  await expect(card(page, 'Скрапер')).toContainText('В порядке');
});

test('english and georgian copy render', async ({ page }) => {
  await setup(page, 'en');
  await page.goto('/admin/system');
  await expect(card(page, 'Database backup')).toContainText('Overdue');
  await setup(page, 'ka');
  await page.goto('/admin/system');
  await expect(page.getByRole('heading', { level: 1, name: 'სისტემის მდგომარეობა' })).toBeVisible();
});

test('system visual baseline', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await setup(page);
  await page.goto('/admin/system');
  await expect(card(page, 'Скрапер')).toContainText('В порядке');
  await page.evaluate(async () => { await document.fonts.ready; });
  await expect(page).toHaveScreenshot('admin-system-ru-desktop.png', { fullPage: true });

  const mobile = await page.context().newPage();
  await setup(mobile, 'ka');
  await mobile.setViewportSize({ width: 390, height: 844 });
  await mobile.goto('/admin/system');
  await expect(mobile.getByRole('heading', { level: 1, name: 'სისტემის მდგომარეობა' })).toBeVisible();
  const overflow = await mobile.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  await mobile.evaluate(async () => { await document.fonts.ready; });
  await expect(mobile).toHaveScreenshot('admin-system-ka-mobile.png', { fullPage: true });
  await mobile.close();
});
```

If the installed Playwright has no `page.clock` (check `frontend/package.json` `@playwright/test` ≥ 1.45), replace `page.clock.setFixedTime(NOW)` with an `addInitScript` that overrides `Date.now`. Add `'admin-system.spec.ts'` to `testMatch` in `frontend/playwright.config.ts`.

- [ ] **Step 2: CSS** — append to `frontend/app/admin/admin.module.css`:

```css
/* System health */
.jobGrid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.jobCard { display: flex; flex-direction: column; gap: 10px; min-width: 0; padding: 20px; border-radius: var(--radius); }
.jobHead { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; }
.jobTitle { margin: 0; font-size: 16px; font-weight: 600; }
.jobMeta { margin: 0; font-size: 13px; color: hsl(var(--muted-foreground)); overflow-wrap: anywhere; }
.jobSummary { margin: 0; font-size: 14px; overflow-wrap: anywhere; }
.jobLog summary { cursor: pointer; font-size: 13px; color: hsl(var(--muted-foreground)); }
.jobLog[open] summary { margin-bottom: 8px; }
@media (max-width: 860px) { .jobGrid { grid-template-columns: minmax(0, 1fr); } }
```

- [ ] **Step 3: Page** — `frontend/app/admin/system/page.tsx`:

```tsx
'use client';

import { formatDateTime, formatNumber, useAdminCopy, type AdminCopy, type AdminLocale } from '@/lib/admin-i18n';
import type { SystemJob, SystemJobState, SystemStatus } from '@/lib/admin-types';
import { useAdminFetch } from '@/lib/use-admin-fetch';
import { PageHeader } from '@/components/admin/PageHeader';
import { AdminState } from '@/components/admin/AdminState';
import { Badge, type BadgeTone } from '@/components/admin/Badge';
import styles from '../admin.module.css';

const TONE: Record<SystemJobState, BadgeTone> = { ok: 'success', stale: 'warning', failed: 'error', skipped: 'neutral', unknown: 'neutral' };
const ICON: Record<SystemJobState, string> = { ok: '●', stale: '◐', failed: '✕', skipped: '○', unknown: '○' };
const HOUR = 3_600_000;

function age(finishedAt: string, c: AdminCopy, locale: AdminLocale): string {
  const iso = /(?:[zZ]|[+-]\d\d:?\d\d)$/.test(finishedAt) ? finishedAt : `${finishedAt}Z`;
  const hours = Math.floor((Date.now() - Date.parse(iso)) / HOUR);
  if (hours < 1) return c.system.justNow;
  if (hours < 48) return c.system.hoursAgo(formatNumber(hours, locale));
  return c.system.daysAgo(formatNumber(Math.floor(hours / 24), locale));
}

function JobCard({ job, c, locale }: Readonly<{ job: SystemJob; c: AdminCopy; locale: AdminLocale }>) {
  const title = c.system.jobs[job.job];
  return <article className={`liquid-glass ${styles.jobCard}`} aria-labelledby={`job-${job.job}`}>
    <div className={styles.jobHead}>
      <h2 id={`job-${job.job}`} className={styles.jobTitle}>{title}</h2>
      <Badge tone={TONE[job.state]}><span aria-hidden="true">{ICON[job.state]}</span>{c.system.states[job.state]}</Badge>
    </div>
    {job.finished_at === null ? <p className={styles.jobMeta}>{c.system.noData}</p> : <>
      <p className={styles.jobMeta}>
        {c.system.lastRun(formatDateTime(job.finished_at, locale))} · {age(job.finished_at, c, locale)}
        {job.trigger === 'manual' && <> · {c.system.manual}</>}
        {job.exit_code !== null && job.exit_code !== 0 && <> · {c.system.exitCode(String(job.exit_code))}</>}
      </p>
      {job.summary && <p className={`${styles.jobSummary} ${styles.mono}`}>{job.summary}</p>}
    </>}
    <p className={styles.jobMeta}>{c.system.expected[job.job]}</p>
    {job.log_tail.length > 0 && <details className={styles.jobLog}>
      <summary>{c.system.showLog}</summary>
      <pre className={styles.log}>{job.log_tail.join('\n')}</pre>
    </details>}
  </article>;
}

export default function AdminSystem() {
  const { c, locale } = useAdminCopy();
  const { data, error, reload } = useAdminFetch<SystemStatus>('/api/v1/admin/system');

  let body = <AdminState kind="loading" />;
  if (error) body = <AdminState kind="error" onRetry={reload} />;
  else if (data) body = <div className={styles.jobGrid}>
    {data.jobs.map((job) => <JobCard key={job.job} job={job} c={c} locale={locale} />)}
  </div>;

  return <div className={styles.page}>
    <PageHeader title={c.system.title} subtitle={c.system.subtitle}
      actions={<button type="button" className={styles.button} onClick={reload}>{c.common.refresh}</button>} />
    {body}
  </div>;
}
```

Check `PageHeader` accepts both `subtitle` and `actions` (it does on the trends/scraper pages; if `subtitle` + `actions` together is unsupported, follow the component's props). `formatDateTime` uses the browser time zone; the admin is in Tbilisi and the e2e baseline container runs in UTC — keep it consistent with the other admin pages rather than forcing a zone.

Note: the `6 ч назад` assertion relies on `NOW` 10:00Z − 03:40Z = 6 h 20 m → 6.

- [ ] **Step 4: Build and run e2e (non-visual)**

Per memory, a local Next build takes ~15 min and may be killed for low memory. Run: (from `frontend/`) `rtk npm run build` then `rtk npx playwright test admin-system.spec.ts --grep-invert "visual baseline"`. Expected: 4 passed. If the local build is killed, push and rely on CI's `visual` job (it runs all specs); do not claim it passed without output.

- [ ] **Step 5: Commit**

```bash
rtk git add frontend/app/admin/system/page.tsx frontend/app/admin/admin.module.css frontend/e2e/admin-system.spec.ts frontend/playwright.config.ts
rtk git commit -m "feat(admin): system health page"
```

---

### Task 7: `/admin/corpus` page

**Files:**
- Create: `frontend/app/admin/corpus/page.tsx`
- Create: `frontend/e2e/admin-corpus.spec.ts`
- Modify: `frontend/playwright.config.ts` (`testMatch` add `'admin-corpus.spec.ts'`)

**Interfaces:**
- Consumes: `GET /api/v1/admin/corpus` (Task 4), `Corpus` types and `c.corpus` copy (Task 5), `StatTile`, `DataTable` + `Column`, `TrendChart` (props listed in stage 3: `title, labels, series, format, partialLast, emptyText, dataLabel, periodLabel, partialLabel, dash`), `c.trends.showData`, `c.trends.empty`, `c.trends.partial`.

- [ ] **Step 1: Write the failing e2e spec**

`frontend/e2e/admin-corpus.spec.ts`:

```ts
import { expect, Page, Route, test } from '@playwright/test';

const weeks = Array.from({ length: 12 }, (_, i) => {
  const d = new Date(Date.UTC(2026, 6, 27 + i * 7));
  return { week_start: d.toISOString().slice(0, 10), added: [9, 4, 0, 12, 7, 3, 5, 8, 2, 6, 11, 1][i], partial: i === 11 };
});
const CORPUS = {
  totals: { documents: 14725, chunks: 269218, added_7d: 12, added_30d: 61, last_ingest: '2026-10-12T03:12:40' },
  by_type: [
    { document_type: 'court_decision', documents: 11249, added_30d: 40, without_date: 0, without_chunks: 0 },
    { document_type: 'law', documents: 1204, added_30d: 3, without_date: 572, without_chunks: 2 },
  ],
  weekly: weeks,
  pending: { decision_facts: 4, law_amendments: 0 },
};

async function json(route: Route, data: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
}

async function setup(page: Page, lang = 'ru') {
  await page.addInitScript((language) => {
    localStorage.setItem('ta_lang', language);
    localStorage.setItem('ta_authenticated', '1');
  }, lang);
  const documentQueries: string[] = [];
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === '/api/v1/auth/me') return json(route, { username: 'admin', role: 'admin' });
    if (url.pathname === '/api/v1/admin/corpus') return json(route, CORPUS);
    if (url.pathname === '/api/v1/admin/documents') {
      documentQueries.push(url.searchParams.get('doc_type') ?? '');
      return json(route, { total: 0, items: [] });
    }
    return json(route, { detail: 'No fixture' }, 404);
  });
  return { documentQueries };
}

test('totals, queues and per-type gaps', async ({ page }) => {
  await setup(page);
  await page.goto('/admin/corpus');
  await expect(page.getByRole('heading', { level: 1, name: 'Корпус' })).toBeVisible();
  await expect(page.getByText('14 725')).toBeVisible();
  await expect(page.getByText('269 218')).toBeVisible();
  await expect(page.getByText('Решения ждут извлечения фактов')).toBeVisible();
  const law = page.getByRole('row').filter({ hasText: 'law' });
  await expect(law).toContainText('572');
});

test('weekly chart lists 12 weeks and marks the running one', async ({ page }) => {
  await setup(page);
  await page.goto('/admin/corpus');
  const chart = page.getByRole('figure').filter({ hasText: 'Поступления по неделям' });
  await chart.getByText('Показать данные').click();
  await expect(chart.locator('tbody tr')).toHaveCount(12);
  await expect(chart.locator('tbody tr').last()).toContainText('текущий период ещё идёт');
});

test('a type links to the filtered documents list', async ({ page }) => {
  const { documentQueries } = await setup(page);
  await page.goto('/admin/corpus');
  await page.getByRole('link', { name: 'law', exact: true }).click();
  await expect(page).toHaveURL(/\/admin\/documents\?doc_type=law$/);
  await expect(page.getByRole('combobox', { name: 'Тип' })).toHaveValue('law');
  await expect.poll(() => documentQueries.at(-1)).toBe('law');
});

test('unknown doc_type in the URL is ignored', async ({ page }) => {
  const { documentQueries } = await setup(page);
  await page.goto('/admin/documents?doc_type=evil');
  await expect.poll(() => documentQueries.at(-1)).toBe('');
});

test('corpus visual baseline', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await setup(page);
  await page.goto('/admin/corpus');
  await expect(page.getByText('14 725')).toBeVisible();
  await page.evaluate(async () => { await document.fonts.ready; });
  await expect(page).toHaveScreenshot('admin-corpus-ru-desktop.png', { fullPage: true });
});
```

Add `'admin-corpus.spec.ts'` to `testMatch`. (The RU number format uses a narrow no-break space; if `getByText('14 725')` doesn't match, use `getByText(/14\s725/)`.)

- [ ] **Step 2: Page** — `frontend/app/admin/corpus/page.tsx`:

```tsx
'use client';

import Link from 'next/link';
import { formatDateTime, formatNumber, useAdminCopy, type AdminCopy, type AdminLocale } from '@/lib/admin-i18n';
import type { Corpus, CorpusTypeRow } from '@/lib/admin-types';
import { useAdminFetch } from '@/lib/use-admin-fetch';
import { PageHeader } from '@/components/admin/PageHeader';
import { StatTile } from '@/components/admin/StatTile';
import { AdminState } from '@/components/admin/AdminState';
import { DataTable, type Column } from '@/components/admin/DataTable';
import { TrendChart } from '@/components/admin/TrendChart';
import styles from '../admin.module.css';

// Validated with the dataviz palette checker on the dark admin surface (stage 3).
const BLUE = '#3b82f6';

function weekLabel(start: string, locale: AdminLocale): string {
  return new Intl.DateTimeFormat(locale, { day: '2-digit', month: '2-digit', timeZone: 'UTC' })
    .format(new Date(`${start}T00:00:00Z`));
}

function CorpusView({ data, c, locale }: Readonly<{ data: Corpus; c: AdminCopy; locale: AdminLocale }>) {
  const n = (v: number) => formatNumber(v, locale);
  const gap = (v: number) => (v > 0 ? <strong className={styles.warning}>{n(v)}</strong> : n(v));
  const columns: Column<CorpusTypeRow>[] = [
    { key: 'type', header: c.corpus.type, render: (r) =>
      <Link href={`/admin/documents?doc_type=${encodeURIComponent(r.document_type)}`}>{r.document_type}</Link> },
    { key: 'documents', header: c.corpus.total, render: (r) => n(r.documents) },
    { key: 'new', header: c.corpus.new30, render: (r) => n(r.added_30d) },
    { key: 'noDate', header: c.corpus.withoutDate, render: (r) => gap(r.without_date) },
    { key: 'noChunks', header: c.corpus.withoutChunks, render: (r) => gap(r.without_chunks) },
  ];
  const { totals, pending } = data;
  return <>
    <div className={`${styles.tiles} ${styles.tiles3}`}>
      <StatTile label={c.corpus.documents} value={n(totals.documents)} />
      <StatTile label={c.corpus.chunks} value={n(totals.chunks)} />
      <StatTile label={c.corpus.lastIngest} value={formatDateTime(totals.last_ingest, locale)} />
      <StatTile label={c.corpus.added7d} value={n(totals.added_7d)} />
      <StatTile label={c.corpus.added30d} value={n(totals.added_30d)} />
      <StatTile label={c.corpus.decisionsQueue} value={n(pending.decision_facts)}
        detail={`${c.corpus.amendmentsQueue}: ${n(pending.law_amendments)}`} />
    </div>
    <section className={`liquid-glass ${styles.panel}`}>
      <h2 className={styles.panelTitle}>{c.corpus.byType}</h2>
      <DataTable columns={columns} rows={data.by_type} rowKey={(r) => r.document_type} loading={false} error={false}
        onRetry={() => undefined} emptyText={c.common.empty} />
    </section>
    <section className={`liquid-glass ${styles.panel}`}>
      <TrendChart title={c.corpus.weekly} format={n}
        labels={data.weekly.map((w) => weekLabel(w.week_start, locale))}
        series={[{ key: 'added', label: c.corpus.added, color: BLUE, values: data.weekly.map((w) => w.added) }]}
        partialLast={data.weekly.at(-1)?.partial ?? false} emptyText={c.trends.empty} dataLabel={c.trends.showData}
        periodLabel={c.corpus.week} partialLabel={c.trends.partial} dash={c.common.dash} />
    </section>
  </>;
}

export default function AdminCorpus() {
  const { c, locale } = useAdminCopy();
  const { data, error, reload } = useAdminFetch<Corpus>('/api/v1/admin/corpus');

  let body = <AdminState kind="loading" />;
  if (error) body = <AdminState kind="error" onRetry={reload} />;
  else if (data) body = <CorpusView data={data} c={c} locale={locale} />;

  return <div className={styles.page}>
    <PageHeader title={c.corpus.title} subtitle={c.corpus.subtitle}
      actions={<button type="button" className={styles.button} onClick={reload}>{c.common.refresh}</button>} />
    {body}
  </div>;
}
```

Check `DataTable`'s required props in `frontend/components/admin/DataTable.tsx` and drop any of `loading/error/onRetry` that are optional there.

- [ ] **Step 3: Type-check, lint, e2e (non-visual)**

Run (from `frontend/`): `rtk npx tsc --noEmit && rtk npm run lint`, then (after a build) `rtk npx playwright test admin-corpus.spec.ts --grep-invert "visual baseline"` → 4 passed. Same fallback to CI as Task 6.

- [ ] **Step 4: Commit**

```bash
rtk git add frontend/app/admin/corpus/page.tsx frontend/e2e/admin-corpus.spec.ts frontend/playwright.config.ts
rtk git commit -m "feat(admin): corpus page with per-type gaps and weekly ingest"
```

---

### Task 8: Shared e2e matrix, visual baselines, docs, spec sync

**Files:**
- Modify: `frontend/e2e/admin.spec.ts` (fixtures + `PAGES`)
- Regenerate: `frontend/e2e/__screenshots__/*.png` affected by the nav change, plus new `admin-system-ru-desktop.png`, `admin-system-ka-mobile.png`, `admin-corpus-ru-desktop.png`
- Modify: `docs/PRODUCTION_OPERATIONS.md`, `docs/DEVELOPMENT_MEMORY.md`
- Modify: `docs/superpowers/specs/2026-10-12-admin-stage5-ops-corpus-design.md` (deviations)

- [ ] **Step 1: Update `admin.spec.ts`**

Delete the `ops` fixture constant and the `'/api/v1/admin/ops': ops,` fixture line. Add fixtures:

```ts
const system = { generated_at: '2026-10-12T10:00:00', jobs: ['scraper', 'canary', 'backup', 'restore_drill'].map((job) => ({
  job, state: 'ok', started_at: '2026-10-12T03:00:00Z', finished_at: '2026-10-12T03:40:00Z', exit_code: 0,
  summary: job === 'scraper' ? '+14 new docs (full)' : 'ok', trigger: 'cron', skipped: false, log_tail: [] })) };
const corpusFixture = {
  totals: { documents: 48211, chunks: 269218, added_7d: 12, added_30d: 61, last_ingest: '2026-10-11T02:10:00' },
  by_type: [{ document_type: 'law', documents: 1204, added_30d: 3, without_date: 0, without_chunks: 0 }],
  weekly: Array.from({ length: 12 }, (_, i) => ({ week_start: `2026-${i < 6 ? '08' : '09'}-0${(i % 6) + 1}`, added: i, partial: i === 11 })),
  pending: { decision_facts: 249, law_amendments: 0 },
};
```

and in `fixtures`:

```ts
      '/api/v1/admin/system': system,
      '/api/v1/admin/corpus': corpusFixture,
```

In `PAGES` replace the `/admin/scraper` entry with:

```ts
  { path: '/admin/corpus', ready: text('law', true) },
  { path: '/admin/system', ready: text('+14 new docs (full)') },
```

- [ ] **Step 2: Regenerate visual baselines in the pinned container**

Use the same container procedure as stage 3 (commit `8917b37`; see `docs/DEVELOPMENT_MEMORY.md` stage 3 entry for the exact `docker run` line with the pinned image `mcr.microsoft.com/playwright@sha256:dcc5531e97840b9b5e794f2814476b21571c5124a3fca2267d73041f56e7580e` and `--update-snapshots`). It takes ~40 min on this machine — run it in the background. Commit only PNGs whose change is explained by: the new nav items (every admin baseline with a sidebar) or the three new pages. Inspect at least `admin-dashboard-ru-desktop.png` and the three new PNGs visually before committing. If Docker is unavailable, stop and report — don't commit Windows-rendered baselines.

- [ ] **Step 3: Docs**

`docs/PRODUCTION_OPERATIONS.md`, in the admin section, add a short block:

```markdown
### Состояние системы и корпус (этап 5a)

- `/admin/system` показывает последний запуск скрапера, канарейки, бэкапа и restore drill из
  `/root/infohub/ops-status/<job>.json`. Файлы пишет `ops/write_job_status.py` из EXIT-ловушек
  `run_scraper.sh`, `ops/backup-infohub-db.sh`, `ops/restore-drill-infohub-db.sh`; папка смонтирована
  в бэкенд только для чтения (`/app/ops-status`).
- После первого деплоя все карточки показывают «Нет данных» до ближайшего запуска каждой задачи.
- `/admin/corpus` — только чтение из `documents`/`document_chunks`.
- Удалены: страница `/admin/scraper`, `GET /api/v1/admin/ops`, роутер `/api/v1/scraper/*`.
```

`docs/DEVELOPMENT_MEMORY.md`: add a dated (2026-10-12) stage 5a entry in the same format as the stage 3 entry: what shipped, the file-channel decision (spec option A), the deviations listed at the top of this plan, and that 5b (manual launch) is next.

- [ ] **Step 4: Sync the spec**

In the spec, part 5a §1: replace the `ops/write_job_status.sh` heading/paragraph with `ops/write_job_status.py` and the CLI from Task 1; in §2 state table replace the `exit_code == 75` rows with: `skipped` — `skipped: true` in the file (backup exits 0, drill exits 75 on a busy lock); `failed` — `exit_code != 0` and not skipped. In §4 replace `ops/tests/test_write_job_status.sh` with `backend/tests/test_ops_job_status.py`. In §3 replace "редирект не нужен" sentence context: add that dashboard links now point to `/admin/system` and `/admin/corpus`.

- [ ] **Step 5: Full local verification**

From `backend/`: `rtk python -m pytest tests/test_ops_job_status.py tests/test_admin_system.py tests/test_admin_trends.py -q` → all pass.
From `frontend/`: `rtk npx tsc --noEmit && rtk npm run lint` → clean.
Grep `frontend/app/admin` for `style={{` → no hits.

- [ ] **Step 6: Commit and push**

```bash
rtk git add -A frontend/e2e docs
rtk git commit -m "test(admin): system/corpus in the page matrix; baselines; docs for stage 5a"
rtk git push -u origin feat/admin-stage5-ops-corpus
```

Then open the PR (`gh pr create`) titled `Admin stage 5a: system health and corpus`, body: summary, deploy notes (normal `deploy.sh`; creates `ops-status`; cards show "Нет данных" until each job's next run; do not deploy around 03:00–04:00 UTC), the KA strings list for Gela, and the 🤖 attribution line. Wait for CI; report its actual result.

---

## Self-review notes

- Spec 5a coverage: §1 status channel → Tasks 1–2; §2 `/admin/system` → Task 3, `/admin/corpus` → Task 4, cleanup → Task 4; §3 frontend → Tasks 5–7; §4 tests → each task + Task 8; §5 deploy → Task 2 (`install -d`) + Task 8 docs/PR notes.
- Names used across tasks: `system_status`, `corpus`, `window_of`, `tbilisi_midnight_utc`, `SystemStatus`, `SystemJob`, `Corpus`, `CorpusTypeRow`, `c.system.*`, `c.corpus.*` — consistent.
- Part 5b (requests, dispatcher, `run_canary.sh`, `INFOHUB_MANUAL_RUN`) is intentionally not in this plan.
