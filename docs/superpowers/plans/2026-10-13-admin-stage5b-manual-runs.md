# Admin Stage 5b — Manual Runs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** From `/admin/system` an admin can start four whitelisted host jobs: ingest-only scraper, full nightly run, canary and backup. Every start is journaled, never overlaps the nightly run and leaves the Telegram alerts unchanged.

**Architecture:** The backend never executes anything. `POST /api/v1/admin/system/jobs/{job}` checks guards, journals `ops.job_requested` and atomically drops `ops-requests/<job>.json` (a read-write bind mount). A host cron dispatcher (`ops/ops-dispatcher.sh`, every minute, own `flock`) picks requests by fixed file names and runs one of four hard-coded commands. It reports `running → done/skipped/failed` into `ops-status/<job>.request.json`, which the backend already reads through the read-only 5a mount. The page shows the request on the card and polls every 15 s while it is active.

**Tech Stack:** Bash + Python 3 stdlib (host), FastAPI + SQLAlchemy (backend), Next.js 16 / React client components (frontend), pytest, Playwright 1.62.1 (pinned container for baselines).

**Spec:** `docs/superpowers/specs/2026-10-12-admin-stage5-ops-corpus-design.md`, Part 5b (§6–§11). Part 5a is live on prod (`dc37bc1`).

## Global Constraints

- Whitelist, exactly: `scraper_ingest`, `scraper_full`, `canary`, `backup`. Restore drill has no button and no request path.
- The backend writes only to `ADMIN_OPS_REQUEST_DIR` (default `/app/ops-requests`). It gets no docker socket, no SSH and no host execution.
- No DB schema change. The journal row is `action="ops.job_requested"`, `target_type="ops_job"`, `target_id=<job>`, `after={"request_id": ...}`.
- Request file: `{"schema_version":1,"request_id":"<uuid4>","job":"<job>","requested_at":"YYYY-MM-DDTHH:MM:SSZ","actor_id":"<uuid>"}`, written with tmp + `os.replace`.
- 409 codes: `already_pending`, `scraper_busy`, `backup_too_recent` (last successful backup < 6 h), `canary_too_recent` (last canary run < 10 min). Errors use the existing `admin_error(status, code, message)` shape. The frontend localises by `code`.
- Request states: `queued`, `running`, `done`, `skipped`, `failed`. `reason` is `"busy"` for skipped and `"interrupted"` for a request stuck in `processing/` for more than 6 h.
- The dispatcher command map is a hard `case` on the file name:
  - `scraper_ingest` → `INFOHUB_JOB_TRIGGER=manual run_scraper.sh --ingest-only`
  - `scraper_full` → `INFOHUB_JOB_TRIGGER=manual INFOHUB_MANUAL_RUN=1 run_scraper.sh`
  - `canary` → `INFOHUB_JOB_TRIGGER=manual ops/run_canary.sh`
  - `backup` → `INFOHUB_JOB_TRIGGER=manual ops/backup-infohub-db.sh`
- With `INFOHUB_MANUAL_RUN=1`, `scraper_alert.sh` never writes `zero_new_streak`, neither increment nor reset. Failure alerts are still sent.
- Mounts and deploy:
  - `./ops-requests:/app/ops-requests` (read-write) on the backend.
  - `deploy_production.sh` runs `install -d -m 0770 ops-requests` and installs `/etc/cron.d/infohub-ops-dispatcher`.
- Host scripts are delivered by `git reset --hard` in `/root/infohub`, not by the image. The new `.sh` files must be committed with LF endings. Cron calls them through `/bin/bash`, so the exec bit does not matter.
- Copy has three languages (RU/KA/EN) with `satisfies`. New KA strings go through the Georgian style skill if it is installed (it was used in stage 5a Task 5) and are listed in the task report for Gela.
- Local backend tests need these env vars, and there is no conftest:
  `SECRET_KEY=test-secret-key-for-tests-minimum-32-characters JWT_SECRET_KEY=test-jwt-secret-for-tests-minimum-32 DATABASE_URL=sqlite:///test.db REDIS_URL=redis://localhost:6379/15 OPENAI_API_KEY=test-key`, run from `backend/`; delete `backend/test.db` afterwards.
- Shell-script tests need `bash` and `flock`. They are skipped on Windows (`needs_posix`) and run in Linux CI.
- Shell commands in this repo are prefixed with `rtk` (user rule), e.g. `rtk git commit`.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Double click / two tabs.** A second POST for the same job before the dispatcher runs must be 409 `already_pending`, never a second file. Covered in Task 4 (`test_second_request_is_already_pending`).
2. **Manual full run vs the nightly 03:00 run.** They share the scraper `flock`. The loser prints "Another scraper run is active" and must end as `skipped`, not `done`. Covered in Task 3 (`test_busy_scraper_is_skipped`).
3. **Dispatcher killed mid-job (deploy, reboot).** The card must not stay "running" forever. After 6 h the request becomes `failed`/`interrupted` and the button returns. Covered in Task 3 (`test_stuck_processing_becomes_interrupted`).
4. **Hostile or garbage file in `ops-requests/`** (unknown name, symlink, bad UUID, half-written temp file). It must never run a command. Unknown names and invalid files go to `rejected/`, and dot-temp files are ignored. Covered in Task 2 and Task 3.
5. **Commit failure after the file is written.** No orphan request may run without a journal row. The file is removed and the API returns 500. Covered in Task 4 (`test_commit_failure_removes_the_request_file`).

---

### Task 1: Shared canary runner and the manual-run streak guard

**Files:**
- Create: `ops/run_canary.sh`
- Modify: `run_scraper.sh` (replace the canary block, lines 212–221)
- Modify: `scraper_alert.sh`
- Modify: `.github/workflows/ci.yml` (`bash -n` list; backend pytest list next to `tests/test_ops_job_status.py`)
- Test: `backend/tests/test_ops_run_canary.py`

**Interfaces:**
- Produces: `ops/run_canary.sh [LOG_FILE]`, which exits with the canary's own exit code. Env overrides: `INFOHUB_BACKEND_CONTAINER`, `INFOHUB_CANARY_ALERT`, `INFOHUB_OPS_STATUS_WRITER`, `INFOHUB_LOG_DIR`, and `INFOHUB_JOB_TRIGGER` (passed through to the status writer).
- Produces: `scraper_alert.sh` honours `INFOHUB_DIR` (default `/root/infohub`) and `INFOHUB_MANUAL_RUN=1`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_ops_run_canary.py`:

```python
"""ops/run_canary.sh (nightly + manual canary) and the manual-run guard in scraper_alert.sh."""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CANARY = ROOT / "ops" / "run_canary.sh"
SCRAPER_ALERT = ROOT / "scraper_alert.sh"
RUN_SCRAPER = ROOT / "run_scraper.sh"

needs_posix = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("flock") is None,
    reason="requires bash and flock (Linux CI / production host)",
)


def _bin(tmp_path: Path, canary_exit: int) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(f'#!/usr/bin/env bash\necho "CANARY: 9/10 failed=pit_rate"\nexit {canary_exit}\n',
                      encoding="utf-8", newline="\n")
    docker.chmod(0o755)
    (bin_dir / "alert.sh").write_text('printf "%s|%s\\n" "$1" "$2" >> "$(dirname "$0")/alerts.log"\n',
                                      encoding="utf-8", newline="\n")
    return bin_dir


def _run_canary(tmp_path: Path, canary_exit: int = 0, args=(), trigger=None) -> subprocess.CompletedProcess:
    bin_dir = _bin(tmp_path, canary_exit)
    env = {**os.environ,
           "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
           "INFOHUB_CANARY_ALERT": str(bin_dir / "alert.sh"),
           "INFOHUB_OPS_STATUS_DIR": str(tmp_path / "status"),
           "INFOHUB_LOG_DIR": str(tmp_path / "logs")}
    env.pop("INFOHUB_JOB_TRIGGER", None)
    if trigger:
        env["INFOHUB_JOB_TRIGGER"] = trigger
    return subprocess.run(["bash", str(CANARY), *args], env=env, capture_output=True, text=True)


def _status(tmp_path: Path) -> dict:
    return json.loads((tmp_path / "status" / "canary.json").read_text(encoding="utf-8"))


@needs_posix
def test_manual_canary_writes_status_alert_and_own_log(tmp_path):
    result = _run_canary(tmp_path, trigger="manual")
    assert result.returncode == 0, result.stderr
    status = _status(tmp_path)
    assert status["exit_code"] == 0 and status["trigger"] == "manual"
    assert status["summary"] == "CANARY: 9/10 failed=pit_rate"
    assert (tmp_path / "bin" / "alerts.log").read_text(encoding="utf-8") == "0|CANARY: 9/10 failed=pit_rate\n"
    assert len(list((tmp_path / "logs").glob("canary_*.log"))) == 1


@needs_posix
def test_failing_canary_exits_with_its_code_and_appends_to_the_given_log(tmp_path):
    log = tmp_path / "nightly.log"
    log.write_text("before\n", encoding="utf-8")
    result = _run_canary(tmp_path, canary_exit=1, args=(str(log),))
    assert result.returncode == 1
    status = _status(tmp_path)
    assert status["exit_code"] == 1 and status["trigger"] == "cron"
    assert "CANARY: 9/10" in log.read_text(encoding="utf-8")
    assert not (tmp_path / "logs").exists()


def test_nightly_run_uses_the_shared_canary_script():
    text = RUN_SCRAPER.read_text(encoding="utf-8")
    assert 'ops/run_canary.sh" "$LOG_FILE"' in text
    assert "canary_eval.py" not in text


def _alert(tmp_path: Path, *args, manual=False, streak="1"):
    (tmp_path / "logs").mkdir(exist_ok=True)
    streak_file = tmp_path / "logs" / "zero_new_streak"
    streak_file.write_text(streak, encoding="utf-8")
    env = {**os.environ, "INFOHUB_DIR": str(tmp_path)}
    env.pop("INFOHUB_MANUAL_RUN", None)
    if manual:
        env["INFOHUB_MANUAL_RUN"] = "1"
    result = subprocess.run(["bash", str(SCRAPER_ALERT), *args], env=env, capture_output=True, text=True)
    return result, streak_file.read_text(encoding="utf-8").strip()


@needs_posix
@pytest.mark.parametrize("args", [("0", "0"), ("0", "5"), ("1", "?")])
def test_manual_run_leaves_the_zero_streak_alone(tmp_path, args):
    result, streak = _alert(tmp_path, *args, manual=True, streak="2")
    assert result.returncode == 0 and streak == "2"


@needs_posix
def test_manual_failure_still_alerts(tmp_path):
    result, _ = _alert(tmp_path, "1", "?", manual=True)
    assert "would have sent" in result.stdout and "FAILED" in result.stdout


@needs_posix
def test_nightly_run_still_counts_the_streak(tmp_path):
    _, streak = _alert(tmp_path, "0", "0", streak="1")
    assert streak == "2"
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run (from `backend/`, with the env vars from Global Constraints): `rtk python -m pytest tests/test_ops_run_canary.py -q`
Expected:
- On Windows, `test_nightly_run_uses_the_shared_canary_script` FAILS ("canary_eval.py" is still in `run_scraper.sh`) and the rest are SKIPPED.
- On Linux, everything fails.

