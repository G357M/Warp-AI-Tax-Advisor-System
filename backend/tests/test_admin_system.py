"""Admin System page: job state from host status files (no database)."""
import json
from datetime import datetime

from api.routes.admin_system import router
from core.admin_system import system_status
from core.security import require_admin

NOW = datetime(2026, 10, 12, 10, 0)  # naive UTC


def _write(directory, name, **fields):
    data = {"schema_version": 1, "job": name, "started_at": "2026-10-12T03:00:00Z",
            "finished_at": "2026-10-12T03:40:00Z", "exit_code": 0, "summary": "ok",
            "trigger": "cron", "skipped": False, "log_tail": ["a", "b"]}
    data.update(fields)
    (directory / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")


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
    _write(tmp_path, "restore_drill", finished_at="2026-09-06T10:00:00Z")  # exactly 36 days
    states = _states(tmp_path)
    assert states["scraper"] == "ok" and states["canary"] == "stale" and states["restore_drill"] == "ok"
    _write(tmp_path, "restore_drill", finished_at="2026-09-06T09:59:59Z")
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


def _request_status(directory, name, **fields):
    data = {"schema_version": 1, "job": name, "request_id": "r-" + name, "requested_at": "2026-10-12T09:00:00Z",
            "state": "done", "started_at": "2026-10-12T09:00:30Z", "finished_at": "2026-10-12T09:05:00Z",
            "exit_code": 0, "reason": None}
    data.update(fields)
    (directory / f"{name}.request.json").write_text(json.dumps(data), encoding="utf-8")


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


def test_bad_request_status_is_ignored(tmp_path):
    _request_status(tmp_path, "canary", state="exploded")
    _request_status(tmp_path, "backup", job="canary")
    (tmp_path / "scraper_full.request.json").write_text("{", encoding="utf-8")
    cards = _cards(tmp_path)
    assert cards["canary"] is None and cards["backup"] is None and cards["scraper"] is None
    assert cards["restore_drill"] is None
