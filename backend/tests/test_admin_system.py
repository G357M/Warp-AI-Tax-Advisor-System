"""Admin System page: job state from host status files (no database)."""
import json
from datetime import datetime
from pathlib import Path

from core.admin_system import system_status

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
    # Foreign job: write canary.json but with job="backup" inside
    _write(tmp_path, "canary")
    import json
    data = json.loads((tmp_path / "canary.json").read_text(encoding="utf-8"))
    data["job"] = "backup"
    (tmp_path / "canary.json").write_text(json.dumps(data), encoding="utf-8")
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
    source = (Path(__file__).parents[1] / "api" / "routes" / "admin_system.py").read_text(encoding="utf-8")
    assert "dependencies=[Depends(require_admin)]" in source