- [ ] **Step 3: Create `ops/run_canary.sh`** (LF endings)

```bash
#!/usr/bin/env bash

# RAG canary: 10 known-answer questions through the real answer pipeline, then
# the Telegram alert and the admin status file (ops-status/canary.json).
# Called by the nightly run_scraper.sh with its log file, and by the ops
# dispatcher for a manual run (no argument: the canary writes its own log).
# Exits with the canary's own exit code.

set -uo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
CONTAINER_NAME="${INFOHUB_BACKEND_CONTAINER:-infohub-backend}"
ALERT="${INFOHUB_CANARY_ALERT:-$ROOT/canary_alert.sh}"
STATUS_WRITER="${INFOHUB_OPS_STATUS_WRITER:-$SCRIPT_DIR/write_job_status.py}"
LOG_DIR="${INFOHUB_LOG_DIR:-/root/infohub/logs}"

LOG_FILE="${1:-}"
if [ -z "$LOG_FILE" ]; then
    mkdir -p "$LOG_DIR"
    find "$LOG_DIR" -name "canary_*.log" -mtime +30 -delete
    LOG_FILE="$LOG_DIR/canary_$(date -u +%Y%m%d_%H%M%S).log"
    touch "$LOG_FILE"
    chmod 0600 "$LOG_FILE"
fi

STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
CANARY_EXIT=0
CANARY_OUT="$(docker exec "$CONTAINER_NAME" python /app/scripts/canary_eval.py 2>>"$LOG_FILE")" || CANARY_EXIT=$?
echo "$CANARY_OUT" | tee -a "$LOG_FILE"
CANARY_LINE="$(echo "$CANARY_OUT" | grep '^CANARY:' | tail -1 || true)"
bash "$ALERT" "$CANARY_EXIT" "$CANARY_LINE" 2>&1 | tee -a "$LOG_FILE" || true
python3 "$STATUS_WRITER" canary "$STARTED_AT" "$CANARY_EXIT" "$CANARY_LINE" "$LOG_FILE" || true
exit "$CANARY_EXIT"
```

- [ ] **Step 4: Replace the canary block in `run_scraper.sh`**

Replace everything from `# Nightly RAG canary: 10 known-answer questions...` through the `python3 "$STATUS_WRITER" canary ...` call (two lines) with:

```bash
# Nightly RAG canary (ops/run_canary.sh, shared with the admin manual run):
# alerts to Telegram below threshold and writes ops-status/canary.json. Non-fatal.
echo "Running RAG canary..." | tee -a "$LOG_FILE"
bash "$SCRIPT_DIR/ops/run_canary.sh" "$LOG_FILE" || true
```

- [ ] **Step 5: Add the manual-run guard to `scraper_alert.sh`**

- In the header comment, after the `Credentials are read...` paragraph, add:

```bash
# A manual full run from the admin panel (INFOHUB_MANUAL_RUN=1) still alerts on
# failure but never moves the nightly zero-new streak, in either direction.
```

- Replace `INFOHUB_DIR="/root/infohub"` with `INFOHUB_DIR="${INFOHUB_DIR:-/root/infohub}"`.
- After `ZERO_NEW_THRESHOLD=...`, add `MANUAL_RUN="${INFOHUB_MANUAL_RUN:-0}"`.
- After `read_streak() { ... }`, add:

```bash
write_streak() {
    [ "$MANUAL_RUN" = "1" ] || echo "$1" > "$STREAK_FILE"
}
```

- In the failure branch, replace `echo 0 > "$STREAK_FILE"` with `write_streak 0`.
- Directly after the failure branch's closing `fi`, insert:

```bash
if [ "$MANUAL_RUN" = "1" ]; then
    echo "[scraper_alert] manual run: +${NEW_DOCS} new docs — nightly streak unchanged."
    exit 0
fi
```

- In the zero-docs and healthy branches, replace the three remaining `echo ... > "$STREAK_FILE"` writes with `write_streak "$streak"`, `write_streak 0` and `write_streak 0`. They are unreachable for manual runs now, but this keeps one write path.

- [ ] **Step 6: CI lists**

In `.github/workflows/ci.yml`:
- Add `ops/run_canary.sh` to the `bash -n` list after `ops/restore-drill-infohub-db.sh`.
- Add `tests/test_ops_run_canary.py` to the backend pytest list right after `tests/test_ops_job_status.py`.

- [ ] **Step 7: Run the tests**

Run: `rtk python -m pytest tests/test_ops_run_canary.py tests/test_ops_job_status.py -q`, then `bash -n ops/run_canary.sh run_scraper.sh scraper_alert.sh`.
Expected: the source-text test passes locally and the POSIX tests are skipped on Windows. All pass in CI. `bash -n` prints nothing.

- [ ] **Step 8: Commit**

```bash
rtk git add ops/run_canary.sh run_scraper.sh scraper_alert.sh .github/workflows/ci.yml backend/tests/test_ops_run_canary.py
rtk git commit -m "feat(ops): shared canary runner; manual full run keeps the zero-new streak

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Host request helper `ops/ops_request.py`

**Files:**
- Create: `ops/ops_request.py`
- Modify: `.github/workflows/ci.yml` (backend pytest list)
- Test: `backend/tests/test_ops_request.py`

**Interfaces:**
- Produces this CLI, used by Task 3. `FILE` is a request file whose base name is `<job>.json`:
  - `ops_request.py check FILE`: exit 0 and print the normalised `request_id`, or exit 1.
  - `ops_request.py running FILE STARTED_AT`
  - `ops_request.py finish FILE STARTED_AT EXIT_CODE OUTPUT_FILE`
  - `ops_request.py interrupted FILE`
  - Bad usage exits 2. An unreadable request exits 1. A write error on `running`/`finish`/`interrupted` prints to stderr and exits 0.
- Produces `<INFOHUB_OPS_STATUS_DIR>/<job>.request.json`: `{"schema_version":1,"job","request_id","requested_at","state","started_at","finished_at","exit_code","reason"}`. Task 4 reads this file.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_ops_request.py`:

```python
"""Host side of admin manual runs: request validation and request status files."""
import importlib.util
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("ops_request", ROOT / "ops" / "ops_request.py")
ops_request = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ops_request)


@pytest.fixture
def status_dir(tmp_path, monkeypatch):
    out = tmp_path / "ops-status"
    monkeypatch.setenv("INFOHUB_OPS_STATUS_DIR", str(out))
    return out


def _request(directory: Path, job: str, **fields) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    data = {"schema_version": 1, "request_id": str(uuid4()), "job": job,
            "requested_at": "2026-10-13T10:00:00Z", "actor_id": str(uuid4())}
    data.update(fields)
    path = directory / f"{job}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _status(status_dir: Path, job: str) -> dict:
    return json.loads((status_dir / f"{job}.request.json").read_text(encoding="utf-8"))


def test_check_prints_the_request_id(tmp_path, capsys):
    path = _request(tmp_path, "canary", request_id="7A1C0D3E-1111-4222-8333-944455556666")
    assert ops_request.main(["x", "check", str(path)]) == 0
    assert capsys.readouterr().out.strip() == "7a1c0d3e-1111-4222-8333-944455556666"


@pytest.mark.parametrize("fields", [
    {"request_id": "not-a-uuid"}, {"request_id": None}, {"request_id": 5},
    {"schema_version": 2}, {"job": "backup"},
])
def test_check_rejects_bad_requests(tmp_path, fields):
    assert ops_request.main(["x", "check", str(_request(tmp_path, "canary", **fields))]) == 1


def test_check_rejects_unknown_names_garbage_and_large_files(tmp_path):
    assert ops_request.main(["x", "check", str(_request(tmp_path, "restore_drill"))]) == 1
    junk = tmp_path / "backup.json"
    junk.write_text("{not json", encoding="utf-8")
    assert ops_request.main(["x", "check", str(junk)]) == 1
    big = _request(tmp_path, "scraper_full", padding="x" * 5000)
    assert ops_request.main(["x", "check", str(big)]) == 1


@pytest.mark.skipif(not hasattr(os, "symlink") or os.name == "nt", reason="symlinks need POSIX")
def test_check_rejects_a_symlink(tmp_path):
    real = _request(tmp_path / "real", "canary")
    link = tmp_path / "canary.json"
    link.symlink_to(real)
    assert ops_request.main(["x", "check", str(link)]) == 1


def test_running_then_done(tmp_path, status_dir):
    path = _request(tmp_path, "scraper_full")
    request_id = json.loads(path.read_text(encoding="utf-8"))["request_id"]
    assert ops_request.main(["x", "running", str(path), "2026-10-13T10:01:00Z"]) == 0
    running = _status(status_dir, "scraper_full")
    assert running["state"] == "running" and running["request_id"] == request_id
    assert running["requested_at"] == "2026-10-13T10:00:00Z" and running["finished_at"] is None
    output = tmp_path / "out.log"
    output.write_text("+3 new docs\n", encoding="utf-8")
    assert ops_request.main(["x", "finish", str(path), "2026-10-13T10:01:00Z", "0", str(output)]) == 0
    done = _status(status_dir, "scraper_full")
    assert done["state"] == "done" and done["exit_code"] == 0 and done["reason"] is None
    assert done["started_at"] == "2026-10-13T10:01:00Z" and done["finished_at"]


def test_nonzero_exit_is_failed(tmp_path, status_dir):
    path = _request(tmp_path, "canary")
    output = tmp_path / "out.log"
    output.write_text("CANARY: 7/10\n", encoding="utf-8")
    ops_request.main(["x", "finish", str(path), "2026-10-13T10:01:00Z", "1", str(output)])
    assert _status(status_dir, "canary")["state"] == "failed"
    assert _status(status_dir, "canary")["exit_code"] == 1


def test_busy_scraper_output_is_skipped(tmp_path, status_dir):
    path = _request(tmp_path, "scraper_ingest")
    output = tmp_path / "out.log"
    output.write_text("[ingestion] Another scraper run is active; this invocation is skipped.\n", encoding="utf-8")
    ops_request.main(["x", "finish", str(path), "2026-10-13T10:01:00Z", "0", str(output)])
    status = _status(status_dir, "scraper_ingest")
    assert status["state"] == "skipped" and status["reason"] == "busy"


def test_skipped_job_status_since_start_is_skipped(tmp_path, status_dir):
    status_dir.mkdir(parents=True)
    (status_dir / "backup.json").write_text(json.dumps(
        {"schema_version": 1, "job": "backup", "skipped": True, "exit_code": 0,
         "finished_at": "2026-10-13T10:01:05Z"}), encoding="utf-8")
    path = _request(tmp_path, "backup")
    output = tmp_path / "out.log"
    output.write_text("", encoding="utf-8")
    ops_request.main(["x", "finish", str(path), "2026-10-13T10:01:00Z", "0", str(output)])
    assert _status(status_dir, "backup")["state"] == "skipped"
    # an older skip (before this run started) does not count
    ops_request.main(["x", "finish", str(path), "2026-10-13T10:02:00Z", "0", str(output)])
    assert _status(status_dir, "backup")["state"] == "done"


def test_interrupted(tmp_path, status_dir):
    path = _request(tmp_path, "backup")
    assert ops_request.main(["x", "interrupted", str(path)]) == 0
    status = _status(status_dir, "backup")
    assert status["state"] == "failed" and status["reason"] == "interrupted" and status["finished_at"]


def test_bad_usage_and_unreadable_request(tmp_path, status_dir):
    assert ops_request.main(["x"]) == 2
    assert ops_request.main(["x", "launch", str(tmp_path / "canary.json")]) == 2
    assert ops_request.main(["x", "running", str(tmp_path / "canary.json"), "t"]) == 1
    assert not status_dir.exists()


def test_write_failure_never_fails_the_dispatcher(tmp_path, monkeypatch, capsys):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("INFOHUB_OPS_STATUS_DIR", str(blocker / "sub"))
    path = _request(tmp_path, "canary")
    assert ops_request.main(["x", "interrupted", str(path)]) == 0
    assert "could not write" in capsys.readouterr().err
```

