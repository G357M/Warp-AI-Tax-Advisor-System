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


def _request(directory: Path, filename_job: str, **fields) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    # Allow job to be overridden in fields for mismatch testing
    actual_job = fields.pop('job', filename_job)
    data = {"schema_version": 1, "request_id": str(uuid4()), "job": actual_job,
            "requested_at": "2026-10-13T10:00:00Z", "actor_id": str(uuid4())}
    data.update(fields)
    path = directory / f"{filename_job}.json"
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


def test_status_file_is_array_does_not_crash(tmp_path, status_dir):
    """Status file holding a JSON array should not crash _skipped_since."""
    status_dir.mkdir(parents=True)
    (status_dir / "backup.json").write_text("[]", encoding="utf-8")
    path = _request(tmp_path, "backup")
    output = tmp_path / "out.log"
    output.write_text("", encoding="utf-8")
    assert ops_request.main(["x", "finish", str(path), "2026-10-13T10:01:00Z", "0", str(output)]) == 0
    assert _status(status_dir, "backup")["state"] == "done"


def test_hostile_surrogate_in_requested_at(tmp_path, status_dir):
    """A request with surrogate in requested_at doesn't crash dispatcher."""
    path = _request(tmp_path, "canary", requested_at="\ud800")
    # check should still work, normalizing the bad requested_at to None
    assert ops_request.main(["x", "check", str(path)]) == 0
    # running should exit 0 and write the status with requested_at null
    assert ops_request.main(["x", "running", str(path), "2026-10-13T10:01:00Z"]) == 0
    status = _status(status_dir, "canary")
    assert status["requested_at"] is None


def test_recursive_json_does_not_crash_on_read(tmp_path):
    """Deeply nested JSON causing RecursionError is rejected."""
    path = tmp_path / "canary.json"
    # Create a deeply nested array that will exceed recursion limit
    nested = "[" * 3000 + "]" * 3000
    path.write_text(json.dumps({"schema_version": 1, "job": "canary", "request_id": str(uuid4()),
                                  "requested_at": "2026-10-13T10:00:00Z", "data": nested}),
                    encoding="utf-8")
    # Should reject due to RecursionError during json.loads
    assert ops_request.main(["x", "check", str(path)]) == 1


@pytest.mark.skipif(not hasattr(os, "mkfifo") or os.name == "nt", reason="FIFOs need POSIX")
def test_check_rejects_fifo_without_blocking(tmp_path):
    """A FIFO should be rejected immediately without hanging."""
    fifo_path = tmp_path / "canary.json"
    os.mkfifo(str(fifo_path))
    # Should exit 1 immediately without blocking on the FIFO
    assert ops_request.main(["x", "check", str(fifo_path)]) == 1
