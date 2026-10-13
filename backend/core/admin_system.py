"""Admin System page: latest status of host cron jobs (read-only).

The host writes ops-status/<job>.json (ops/write_job_status.py); the backend
mounts that dir read-only. Anything unreadable or unexpected becomes
"unknown" rather than an error, so one bad file never hides the others.
Manual-run requests (stage 5b) are read from ops-status/<job>.request.json
(written by the host dispatcher) and from ops-requests/ (files still waiting).
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
MANUAL_JOBS = ("scraper_ingest", "scraper_full", "canary", "backup")
CARD_REQUESTS = {"scraper": ("scraper_ingest", "scraper_full"), "canary": ("canary",),
                 "backup": ("backup",), "restore_drill": ()}
REQUEST_STATES = ("queued", "running", "done", "skipped", "failed")
ACTIVE_STATES = ("queued", "running")


def naive_utc(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed


def load_status(path: Path, job: str) -> dict | None:
    try:
        if path.stat().st_size > MAX_BYTES:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("schema_version") != 1 or data.get("job") != job:
        return None
    if type(data.get("exit_code")) is not int or naive_utc(data.get("finished_at")) is None:
        return None
    return data


def _state(data: dict | None, job: str, now: datetime) -> str:
    if data is None:
        return "unknown"
    fresh = now - naive_utc(data["finished_at"]) <= FRESH_FOR[job]
    if data["exit_code"] != 0 and data.get("skipped") is not True:
        return "failed"
    if data.get("skipped") is True:
        return "skipped" if fresh else "stale"
    return "ok" if fresh else "stale"


def _text(data: dict | None, key: str) -> str | None:
    value = data.get(key) if data else None
    return value if isinstance(value, str) else None


def _entry(job: str, data: dict | None, now: datetime, request: dict | None) -> dict:
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
        "request": request,
    }


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
    "queued"; otherwise the validated ops-status/<job>.request.json the dispatcher
    writes (queued, running, done, skipped or failed)."""
    if request_dir is not None and (request_dir / f"{job}.json").exists():
        return _request(job, "queued", _read_json(request_dir / f"{job}.json"))
    data = _read_json(status_dir / f"{job}.request.json")
    if data is None or data.get("schema_version") != 1 or data.get("job") != job             or data.get("state") not in REQUEST_STATES:
        return None
    return _request(job, data["state"], data)


def card_request(status_dir: Path, request_dir: Path | None, card: str) -> dict | None:
    found = [r for r in (request_status(status_dir, request_dir, job) for job in CARD_REQUESTS[card]) if r]
    active = [r for r in found if r["state"] in ACTIVE_STATES]
    pool = active or found
    return max(pool, key=lambda r: r["requested_at"] or "") if pool else None


def system_status(directory: Path, now: datetime, request_dir: Path | None = None) -> dict:
    return {
        "generated_at": now.isoformat(),
        "jobs": [_entry(job, load_status(directory / f"{job}.json", job), now,
                        card_request(directory, request_dir, job)) for job in JOBS],
    }