- [ ] **Step 2: Run and confirm failure**

Run: `rtk python -m pytest tests/test_ops_request.py -q`
Expected: collection error, because `ops/ops_request.py` does not exist.

- [ ] **Step 3: Implement `ops/ops_request.py`**

```python
#!/usr/bin/env python3
"""Host side of admin manual runs (ops/ops-dispatcher.sh calls this).

  ops_request.py check FILE
      Exit 0 and print the request_id when FILE is a regular file under 4 KiB
      holding a schema-1 request for the job its name says, with a UUID
      request_id; otherwise exit 1. Nothing from the file ever reaches a
      command line: the dispatcher chooses the command by the file name.
  ops_request.py running FILE STARTED_AT
  ops_request.py finish FILE STARTED_AT EXIT_CODE OUTPUT_FILE
  ops_request.py interrupted FILE
      Replace <status dir>/<job>.request.json atomically, so the backend
      (read-only mount) never reads a half-written status.

Env: INFOHUB_OPS_STATUS_DIR (default: <repo>/ops-status).
A status write error is reported on stderr and never fails the dispatcher.
"""
from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

JOBS = ("scraper_ingest", "scraper_full", "canary", "backup")
STATUS_JOB = {"scraper_ingest": "scraper", "scraper_full": "scraper", "canary": "canary", "backup": "backup"}
MAX_BYTES = 4096
OUTPUT_BYTES = 65536
SKIP_MARKERS = ("Another scraper run is active",)
DEFAULT_DIR = Path(__file__).resolve().parents[1] / "ops-status"
USAGE = ("usage: ops_request.py check FILE | running FILE STARTED_AT | "
         "finish FILE STARTED_AT EXIT_CODE OUTPUT_FILE | interrupted FILE")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _status_dir() -> Path:
    return Path(os.environ.get("INFOHUB_OPS_STATUS_DIR") or DEFAULT_DIR)


def read_request(path: Path) -> dict | None:
    job = path.stem if path.suffix == ".json" and path.stem in JOBS else None
    if job is None:
        return None
    try:
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("schema_version") != 1 or data.get("job") != job:
        return None
    try:
        request_id = str(uuid.UUID(str(data.get("request_id"))))
    except ValueError:
        return None
    requested_at = data.get("requested_at")
    return {"job": job, "request_id": request_id,
            "requested_at": requested_at if isinstance(requested_at, str) else None}


def write_status(request: dict, **fields) -> None:
    payload = {"schema_version": 1, "job": request["job"], "request_id": request["request_id"],
               "requested_at": request["requested_at"], "state": None, "started_at": None,
               "finished_at": None, "exit_code": None, "reason": None}
    payload.update(fields)
    directory = _status_dir()
    directory.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=f".{request['job']}.request.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.chmod(tmp, 0o644)
        os.replace(tmp, directory / f"{request['job']}.request.json")
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _output(path: str) -> str:
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - OUTPUT_BYTES))
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""


def _skipped_since(job: str, started_at: str) -> bool:
    """The job's own status file says it skipped on a busy lock during this run."""
    try:
        data = json.loads((_status_dir() / f"{STATUS_JOB[job]}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    finished = data.get("finished_at") if isinstance(data, dict) else None
    return data.get("skipped") is True and isinstance(finished, str) and finished >= started_at


def outcome(job: str, exit_code: int, output: str, started_at: str) -> tuple:
    if any(marker in output for marker in SKIP_MARKERS) or _skipped_since(job, started_at):
        return "skipped", "busy"
    return ("done", None) if exit_code == 0 else ("failed", None)


def main(argv: list) -> int:
    arity = {"check": 3, "running": 4, "finish": 6, "interrupted": 3}
    if len(argv) < 2 or arity.get(argv[1]) != len(argv):
        print(USAGE, file=sys.stderr)
        return 2
    command = argv[1]
    request = read_request(Path(argv[2]))
    if request is None:
        return 1
    if command == "check":
        print(request["request_id"])
        return 0
    try:
        if command == "running":
            write_status(request, state="running", started_at=argv[3])
        elif command == "finish":
            try:
                code = int(argv[4])
            except ValueError:
                code = -1
            state, reason = outcome(request["job"], code, _output(argv[5]), argv[3])
            write_status(request, state=state, started_at=argv[3], finished_at=_now(),
                         exit_code=code, reason=reason)
        else:
            write_status(request, state="failed", finished_at=_now(), reason="interrupted")
    except OSError as exc:
        print(f"[ops-request] could not write {request['job']} request status: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

- [ ] **Step 4: Add `tests/test_ops_request.py` to the backend pytest list in `ci.yml`**, after `tests/test_ops_run_canary.py`.

- [ ] **Step 5: Run the tests**

Run: `rtk python -m pytest tests/test_ops_request.py tests/test_ops_job_status.py -q`
Expected: all pass. The symlink test is skipped on Windows.

- [ ] **Step 6: Commit**

```bash
rtk git add ops/ops_request.py backend/tests/test_ops_request.py .github/workflows/ci.yml
rtk git commit -m "feat(ops): host helper validating manual-run requests and writing their status

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Dispatcher, cron, mount and deploy

**Files:**
- Create: `ops/ops-dispatcher.sh`, `ops/cron-infohub-ops-dispatcher`
- Modify:
  - `scripts/deploy_production.sh` (after `install -d -m 0755 ops-status` and the cron installs)
  - `docker-compose.yml` (backend volumes, next to the `./ops-status` line)
  - `.gitignore` (next to `ops-status/`)
  - `ops/logrotate-infohub` (first line)
  - `.github/workflows/ci.yml` (`bash -n` list + backend pytest list)
- Test: `backend/tests/test_ops_dispatcher.py`

**Interfaces:**
- Consumes: the `ops_request.py` CLI from Task 2, `ops/run_canary.sh` from Task 1, `INFOHUB_JOB_TRIGGER` / `INFOHUB_MANUAL_RUN` from Task 1.
- Produces: the queue layout `ops-requests/<job>.json` (waiting), `ops-requests/processing/<job>.json` (taken) and `ops-requests/rejected/` (refused). Task 4 reads the first two.
- Env overrides (tests): `INFOHUB_OPS_REQUEST_DIR`, `INFOHUB_OPS_STATUS_DIR`, `INFOHUB_OPS_DISPATCHER_LOCK`, `INFOHUB_DISPATCH_SCRAPER`, `INFOHUB_DISPATCH_CANARY`, `INFOHUB_DISPATCH_BACKUP`, `INFOHUB_OPS_INTERRUPTED_AFTER_MIN` (default 360).

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_ops_dispatcher.py`:

```python
"""ops/ops-dispatcher.sh: manual-run requests from the admin panel, run on the host."""
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import pytest

fcntl = pytest.importorskip("fcntl")  # POSIX only

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("flock") is None,
    reason="requires bash and flock (Linux CI / production host)",
)

ROOT = Path(__file__).resolve().parents[2]
DISPATCHER = ROOT / "ops" / "ops-dispatcher.sh"
STUB = ('echo "{name} $* trigger=${{INFOHUB_JOB_TRIGGER:-}} manual=${{INFOHUB_MANUAL_RUN:-0}}" >> "$CALLS"\n'
        "{extra}exit ${{STUB_EXIT:-0}}\n")


def _stub(tmp_path: Path, name: str, extra: str = "") -> Path:
    path = tmp_path / "bin" / f"{name}.sh"
    path.parent.mkdir(exist_ok=True)
    path.write_text(STUB.format(name=name, extra=extra), encoding="utf-8", newline="\n")
    return path


def _request(tmp_path: Path, job: str, request_id: str | None = None, age_s: int = 0) -> Path:
    directory = tmp_path / "ops-requests"
    directory.mkdir(exist_ok=True)
    path = directory / f"{job}.json"
    path.write_text(json.dumps({"schema_version": 1, "request_id": request_id or str(uuid4()), "job": job,
                                "requested_at": "2026-10-13T10:00:00Z", "actor_id": str(uuid4())}),
                    encoding="utf-8")
    if age_s:
        stamp = time.time() - age_s
        os.utime(path, (stamp, stamp))
    return path


def _dispatch(tmp_path: Path, stub_exit: int = 0, scraper_extra: str = "", backup_extra: str = "",
              env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ,
           "INFOHUB_OPS_REQUEST_DIR": str(tmp_path / "ops-requests"),
           "INFOHUB_OPS_STATUS_DIR": str(tmp_path / "ops-status"),
           "INFOHUB_OPS_DISPATCHER_LOCK": str(tmp_path / "dispatcher.lock"),
           "INFOHUB_DISPATCH_SCRAPER": str(_stub(tmp_path, "scraper", scraper_extra)),
           "INFOHUB_DISPATCH_CANARY": str(_stub(tmp_path, "canary")),
           "INFOHUB_DISPATCH_BACKUP": str(_stub(tmp_path, "backup", backup_extra)),
           "CALLS": str(tmp_path / "calls.log"),
           "STUB_EXIT": str(stub_exit)}
    for key in ("INFOHUB_JOB_TRIGGER", "INFOHUB_MANUAL_RUN"):
        env.pop(key, None)
    env.update(env_extra or {})
    return subprocess.run(["bash", str(DISPATCHER)], env=env, capture_output=True, text=True)


def _calls(tmp_path: Path) -> list:
    log = tmp_path / "calls.log"
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def _state(tmp_path: Path, job: str) -> dict:
    return json.loads((tmp_path / "ops-status" / f"{job}.request.json").read_text(encoding="utf-8"))


def _queue_empty(tmp_path: Path) -> bool:
    root = tmp_path / "ops-requests"
    return not [p for p in root.iterdir() if p.is_file()] and not list((root / "processing").iterdir())


