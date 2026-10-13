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
