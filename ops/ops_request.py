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
import re
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
ISO_TIMESTAMP = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _status_dir() -> Path:
    return Path(os.environ.get("INFOHUB_OPS_STATUS_DIR") or DEFAULT_DIR)


def read_request(path: Path) -> dict | None:
    job = path.stem if path.suffix == ".json" and path.stem in JOBS else None
    if job is None:
        return None
    try:
        # Use O_RDONLY | O_NOFOLLOW | O_NONBLOCK to prevent TOCTOU attacks
        # and avoid hanging on FIFOs. Fallback to getattr for Windows compatibility.
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        if hasattr(os, "O_NONBLOCK"):
            flags |= os.O_NONBLOCK
        fd = os.open(str(path), flags)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
                return None
            content = os.read(fd, MAX_BYTES + 1)
            if len(content) > MAX_BYTES:
                return None
            data = json.loads(content.decode("utf-8"))
        finally:
            os.close(fd)
    except (OSError, ValueError, RecursionError):
        return None
    if not isinstance(data, dict) or data.get("schema_version") != 1 or data.get("job") != job:
        return None
    try:
        request_id = str(uuid.UUID(str(data.get("request_id"))))
    except ValueError:
        return None
    requested_at = data.get("requested_at")
    # Validate requested_at format to prevent encoding issues when writing status
    if not (isinstance(requested_at, str) and ISO_TIMESTAMP.match(requested_at)):
        requested_at = None
    return {"job": job, "request_id": request_id,
            "requested_at": requested_at}


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
    if not isinstance(data, dict):
        return False
    finished = data.get("finished_at")
    return data.get("skipped") is True and isinstance(finished, str) and finished >= started_at


def outcome(job: str, exit_code: int, output: str, started_at: str | None) -> tuple:
    if any(marker in output for marker in SKIP_MARKERS) or (started_at and _skipped_since(job, started_at)):
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
        # Get and validate started_at to prevent encoding issues (surrogates, etc.)
        started_at = argv[3] if command != "interrupted" else None
        if started_at and not ISO_TIMESTAMP.match(started_at):
            print(f"[ops-request] ignoring invalid STARTED_AT", file=sys.stderr)
            started_at = None  # Treat invalid timestamp as None, still write status

        if command == "running":
            write_status(request, state="running", started_at=started_at)
        elif command == "finish":
            try:
                code = int(argv[4])
            except ValueError:
                code = -1
            # For outcome check, use started_at only if valid (not None)
            state, reason = outcome(request["job"], code, _output(argv[5]), started_at)
            write_status(request, state=state, started_at=started_at, finished_at=_now(),
                         exit_code=code, reason=reason)
        else:
            write_status(request, state="failed", finished_at=_now(), reason="interrupted")
    except (OSError, ValueError) as exc:
        print(f"[ops-request] could not write {request['job']} request status: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