def test_full_run_is_manual_and_done(tmp_path):
    request_id = str(uuid4())
    _request(tmp_path, "scraper_full", request_id)
    result = _dispatch(tmp_path)
    assert result.returncode == 0, result.stderr
    assert _calls(tmp_path) == ["scraper  trigger=manual manual=1"]
    state = _state(tmp_path, "scraper_full")
    assert state["state"] == "done" and state["exit_code"] == 0 and state["request_id"] == request_id
    assert _queue_empty(tmp_path)


def test_each_job_maps_to_its_fixed_command(tmp_path):
    _request(tmp_path, "scraper_ingest", age_s=30)
    _request(tmp_path, "canary", age_s=20)
    _request(tmp_path, "backup", age_s=10)
    _dispatch(tmp_path)
    assert _calls(tmp_path) == ["scraper --ingest-only trigger=manual manual=0",
                                "canary  trigger=manual manual=0",
                                "backup  trigger=manual manual=0"]


def test_failure_is_failed_with_the_exit_code(tmp_path):
    _request(tmp_path, "canary")
    _dispatch(tmp_path, stub_exit=3)
    state = _state(tmp_path, "canary")
    assert state["state"] == "failed" and state["exit_code"] == 3


def test_busy_scraper_is_skipped(tmp_path):
    _request(tmp_path, "scraper_full")
    _dispatch(tmp_path, scraper_extra='echo "[ingestion] Another scraper run is active; this invocation is skipped."\n')
    state = _state(tmp_path, "scraper_full")
    assert state["state"] == "skipped" and state["reason"] == "busy"


def test_backup_skipped_on_its_own_lock_is_skipped(tmp_path):
    _request(tmp_path, "backup")
    write = ('mkdir -p "$INFOHUB_OPS_STATUS_DIR"; printf \'{"schema_version":1,"job":"backup","skipped":true,'
             '"exit_code":0,"finished_at":"%s"}\' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" '
             '> "$INFOHUB_OPS_STATUS_DIR/backup.json"\n')
    _dispatch(tmp_path, backup_extra=write)
    assert _state(tmp_path, "backup")["state"] == "skipped"


def test_unknown_names_and_invalid_requests_are_rejected_without_running(tmp_path):
    _request(tmp_path, "restore_drill")
    _request(tmp_path, "canary", request_id="not-a-uuid")
    _dispatch(tmp_path)
    assert _calls(tmp_path) == []
    rejected = sorted(p.name for p in (tmp_path / "ops-requests" / "rejected").iterdir())
    assert rejected == ["canary.json", "restore_drill.json"]
    assert not (tmp_path / "ops-status" / "canary.request.json").exists()


def test_symlinked_request_is_rejected(tmp_path):
    real = tmp_path / "elsewhere.json"
    real.write_text(json.dumps({"schema_version": 1, "request_id": str(uuid4()), "job": "backup"}),
                    encoding="utf-8")
    (tmp_path / "ops-requests").mkdir()
    (tmp_path / "ops-requests" / "backup.json").symlink_to(real)
    _dispatch(tmp_path)
    assert _calls(tmp_path) == []
    assert (tmp_path / "ops-requests" / "rejected" / "backup.json").is_symlink()


def test_hidden_temp_files_are_left_for_the_writer(tmp_path):
    (tmp_path / "ops-requests").mkdir()
    temp = tmp_path / "ops-requests" / ".canary.abc.tmp"
    temp.write_text("{", encoding="utf-8")
    _dispatch(tmp_path)
    assert temp.exists() and _calls(tmp_path) == []


def test_stuck_processing_becomes_interrupted(tmp_path):
    processing = tmp_path / "ops-requests" / "processing"
    processing.mkdir(parents=True)
    stuck = _request(tmp_path, "backup", age_s=7 * 3600)
    stuck.rename(processing / "backup.json")
    fresh = _request(tmp_path, "canary")
    fresh.rename(processing / "canary.json")
    _dispatch(tmp_path)
    state = _state(tmp_path, "backup")
    assert state["state"] == "failed" and state["reason"] == "interrupted"
    assert not (processing / "backup.json").exists()
    assert (processing / "canary.json").exists()       # younger than 6 h: left alone


def test_busy_dispatcher_leaves_requests_waiting(tmp_path):
    request = _request(tmp_path, "canary")
    lock = tmp_path / "dispatcher.lock"
    with open(lock, "w") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        result = _dispatch(tmp_path)
    assert result.returncode == 0 and request.exists() and _calls(tmp_path) == []


def test_missing_request_dir_is_a_quiet_no_op(tmp_path):
    result = _dispatch(tmp_path)
    assert result.returncode == 0 and _calls(tmp_path) == []


def test_deploy_and_compose_wire_the_queue():
    deploy = (ROOT / "scripts" / "deploy_production.sh").read_text(encoding="utf-8")
    assert "install -d -m 0770 ops-requests" in deploy
    assert "install -m 0644 ops/cron-infohub-ops-dispatcher /etc/cron.d/infohub-ops-dispatcher" in deploy
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "./ops-requests:/app/ops-requests" in compose
    assert "./ops-requests:/app/ops-requests:ro" not in compose
    cron = (ROOT / "ops" / "cron-infohub-ops-dispatcher").read_text(encoding="utf-8")
    assert "* * * * * root /bin/bash /root/infohub/ops/ops-dispatcher.sh" in cron
```

- [ ] **Step 2: Run and confirm failure**

Run in CI terms; locally on Windows the module is skipped. Run `rtk python -m pytest tests/test_ops_dispatcher.py -q`.
Expected: SKIPPED on Windows. On Linux, everything fails because the dispatcher does not exist. Spend no further time on local runs; Step 8 relies on CI. If WSL or a Linux container is handy, run it there:
`docker run --rm -v "$(pwd -W):/w" -w /w/backend python:3.11-slim sh -c "apt-get update -qq && apt-get install -y -qq util-linux >/dev/null; pip -q install pytest && python -m pytest tests/test_ops_dispatcher.py tests/test_ops_run_canary.py -q"` (Git Bash: prefix `MSYS_NO_PATHCONV=1`).

- [ ] **Step 3: Implement `ops/ops-dispatcher.sh`** (LF endings)

```bash
#!/usr/bin/env bash

# Runs the manual job requests the admin System page leaves in ops-requests/
# (cron, every minute). One dispatcher at a time: while a job runs, later
# minutes exit at once and the requests wait. Only four fixed commands can
# run; a request chooses one by its file name and nothing from its content
# reaches a command line. Progress goes to ops-status/<job>.request.json.

set -uo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
REQUEST_DIR="${INFOHUB_OPS_REQUEST_DIR:-$ROOT/ops-requests}"
export INFOHUB_OPS_STATUS_DIR="${INFOHUB_OPS_STATUS_DIR:-$ROOT/ops-status}"
LOCK_FILE="${INFOHUB_OPS_DISPATCHER_LOCK:-/run/lock/infohub-ops-dispatcher.lock}"
HELPER="$SCRIPT_DIR/ops_request.py"
SCRAPER_CMD="${INFOHUB_DISPATCH_SCRAPER:-$ROOT/run_scraper.sh}"
CANARY_CMD="${INFOHUB_DISPATCH_CANARY:-$SCRIPT_DIR/run_canary.sh}"
BACKUP_CMD="${INFOHUB_DISPATCH_BACKUP:-$SCRIPT_DIR/backup-infohub-db.sh}"
INTERRUPTED_AFTER_MIN="${INFOHUB_OPS_INTERRUPTED_AFTER_MIN:-360}"

log() { echo "[ops-dispatcher $(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

exec 9>"$LOCK_FILE"
flock -n 9 || exit 0

[ -d "$REQUEST_DIR" ] || exit 0
mkdir -p "$REQUEST_DIR/processing" "$REQUEST_DIR/rejected"

run_job() {
    case "$1" in
        scraper_ingest) INFOHUB_JOB_TRIGGER=manual bash "$SCRAPER_CMD" --ingest-only ;;
        scraper_full) INFOHUB_JOB_TRIGGER=manual INFOHUB_MANUAL_RUN=1 bash "$SCRAPER_CMD" ;;
        canary) INFOHUB_JOB_TRIGGER=manual bash "$CANARY_CMD" ;;
        backup) INFOHUB_JOB_TRIGGER=manual bash "$BACKUP_CMD" ;;
        *) return 2 ;;
    esac
}

# A request still in processing/ after 6 h belongs to a dispatcher that died
# mid-job (deploy, reboot): close it so the card leaves "running".
while IFS= read -r -d '' stuck; do
    python3 "$HELPER" interrupted "$stuck" || true
    rm -f -- "$stuck"
    log "$(basename "$stuck"): interrupted"
done < <(find "$REQUEST_DIR/processing" -maxdepth 1 ! -type d -mmin +"$INTERRUPTED_AFTER_MIN" -print0)

# Oldest first. Dot files are the backend's in-flight temp files.
while IFS= read -r request; do
    [ -n "$request" ] || continue
    name="$(basename "$request")"
    case "$name" in
        scraper_ingest.json|scraper_full.json|canary.json|backup.json) job="${name%.json}" ;;
        *)
            mv -f -- "$request" "$REQUEST_DIR/rejected/"
            log "$name: rejected (not a known job)"
            continue ;;
    esac
    if ! request_id="$(python3 "$HELPER" check "$request")"; then
        mv -f -- "$request" "$REQUEST_DIR/rejected/"
        log "$name: rejected (invalid request)"
        continue
    fi
    taken="$REQUEST_DIR/processing/$name"
    mv -f -- "$request" "$taken"
    touch -- "$taken"
    started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    python3 "$HELPER" running "$taken" "$started_at" || true
    log "$name: running request $request_id"
    output="$(mktemp)"
    run_job "$job" >"$output" 2>&1
    rc=$?
    cat "$output"
    python3 "$HELPER" finish "$taken" "$started_at" "$rc" "$output" || true
    rm -f -- "$output" "$taken"
    log "$name: finished with exit $rc"
