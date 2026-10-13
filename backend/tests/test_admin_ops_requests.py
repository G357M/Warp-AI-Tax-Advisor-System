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
