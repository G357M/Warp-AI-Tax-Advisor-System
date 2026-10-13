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