done < <(find "$REQUEST_DIR" -maxdepth 1 ! -type d ! -name '.*' -printf '%T@ %p\n' | sort -n | cut -d' ' -f2-)
```

- [ ] **Step 4: Create `ops/cron-infohub-ops-dispatcher`**

```
# Installed to /etc/cron.d/infohub-ops-dispatcher by scripts/deploy_production.sh.
# Every minute: run manual job requests from the admin System page (ops-requests/).
# The dispatcher holds its own lock, so a long job never starts a second copy.
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
* * * * * root /bin/bash /root/infohub/ops/ops-dispatcher.sh >> /root/infohub/logs/ops-dispatcher.log 2>&1
```

- [ ] **Step 5: Wire deploy, compose, gitignore, logrotate, CI**

- `scripts/deploy_production.sh`:
  - after `install -d -m 0755 ops-status`, add `install -d -m 0770 ops-requests`;
  - after the `cron-infohub-restore-drill` install line, add `install -m 0644 ops/cron-infohub-ops-dispatcher /etc/cron.d/infohub-ops-dispatcher`.
- `docker-compose.yml`: in the backend `volumes:`, below `- ./ops-status:/app/ops-status:ro`, add `- ./ops-requests:/app/ops-requests`.
- `.gitignore`: below `ops-status/`, add `ops-requests/`.
- `ops/logrotate-infohub`: add `/root/infohub/logs/ops-dispatcher.log` to the first line's file list.
- `.github/workflows/ci.yml`:
  - add `ops/ops-dispatcher.sh` to the `bash -n` list;
  - add `tests/test_ops_dispatcher.py` to the backend pytest list after `tests/test_ops_request.py`.

- [ ] **Step 6: Syntax check**

Run: `bash -n ops/ops-dispatcher.sh && echo ok`, then `rtk git diff --stat`.
Expected: `ok`.

- [ ] **Step 7: Make sure LF endings are committed**

Run: `rtk git add ops/ops-dispatcher.sh ops/run_canary.sh && git ls-files --eol ops/ops-dispatcher.sh ops/run_canary.sh`
Expected: `i/lf` for both. If `i/crlf` appears, rewrite the files with LF and re-add.

- [ ] **Step 8: Commit**

```bash
rtk git add ops/ops-dispatcher.sh ops/cron-infohub-ops-dispatcher scripts/deploy_production.sh docker-compose.yml .gitignore ops/logrotate-infohub .github/workflows/ci.yml backend/tests/test_ops_dispatcher.py
rtk git commit -m "feat(ops): cron dispatcher for admin manual runs with a fixed command map

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

The dispatcher tests run first in CI (Task 6 pushes). Any failure there goes back to this task.

---

### Task 4: Backend — request endpoint and request state on the System page

**Files:**
- Modify: `backend/core/admin_system.py` (public `naive_utc`, `load_status`; request reading; `system_status(..., request_dir=None)`)
- Create: `backend/core/admin_ops_requests.py`
- Modify: `backend/api/routes/admin_system.py`
- Modify: `backend/core/admin_audit.py` (`ADMIN_ACTIONS` += `"ops.job_requested"`, `TARGET_TYPES` += `"ops_job"`)
- Modify: `.github/workflows/ci.yml` (backend pytest list)
- Test: `backend/tests/test_admin_system.py` (append), create `backend/tests/test_admin_ops_requests.py`

**Interfaces:**
- Consumes: the `<job>.request.json` format from Task 2 and the queue layout from Task 3.
- Produces for the frontend:
  - `GET /api/v1/admin/system`: every job entry gains `"request": null | {job, state, request_id, requested_at, started_at, finished_at, exit_code, reason}`. The scraper card shows `scraper_ingest`/`scraper_full`, canary shows `canary`, backup shows `backup`, and restore_drill is always `null`.
  - `POST /api/v1/admin/system/jobs/{job}` returns 202 `{"request_id","job","state":"queued"}`.
  - Errors: 409 `{"detail":{"code","message"}}` with the four codes, 422 for an unknown job, and 500 `{"detail":{"code":"ops_queue_unavailable",...}}` if the folder is not writable.

- [ ] **Step 1: Append failing tests to `backend/tests/test_admin_system.py`**

```python
def _request_status(directory, job, **fields):
    data = {"schema_version": 1, "job": job, "request_id": "r-" + job, "requested_at": "2026-10-12T09:00:00Z",
            "state": "done", "started_at": "2026-10-12T09:00:30Z", "finished_at": "2026-10-12T09:05:00Z",
            "exit_code": 0, "reason": None}
    data.update(fields)
    (directory / f"{job}.request.json").write_text(json.dumps(data), encoding="utf-8")


def _cards(status_dir, request_dir=None):
    return {j["job"]: j["request"] for j in system_status(status_dir, NOW, request_dir)["jobs"]}


def test_no_requests_anywhere(tmp_path):
    assert set(_cards(tmp_path, tmp_path / "requests").values()) == {None}
    assert set(_cards(tmp_path).values()) == {None}


def test_waiting_file_is_queued_on_the_scraper_card(tmp_path):
    requests = tmp_path / "requests"
    requests.mkdir()
    (requests / "scraper_full.json").write_text(json.dumps(
        {"schema_version": 1, "request_id": "abc", "job": "scraper_full", "requested_at": "2026-10-12T09:59:00Z"}),
        encoding="utf-8")
    request = _cards(tmp_path, requests)["scraper"]
    assert request["job"] == "scraper_full" and request["state"] == "queued"
    assert request["request_id"] == "abc" and request["requested_at"] == "2026-10-12T09:59:00Z"


def test_finished_request_passes_through(tmp_path):
    _request_status(tmp_path, "canary", state="failed", exit_code=1)
    request = _cards(tmp_path, tmp_path / "requests")["canary"]
    assert request["state"] == "failed" and request["exit_code"] == 1 and request["job"] == "canary"


def test_active_request_wins_over_a_newer_finished_one(tmp_path):
    _request_status(tmp_path, "scraper_ingest", state="running", requested_at="2026-10-12T09:00:00Z",
                    finished_at=None, exit_code=None)
    _request_status(tmp_path, "scraper_full", requested_at="2026-10-12T09:30:00Z")
    assert _cards(tmp_path)["scraper"]["job"] == "scraper_ingest"
    _request_status(tmp_path, "scraper_ingest", requested_at="2026-10-12T09:00:00Z")
    assert _cards(tmp_path)["scraper"]["job"] == "scraper_full"


def test_taken_file_with_an_old_status_reads_as_running(tmp_path):
    _request_status(tmp_path, "backup")                      # previous run: done
    processing = tmp_path / "requests" / "processing"
    processing.mkdir(parents=True)
    (processing / "backup.json").write_text(json.dumps({"request_id": "new"}), encoding="utf-8")
    request = _cards(tmp_path, tmp_path / "requests")["backup"]
    assert request["state"] == "running" and request["request_id"] == "new"


def test_bad_request_status_is_ignored(tmp_path):
    _request_status(tmp_path, "canary", state="exploded")
    _request_status(tmp_path, "backup", job="canary")
    (tmp_path / "scraper_full.request.json").write_text("{", encoding="utf-8")
    cards = _cards(tmp_path)
    assert cards["canary"] is None and cards["backup"] is None and cards["scraper"] is None
    assert cards["restore_drill"] is None
```

- [ ] **Step 2: Create failing `backend/tests/test_admin_ops_requests.py`**

```python
"""Admin manual runs: guards, the request file and its journal row (no database: fake session)."""
import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.routes.admin_system import router
from core.admin_ops_requests import request_job
from core.database import get_db
from core.security import require_admin

NOW = datetime(2026, 10, 13, 10, 0)  # naive UTC
ADMIN = SimpleNamespace(id=uuid4())


class FakeDb:
    def __init__(self, fail_commit=False):
        self.added, self.commits, self.rollbacks, self.fail_commit = [], 0, 0, fail_commit

    def add(self, row):
        self.added.append(row)

    def flush(self):
        pass

    def commit(self):
        if self.fail_commit:
            raise RuntimeError("commit failed")
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


@pytest.fixture
def dirs(tmp_path):
    status, requests = tmp_path / "status", tmp_path / "requests"
    status.mkdir()
    requests.mkdir()
    return status, requests


def _run(dirs, job, db=None):
    status, requests = dirs
    return request_job(db or FakeDb(), actor=ADMIN, job=job, status_dir=status, request_dir=requests, now=NOW)


def _code(dirs, job):
    with pytest.raises(HTTPException) as caught:
        _run(dirs, job)
    assert caught.value.status_code == 409
    return caught.value.detail["code"]


def _job_status(dirs, job, finished_at, exit_code=0, skipped=False):
    (dirs[0] / f"{job}.json").write_text(json.dumps(
        {"schema_version": 1, "job": job, "finished_at": finished_at, "exit_code": exit_code,
         "skipped": skipped}), encoding="utf-8")


def test_request_writes_the_file_and_the_journal_row(dirs):
    db = FakeDb()
    result = _run(dirs, "scraper_full", db)
    assert result["job"] == "scraper_full" and result["state"] == "queued"
    data = json.loads((dirs[1] / "scraper_full.json").read_text(encoding="utf-8"))
    assert data == {"schema_version": 1, "request_id": result["request_id"], "job": "scraper_full",
                    "requested_at": "2026-10-13T10:00:00Z", "actor_id": str(ADMIN.id)}
    UUID(result["request_id"])
    [row] = db.added
    assert (row.action, row.target_type, row.target_id) == ("ops.job_requested", "ops_job", "scraper_full")
    assert row.after == {"request_id": result["request_id"]} and db.commits == 1
    assert [p.name for p in dirs[1].iterdir()] == ["scraper_full.json"]   # no temp files left


def test_second_request_is_already_pending(dirs):
    _run(dirs, "canary")
    assert _code(dirs, "canary") == "already_pending"


def test_running_request_is_already_pending(dirs):
    (dirs[0] / "backup.request.json").write_text(json.dumps(
        {"schema_version": 1, "job": "backup", "state": "running", "request_id": "x"}), encoding="utf-8")
    assert _code(dirs, "backup") == "already_pending"


def test_other_scraper_job_active_is_scraper_busy(dirs):
    _run(dirs, "scraper_ingest")
    assert _code(dirs, "scraper_full") == "scraper_busy"
    assert not (dirs[1] / "scraper_full.json").exists()


@pytest.mark.parametrize("finished_at, exit_code, skipped, blocked", [
    ("2026-10-13T05:00:00Z", 0, False, True),    # 5 h ago, ok
    ("2026-10-13T04:00:00Z", 0, False, False),   # exactly 6 h
    ("2026-10-13T09:00:00Z", 1, False, False),   # failed: retry allowed
    ("2026-10-13T09:00:00Z", 0, True, False),    # skipped: nothing was dumped
])
def test_backup_guard(dirs, finished_at, exit_code, skipped, blocked):
    _job_status(dirs, "backup", finished_at, exit_code, skipped)
    if blocked:
        assert _code(dirs, "backup") == "backup_too_recent"
    else:
        assert _run(dirs, "backup")["state"] == "queued"


@pytest.mark.parametrize("finished_at, exit_code, blocked", [
    ("2026-10-13T09:51:00Z", 0, True),
    ("2026-10-13T09:51:00Z", 1, True),            # any outcome counts: each run costs LLM calls
    ("2026-10-13T09:50:00Z", 0, False),           # exactly 10 min
])
def test_canary_guard(dirs, finished_at, exit_code, blocked):
    _job_status(dirs, "canary", finished_at, exit_code)
    if blocked:
        assert _code(dirs, "canary") == "canary_too_recent"
    else:
        assert _run(dirs, "canary")["state"] == "queued"


def test_commit_failure_removes_the_request_file(dirs):
    with pytest.raises(RuntimeError):
        _run(dirs, "canary", FakeDb(fail_commit=True))
    assert list(dirs[1].iterdir()) == []


def test_unwritable_folder_is_a_coded_500_and_no_commit(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    db = FakeDb()
    with pytest.raises(HTTPException) as caught:
        request_job(db, actor=ADMIN, job="canary", status_dir=tmp_path, request_dir=blocker / "sub", now=NOW)
    assert caught.value.status_code == 500 and caught.value.detail["code"] == "ops_queue_unavailable"
    assert db.commits == 0 and db.rollbacks == 1


@pytest.fixture
def client(dirs, monkeypatch):
    monkeypatch.setenv("ADMIN_OPS_STATUS_DIR", str(dirs[0]))
    monkeypatch.setenv("ADMIN_OPS_REQUEST_DIR", str(dirs[1]))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: ADMIN
    app.dependency_overrides[get_db] = lambda: FakeDb()
    return TestClient(app)


def test_endpoint_accepts_only_whitelisted_jobs(client, dirs):
    assert client.post("/admin/system/jobs/restore_drill").status_code == 422
    assert client.post("/admin/system/jobs/rm%20-rf").status_code == 422
    response = client.post("/admin/system/jobs/backup")
    assert response.status_code == 202 and response.json()["state"] == "queued"
    conflict = client.post("/admin/system/jobs/backup")
    assert conflict.status_code == 409 and conflict.json()["detail"]["code"] == "already_pending"
    system = client.get("/admin/system").json()
    backup = next(j for j in system["jobs"] if j["job"] == "backup")
    assert backup["request"]["state"] == "queued"


def test_endpoint_needs_an_admin(dirs, monkeypatch):
    monkeypatch.setenv("ADMIN_OPS_REQUEST_DIR", str(dirs[1]))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: FakeDb()
    assert TestClient(app).post("/admin/system/jobs/canary").status_code in (401, 403)
    assert list(dirs[1].iterdir()) == []
```

