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
    "restore_drill": timedelta(days=36),
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