- [ ] **Step 3: Run and confirm failure**

Run: `rtk python -m pytest tests/test_admin_system.py tests/test_admin_ops_requests.py -q`
Expected: the new system tests fail because `system_status()` takes 2 positional args, and `test_admin_ops_requests.py` errors on import because `core.admin_ops_requests` is missing.

- [ ] **Step 4: Extend `backend/core/admin_system.py`**

- Rename `_naive_utc` → `naive_utc` and `_load` → `load_status`, and update their internal uses.
- Extend the module docstring with: `Manual-run requests (stage 5b) are read from ops-status/<job>.request.json (written by the host dispatcher) and from ops-requests/ (files still waiting or taken).`
- Add after `MAX_BYTES`:

```python
MANUAL_JOBS = ("scraper_ingest", "scraper_full", "canary", "backup")
CARD_REQUESTS = {"scraper": ("scraper_ingest", "scraper_full"), "canary": ("canary",),
                 "backup": ("backup",), "restore_drill": ()}
REQUEST_STATES = ("queued", "running", "done", "skipped", "failed")
ACTIVE_STATES = ("queued", "running")
```

- Add before `system_status`:

```python
def _read_json(path: Path) -> dict | None:
    try:
        if path.stat().st_size > MAX_BYTES:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _request(job: str, state: str, data: dict | None) -> dict:
    exit_code = data.get("exit_code") if data else None
    return {"job": job, "state": state, "request_id": _text(data, "request_id"),
            "requested_at": _text(data, "requested_at"), "started_at": _text(data, "started_at"),
            "finished_at": _text(data, "finished_at"),
            "exit_code": exit_code if type(exit_code) is int else None, "reason": _text(data, "reason")}


def request_status(status_dir: Path, request_dir: Path | None, job: str) -> dict | None:
    """Latest manual request for one job. A file still waiting in ops-requests/ is
    "queued"; a file the dispatcher took is "running" until its status says so."""
    if request_dir is not None and (request_dir / f"{job}.json").exists():
        return _request(job, "queued", _read_json(request_dir / f"{job}.json"))
    data = _read_json(status_dir / f"{job}.request.json")
    if data is None or data.get("schema_version") != 1 or data.get("job") != job \
            or data.get("state") not in REQUEST_STATES:
        data = None
    taken = request_dir / "processing" / f"{job}.json" if request_dir is not None else None
    if taken is not None and taken.exists() and (data is None or data["state"] not in ACTIVE_STATES):
        return _request(job, "running", _read_json(taken))
    return _request(job, data["state"], data) if data else None


def card_request(status_dir: Path, request_dir: Path | None, card: str) -> dict | None:
    found = [r for r in (request_status(status_dir, request_dir, job) for job in CARD_REQUESTS[card]) if r]
    active = [r for r in found if r["state"] in ACTIVE_STATES]
    pool = active or found
    return max(pool, key=lambda r: r["requested_at"] or "") if pool else None
```

- Change `_entry(job, data, now)` to `_entry(job, data, now, request)` and add `"request": request,` as the last key.
- Change `system_status`:

```python
def system_status(directory: Path, now: datetime, request_dir: Path | None = None) -> dict:
    return {
        "generated_at": now.isoformat(),
        "jobs": [_entry(job, load_status(directory / f"{job}.json", job), now,
                        card_request(directory, request_dir, job)) for job in JOBS],
    }
```

- [ ] **Step 5: Create `backend/core/admin_ops_requests.py`**

```python
"""Admin manual runs (stage 5b): queue a whitelisted host job for ops/ops-dispatcher.sh.

The backend never runs anything itself. It drops ops-requests/<job>.json, which
the host dispatcher picks up within a minute, and journals the request. These
checks stop double clicks and accidents; the host flocks are what really keep
two runs of a job apart.
"""
import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from core.admin_audit import record_admin_action
from core.admin_system import ACTIVE_STATES, load_status, naive_utc, request_status
from core.admin_users import admin_error

BACKUP_MIN_GAP = timedelta(hours=6)
CANARY_MIN_GAP = timedelta(minutes=10)
SCRAPER_JOBS = ("scraper_ingest", "scraper_full")


def _active(status_dir: Path, request_dir: Path, job: str) -> bool:
    request = request_status(status_dir, request_dir, job)
    return request is not None and request["state"] in ACTIVE_STATES


def check_request(job: str, status_dir: Path, request_dir: Path, now: datetime) -> None:
    if _active(status_dir, request_dir, job):
        raise admin_error(409, "already_pending", "This job already has a request waiting or running")
    if job in SCRAPER_JOBS and any(_active(status_dir, request_dir, other) for other in SCRAPER_JOBS if other != job):
        raise admin_error(409, "scraper_busy", "The scraper already has another request waiting or running")
    if job == "backup":
        last = load_status(status_dir / "backup.json", "backup")
        if last and last["exit_code"] == 0 and last.get("skipped") is not True \
                and now - naive_utc(last["finished_at"]) < BACKUP_MIN_GAP:
            raise admin_error(409, "backup_too_recent",
                              f"The last backup finished at {last['finished_at']}; allow 6 hours between backups")
    if job == "canary":
        last = load_status(status_dir / "canary.json", "canary")
        if last and now - naive_utc(last["finished_at"]) < CANARY_MIN_GAP:
            raise admin_error(409, "canary_too_recent", "The canary ran less than 10 minutes ago")


def _write_request(request_dir: Path, payload: dict) -> Path:
    target = request_dir / f"{payload['job']}.json"
    fd, tmp = tempfile.mkstemp(dir=request_dir, prefix=f".{payload['job']}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return target


def request_job(db, *, actor, job: str, status_dir: Path, request_dir: Path, now: datetime) -> dict:
    """Journal row first (flushed, so an insert failure stops us before any file
    exists), then the request file, then the commit. A failed commit removes the
    file again, so the dispatcher never runs a request the journal lacks."""
    check_request(job, status_dir, request_dir, now)
    request_id = str(uuid4())
    record_admin_action(db, actor=actor, action="ops.job_requested", target_type="ops_job",
                        target_id=job, after={"request_id": request_id})
    payload = {"schema_version": 1, "request_id": request_id, "job": job,
               "requested_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "actor_id": str(actor.id)}
    try:
        target = _write_request(request_dir, payload)
    except OSError:
        db.rollback()
        raise admin_error(500, "ops_queue_unavailable", "The ops request folder is not writable") from None
    try:
        db.commit()
    except Exception:
        target.unlink(missing_ok=True)
        db.rollback()
        raise
    return {"request_id": request_id, "job": job, "state": "queued"}
```

- [ ] **Step 6: Update the route `backend/api/routes/admin_system.py`**

```python
"""Admin System page: latest status of host cron jobs and manual runs. Requires the admin role."""
import os
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.admin_ops_requests import request_job
from core.admin_system import system_status
from core.database import get_db
from core.security import require_admin
from core.time_utils import utc_now
from models import User

router = APIRouter(prefix="/admin/system", tags=["Admin"], dependencies=[Depends(require_admin)])

ManualJob = Literal["scraper_ingest", "scraper_full", "canary", "backup"]


def _dirs() -> tuple:
    return (Path(os.environ.get("ADMIN_OPS_STATUS_DIR", "/app/ops-status")),
            Path(os.environ.get("ADMIN_OPS_REQUEST_DIR", "/app/ops-requests")))


@router.get("")
def get_system():
    status_dir, request_dir = _dirs()
    return system_status(status_dir, utc_now(), request_dir)


@router.post("/jobs/{job}", status_code=202, responses={
    409: {"description": "already_pending, scraper_busy, backup_too_recent or canary_too_recent"},
    500: {"description": "ops_queue_unavailable: the request folder is not writable"},
})
def post_job(job: ManualJob, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    status_dir, request_dir = _dirs()
    return request_job(db, actor=admin, job=job, status_dir=status_dir, request_dir=request_dir, now=utc_now())
```

- [ ] **Step 7: Audit constants**

In `backend/core/admin_audit.py`, append `"ops.job_requested"` to `ADMIN_ACTIONS` and `"ops_job"` to `TARGET_TYPES`.

- [ ] **Step 8: CI list**

Add `tests/test_admin_ops_requests.py` after `tests/test_admin_system.py` in the backend pytest list.

- [ ] **Step 9: Run the tests**

Run: `rtk python -m pytest tests/test_admin_system.py tests/test_admin_ops_requests.py tests/test_ops_request.py tests/test_ops_job_status.py tests/test_admin_trends.py -q`, then `rm -f test.db`.
Expected: all pass.

- [ ] **Step 10: Commit**

```bash
rtk git add backend/core/admin_system.py backend/core/admin_ops_requests.py backend/api/routes/admin_system.py backend/core/admin_audit.py backend/tests/test_admin_system.py backend/tests/test_admin_ops_requests.py .github/workflows/ci.yml
rtk git commit -m "feat(admin): journaled manual-run requests and their state on the System page

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Frontend — buttons, confirm dialog, request line, polling

**Files:**
- Modify: `frontend/lib/admin-types.ts`, `frontend/lib/admin-i18n.ts`, `frontend/app/admin/system/page.tsx`, `frontend/app/admin/admin.module.css`

**Interfaces:**
- Consumes: the Task 4 API (`request` on each job; POST 202/409/500 with `detail.code`).
- Produces: card buttons with the accessible names below. Task 6 e2e relies on them, in RU:
  - «Загрузить новые документы», «Полный ночной прогон» (scraper card)
  - «Прогнать канарейку» (canary card)
  - «Бэкап сейчас» (backup card)
- The dialog confirm button is «Запустить». Request lines: «В очереди…», «Выполняется с …», «Ручной запуск завершён в …», «Ручной запуск пропущен…», «Ручной запуск завершился ошибкой», «Ручной запуск прерван».

- [ ] **Step 1: Types — append to `frontend/lib/admin-types.ts`**

```ts
export const MANUAL_JOBS = ['scraper_ingest', 'scraper_full', 'canary', 'backup'] as const;
export type ManualJob = (typeof MANUAL_JOBS)[number];
export type JobRequestState = 'queued' | 'running' | 'done' | 'skipped' | 'failed';
export interface JobRequest {
  job: ManualJob; state: JobRequestState; request_id: string | null; requested_at: string | null;
  started_at: string | null; finished_at: string | null; exit_code: number | null; reason: string | null;
}
/** Which manual runs each System card offers; restore drill is view-only. */
export const CARD_ACTIONS: Record<SystemJobName, readonly ManualJob[]> = {
  scraper: ['scraper_ingest', 'scraper_full'], canary: ['canary'], backup: ['backup'], restore_drill: [],
};
```

Add `request: JobRequest | null;` to `interface SystemJob` (after `log_tail`).

- [ ] **Step 2: Copy — `frontend/lib/admin-i18n.ts`**

- Import `ManualJob` from `./admin-types`.
- Append `'ops.job_requested'` to `ADMIN_ACTIONS`.
- Append `'already_pending', 'scraper_busy', 'backup_too_recent', 'canary_too_recent', 'ops_queue_unavailable'` to `ADMIN_ERROR_CODES`.
- In each language block:
  - **audit:** add the action label and the target label;
  - **errors:** add the five codes;
  - **system:** add `run`, `confirmRun`, `cost`, `request`.

RU:

```ts
// audit.actions
'ops.job_requested': 'Ручной запуск задачи',
// audit.targets
ops_job: 'Задача',
// errors
already_pending: 'Эта задача уже в очереди или выполняется.',
scraper_busy: 'Скрапер уже запущен другой заявкой.',
backup_too_recent: 'Последний бэкап был меньше 6 часов назад.',
canary_too_recent: 'Канарейка запускалась меньше 10 минут назад.',
ops_queue_unavailable: 'Папка заявок недоступна, запуск не поставлен.',
// system
run: {
  scraper_ingest: 'Загрузить новые документы', scraper_full: 'Полный ночной прогон',
  canary: 'Прогнать канарейку', backup: 'Бэкап сейчас',
} satisfies Record<ManualJob, string>,
confirmRun: 'Запустить',
cost: {
  scraper_ingest: 'Скачает новые документы с infohub.rs.ge и добавит их в базу. Обычно несколько минут, без вызовов LLM. Если скрапер уже работает, запуск будет пропущен.',
  scraper_full: 'Весь ночной прогон: загрузка, разбор решений и поправок, переводы, проверки качества и канарейка. Может занять до часа и сделать сотни вызовов gpt-4o-mini. Ночной счётчик «0 новых документов» не изменится.',
  canary: 'Десять контрольных вопросов через настоящий конвейер ответов: около 10 вызовов gpt-4o-mini. Не чаще раза в 10 минут.',
  backup: 'Полный дамп базы. Хранится 4 последних дампа; самый старый будет удалён. Не чаще раза в 6 часов.',
} satisfies Record<ManualJob, string>,
request: {
  queued: 'В очереди: запустится в течение минуты',
  running: (t: string) => `Выполняется с ${t}`,
  done: (t: string) => `Ручной запуск завершён в ${t}`,
  skipped: 'Ручной запуск пропущен: задача уже шла',
  failed: 'Ручной запуск завершился ошибкой',
  interrupted: 'Ручной запуск прерван',
},
```

KA (run the Georgian style skill over these; list the final strings in the report):

```ts
'ops.job_requested': 'ამოცანის ხელით გაშვება',
ops_job: 'ამოცანა',
already_pending: 'ეს ამოცანა უკვე რიგშია ან მიმდინარეობს.',
scraper_busy: 'მონაცემების შეგროვება უკვე გაშვებულია სხვა მოთხოვნით.',
backup_too_recent: 'ბოლო სარეზერვო ასლი 6 საათზე ნაკლები ხნის წინ შეიქმნა.',
canary_too_recent: 'საკონტროლო შემოწმება 10 წუთზე ნაკლები ხნის წინ გაეშვა.',
ops_queue_unavailable: 'მოთხოვნების საქაღალდე მიუწვდომელია, გაშვება არ დაემატა.',
run: {
  scraper_ingest: 'ახალი დოკუმენტების ჩატვირთვა', scraper_full: 'სრული ღამის გაშვება',
  canary: 'საკონტროლო შემოწმების გაშვება', backup: 'სარეზერვო ასლი ახლავე',
},
confirmRun: 'გაშვება',
cost: {
  scraper_ingest: 'ჩამოტვირთავს ახალ დოკუმენტებს infohub.rs.ge-დან და დაამატებს ბაზაში. ჩვეულებრივ რამდენიმე წუთი სჭირდება, LLM არ გამოიყენება. თუ შეგროვება უკვე მიმდინარეობს, გაშვება გამოტოვდება.',
  scraper_full: 'სრული ღამის ციკლი: ჩატვირთვა, გადაწყვეტილებებისა და ცვლილებების დამუშავება, თარგმანები, ხარისხის შემოწმება და საკონტროლო შემოწმება. შეიძლება ერთ საათამდე გაგრძელდეს და gpt-4o-mini-ს ასობით მოთხოვნა დასჭირდეს. ღამის მრიცხველი „0 ახალი დოკუმენტი“ არ შეიცვლება.',
  canary: 'ათი საკონტროლო კითხვა პასუხების რეალურ ჯაჭვში: დაახლოებით 10 მოთხოვნა gpt-4o-mini-ზე. არაუმეტეს 10 წუთში ერთხელ.',
  backup: 'ბაზის სრული ასლი. ინახება ბოლო 4 ასლი; ყველაზე ძველი წაიშლება. არაუმეტეს 6 საათში ერთხელ.',
},
request: {
  queued: 'რიგშია: გაეშვება ერთი წუთის განმავლობაში',
  running: (t: string) => `მიმდინარეობს ${t}-დან`,
  done: (t: string) => `ხელით გაშვება დასრულდა ${t}-ზე`,
  skipped: 'ხელით გაშვება გამოტოვდა: ამოცანა უკვე მიმდინარეობდა',
  failed: 'ხელით გაშვება შეცდომით დასრულდა',
  interrupted: 'ხელით გაშვება შეწყდა',
},
```

EN:

```ts
'ops.job_requested': 'Manual job run',
ops_job: 'Job',
already_pending: 'This job is already queued or running.',
scraper_busy: 'The scraper is already running for another request.',
backup_too_recent: 'The last backup was less than 6 hours ago.',
canary_too_recent: 'The canary ran less than 10 minutes ago.',
ops_queue_unavailable: 'The request folder is unavailable; nothing was queued.',
run: { scraper_ingest: 'Fetch new documents', scraper_full: 'Full nightly run', canary: 'Run canary', backup: 'Back up now' },
confirmRun: 'Run',
cost: {
  scraper_ingest: 'Downloads new documents from infohub.rs.ge into the database. Usually a few minutes, no LLM calls. Skipped if the scraper is already running.',
  scraper_full: 'The whole nightly run: ingest, decision and amendment extraction, translations, quality gates and the canary. Up to an hour and hundreds of gpt-4o-mini calls. The nightly "0 new documents" streak is left unchanged.',
  canary: 'Ten known-answer questions through the real answer pipeline: about 10 gpt-4o-mini calls. At most once every 10 minutes.',
  backup: 'A full database dump. The 4 newest dumps are kept; the oldest is deleted. At most once every 6 hours.',
},
request: {
  queued: 'Queued: starts within a minute',
  running: (t: string) => `Running since ${t}`,
  done: (t: string) => `Manual run finished at ${t}`,
  skipped: 'Manual run skipped: the job was already running',
  failed: 'Manual run failed',
  interrupted: 'Manual run interrupted',
},
```

- [ ] **Step 3: Page — `frontend/app/admin/system/page.tsx`**

- Imports:
  - `useEffect, useState` from `react`;
  - `CARD_ACTIONS, type JobRequest, type ManualJob` from `@/lib/admin-types`;
  - `adminSend, AdminApiError, errorText` from `@/lib/admin-api`;
  - `ConfirmDialog` from `@/components/admin/ConfirmDialog`.
- Add after `age()`:

```tsx
const POLL_MS = 15_000;
const isActive = (r: JobRequest | null) => r !== null && (r.state === 'queued' || r.state === 'running');
const cardOf = (job: ManualJob): SystemJobName => (job === 'canary' || job === 'backup' ? job : 'scraper');

function RequestLine({ request, c, locale }: Readonly<{ request: JobRequest; c: AdminCopy; locale: AdminLocale }>) {
  const at = (value: string | null) => (value ? formatDateTime(value, locale) : '');
  const r = c.system.request;
  const text = request.state === 'queued' ? r.queued
    : request.state === 'running' ? r.running(at(request.started_at))
    : request.state === 'done' ? r.done(at(request.finished_at))
    : request.state === 'skipped' ? r.skipped
    : request.reason === 'interrupted' ? r.interrupted : r.failed;
  return <p className={styles.jobMeta} role="status">{c.system.run[request.job]}: {text}</p>;
}
```

(Import `SystemJobName` with the other types.)

- `JobCard` gains props `onRun: (job: ManualJob) => void` and `error: string | undefined`. Before `<p className={styles.jobMeta}>{c.system.expected[job.job]}</p>`, render:

```tsx
{job.request && <RequestLine request={job.request} c={c} locale={locale} />}
{CARD_ACTIONS[job.job].length > 0 && <div className={styles.jobActions}>
  {CARD_ACTIONS[job.job].map((action) => <button key={action} type="button" className={styles.button}
    disabled={isActive(job.request)} onClick={() => onRun(action)}>{c.system.run[action]}</button>)}
</div>}
{error && <p className={styles.noticeError} role="alert">{error}</p>}
```

- In `AdminSystem`:

```tsx
const [dialog, setDialog] = useState<ManualJob | null>(null);
const [errors, setErrors] = useState<Partial<Record<SystemJobName, string>>>({});
const polling = data?.jobs.some((j) => isActive(j.request)) ?? false;

useEffect(() => {
  if (!polling) return;
  const id = window.setInterval(reload, POLL_MS);
  return () => window.clearInterval(id);
}, [polling, reload]);

const run = async () => {
  if (dialog === null) return;
  const card = cardOf(dialog);
  try {
    await adminSend(`/api/v1/admin/system/jobs/${dialog}`, 'POST', {});
    setErrors((prev) => ({ ...prev, [card]: undefined }));
  } catch (e) {
    // 409 is about the job, not the dialog: close it and say why on the card.
    if (!(e instanceof AdminApiError && e.status === 409)) throw new Error(errorText(c, e));
    setErrors((prev) => ({ ...prev, [card]: errorText(c, e) }));
  }
  reload();
};
```

Pass `onRun={setDialog}` and `error={errors[job.job]}` to each `JobCard`. After the `{body}`, render:

```tsx
<ConfirmDialog open={dialog !== null} onOpenChange={(open) => { if (!open) setDialog(null); }}
  title={dialog ? c.system.run[dialog] : ''} description={dialog ? c.system.cost[dialog] : undefined}
  confirmLabel={c.system.confirmRun} withReason={false} onConfirm={run} />
```

- [ ] **Step 4: CSS — `frontend/app/admin/admin.module.css`**, after `.jobLog[open] summary`:

```css
.jobActions { display: flex; flex-wrap: wrap; gap: 8px; }
```

- [ ] **Step 5: Static checks**

Run (in `frontend/`):
- `rtk npx tsc --noEmit`
- `rtk npm run lint`
- `rtk npm run check:admin-styles`
- `rtk npm run test:admin-styles`

Expected: all clean. `tsc` fails if any language block misses a key (the `satisfies` checks).

The project does not build Next locally (15 min, OOM risk). The e2e run is in Task 6.

- [ ] **Step 6: Commit**

```bash
rtk git add frontend/lib/admin-types.ts frontend/lib/admin-i18n.ts frontend/app/admin/system/page.tsx frontend/app/admin/admin.module.css
rtk git commit -m "feat(admin): manual-run buttons, confirm dialog and request status on System cards

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: e2e, visual baselines, docs

**Files:**
- Modify: `frontend/e2e/admin-system.spec.ts`
- Update baselines: `frontend/e2e/__screenshots__/admin-system-ru-desktop.png`, `admin-system-ka-mobile.png` (buttons now on the cards)
- Modify: `docs/PRODUCTION_OPERATIONS.md`, `docs/DEVELOPMENT_MEMORY.md`, spec (deviation notes)

**Interfaces:**
- Consumes: the button and copy names from Task 5.

- [ ] **Step 1: Fixtures and helper in `admin-system.spec.ts`**

- In `job()`, add `request: null` to the default object (before `...extra`).
- In the literal `restore_drill` fixture, add `request: null`.
- Add after `card`:

```ts
const RID = '7a1c0d3e-1111-4222-8333-944455556666';
const req = (job: string, state: string, extra: Record<string, unknown> = {}) => ({
  job, state, request_id: RID, requested_at: '2026-10-12T09:58:00Z', started_at: null, finished_at: null,
  exit_code: null, reason: null, ...extra,
});
const withRequest = (name: string, request: unknown) => ({
  ...STATUS, jobs: STATUS.jobs.map((j) => (j.job === name ? { ...j, request } : j)),
});

/** System mock whose GET answer the test switches with `set`; POSTs are recorded. */
async function setupRuns(page: Page, initial: unknown, post = { status: 202, body: { request_id: RID, state: 'queued' } as unknown }) {
  await page.addInitScript(() => {
    localStorage.setItem('ta_lang', 'ru');
    localStorage.setItem('ta_authenticated', '1');
  });
  let current = initial;
  const posts: string[] = [];
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === '/api/v1/auth/me') return json(route, { username: 'admin', role: 'admin' });
    if (url.pathname === '/api/v1/admin/system') return json(route, current);
    if (url.pathname.startsWith('/api/v1/admin/system/jobs/') && route.request().method() === 'POST') {
      posts.push(url.pathname);
      return json(route, post.body, post.status);
    }
    return json(route, { detail: 'No fixture' }, 404);
  });
  return { posts, set: (next: unknown) => { current = next; } };
}
```

- [ ] **Step 2: Tests**

```ts
test('each card offers only its whitelisted runs', async ({ page }) => {
  await setup(page);
  await page.goto('/admin/system');
  await expect(card(page, 'Скрапер').getByRole('button', { name: 'Загрузить новые документы' })).toBeEnabled();
  await expect(card(page, 'Скрапер').getByRole('button', { name: 'Полный ночной прогон' })).toBeEnabled();
  await expect(card(page, 'Канарейка').getByRole('button', { name: 'Прогнать канарейку' })).toBeEnabled();
  await expect(card(page, 'Бэкап базы').getByRole('button', { name: 'Бэкап сейчас' })).toBeEnabled();
  await expect(card(page, 'Проверка восстановления').getByRole('button')).toHaveCount(0);
});

test('manual run: confirm the cost, then the card follows the request to done', async ({ page }) => {
  await page.clock.setFixedTime(NOW);
  const mock = await setupRuns(page, STATUS);
  await page.goto('/admin/system');
  const canary = card(page, 'Канарейка');
  await canary.getByRole('button', { name: 'Прогнать канарейку' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toContainText('около 10 вызовов gpt-4o-mini');
  mock.set(withRequest('canary', req('canary', 'queued')));
  await dialog.getByRole('button', { name: 'Запустить' }).click();
  await expect(dialog).toBeHidden();
  expect(mock.posts).toEqual(['/api/v1/admin/system/jobs/canary']);
  await expect(canary).toContainText('В очереди');
  await expect(canary.getByRole('button', { name: 'Прогнать канарейку' })).toBeDisabled();

  mock.set(withRequest('canary', req('canary', 'running', { started_at: '2026-10-12T10:00:30Z' })));
  await page.getByRole('button', { name: 'Обновить' }).click();
  await expect(canary).toContainText('Выполняется с');

  mock.set(withRequest('canary', req('canary', 'done', {
    started_at: '2026-10-12T10:00:30Z', finished_at: '2026-10-12T10:02:10Z', exit_code: 0,
  })));
  await page.getByRole('button', { name: 'Обновить' }).click();
  await expect(canary).toContainText('Ручной запуск завершён');
  await expect(canary.getByRole('button', { name: 'Прогнать канарейку' })).toBeEnabled();
});

test('a refused run explains itself on the card', async ({ page }) => {
  await page.clock.setFixedTime(NOW);
  await setupRuns(page, STATUS, { status: 409, body: { detail: { code: 'backup_too_recent', message: 'x' } } });
  await page.goto('/admin/system');
  await card(page, 'Бэкап базы').getByRole('button', { name: 'Бэкап сейчас' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toContainText('Хранится 4 последних дампа; самый старый будет удалён.');
  await dialog.getByRole('button', { name: 'Запустить' }).click();
  await expect(dialog).toBeHidden();
  await expect(card(page, 'Бэкап базы')).toContainText('Последний бэкап был меньше 6 часов назад.');
});

test('an active request is re-read every 15 seconds and locks both scraper buttons', async ({ page }) => {
  await page.clock.install({ time: NOW });
  const mock = await setupRuns(page, withRequest('scraper', req('scraper_full', 'running', { started_at: '2026-10-12T09:59:00Z' })));
  await page.goto('/admin/system');
  const scraper = card(page, 'Скрапер');
  await expect(scraper).toContainText('Выполняется с');
  await expect(scraper.getByRole('button', { name: 'Загрузить новые документы' })).toBeDisabled();
  await expect(scraper.getByRole('button', { name: 'Полный ночной прогон' })).toBeDisabled();
  mock.set(withRequest('scraper', req('scraper_full', 'skipped', {
    started_at: '2026-10-12T09:59:00Z', finished_at: '2026-10-12T09:59:01Z', exit_code: 0, reason: 'busy',
  })));
  await page.clock.runFor(15_000);
  await expect(scraper).toContainText('Ручной запуск пропущен');
  await expect(scraper.getByRole('button', { name: 'Полный ночной прогон' })).toBeEnabled();
});
```

If `setupRuns` with `clock.install` and the auth bootstrap prove flaky, keep the assertions and switch only that test to `setFixedTime` plus `page.clock.runFor`. Note the choice in the report.

- [ ] **Step 3: Regenerate the two system baselines in the pinned container**

First build (as in docs/VISUAL_REGRESSION.md; Git Bash needs `MSYS_NO_PATHCONV=1` and `$(pwd -W)`), then run with `--update-snapshots` limited to `e2e/admin-system.spec.ts`. Then run the full admin matrix without update:
`e2e/admin-system.spec.ts e2e/admin.spec.ts e2e/admin-corpus.spec.ts e2e/admin-trends.spec.ts`.

Expected: all pass. Only `admin-system-ru-desktop.png` and `admin-system-ka-mobile.png` change; check with `rtk git status`. Open both PNGs (Read tool) and confirm that the buttons show on three cards, none on the drill card, and nothing overflows on mobile.

If the container run fails on a cold-start timeout only, rerun once. That was a known flake in 5a.

- [ ] **Step 4: Docs**

- `docs/PRODUCTION_OPERATIONS.md`, in the stage-5a "System page" block, add a short subsection «Ручной запуск (этап 5b)». It covers:
  - the four buttons;
  - the queue `ops-requests/` (`processing/`, `rejected/`);
  - the dispatcher cron and its log `/root/infohub/logs/ops-dispatcher.log`;
  - how to clear a stuck request: `rm /root/infohub/ops-requests/processing/<job>.json`, or wait 6 h for `interrupted`;
  - that `rejected/` is never cleaned automatically and is safe to empty;
  - the post-deploy check: press «Прогнать канарейку» and see `running` then `done` within 1–2 min.
- `docs/DEVELOPMENT_MEMORY.md`: one entry. Manual runs go through files only; the backend writes only `ops-requests/`; the dispatcher's command map is a hard `case`; canary logic lives in `ops/run_canary.sh` for both paths; `INFOHUB_MANUAL_RUN` keeps the zero-new streak.
- Spec, under §10 «Тесты 5b», add a line «Отклонения при реализации». List:
  1. the shell tests live in pytest (`backend/tests/test_ops_dispatcher.py`, `test_ops_run_canary.py`), following the repo's existing `test_db_backup_policy.py` pattern, not `ops/tests/*.sh`;
  2. 409 text is localised by `code` (stage-2 convention), so the backup time is not repeated in the message; the card already shows the last backup time;
  3. an unwritable request folder is a coded 500 `ops_queue_unavailable`;
  4. the journal row is flushed before the file is written.

- [ ] **Step 5: Commit**

```bash
rtk git add frontend/e2e/admin-system.spec.ts frontend/e2e/__screenshots__/admin-system-ru-desktop.png frontend/e2e/__screenshots__/admin-system-ka-mobile.png docs/PRODUCTION_OPERATIONS.md docs/DEVELOPMENT_MEMORY.md docs/superpowers/specs/2026-10-12-admin-stage5-ops-corpus-design.md
rtk git commit -m "test(admin): manual-run e2e and baselines; ops docs for stage 5b

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Deploy notes (for the PR body, not a task)

- Use the normal `deploy.sh`, but not around 03:00–04:00 UTC. It creates `ops-requests/` (0770), installs `/etc/cron.d/infohub-ops-dispatcher` and recreates the backend with the new read-write mount.
- After deploy, Gela presses «Прогнать канарейку». Within 1–2 minutes the card shows `Выполняется с …`, then `Ручной запуск завершён …` and a fresh canary status marked «запущено вручную». The run is also visible on `/admin/audit` as «Ручной запуск задачи».
