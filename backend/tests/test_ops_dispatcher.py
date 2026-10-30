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
              env_extra: dict | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ,
           "INFOHUB_OPS_REQUEST_DIR": str(tmp_path / "ops-requests"),
           "INFOHUB_OPS_STATUS_DIR": str(tmp_path / "ops-status"),
           "INFOHUB_OPS_DISPATCH_STATE": str(tmp_path / "state"),
           "INFOHUB_OPS_DISPATCHER_LOCK": str(tmp_path / "dispatcher.lock"),
           "INFOHUB_DISPATCH_SCRAPER": str(_stub(tmp_path, "scraper", scraper_extra)),
           "INFOHUB_DISPATCH_CANARY": str(_stub(tmp_path, "canary")),
           "INFOHUB_DISPATCH_BACKUP": str(_stub(tmp_path, "backup", backup_extra)),
           "CALLS": str(tmp_path / "calls.log"),
           "STUB_EXIT": str(stub_exit)}
    for key in ("INFOHUB_JOB_TRIGGER", "INFOHUB_MANUAL_RUN"):
        env.pop(key, None)
    env.update(env_extra or {})
    return subprocess.run(["bash", str(DISPATCHER)], env=env, capture_output=True, text=True, cwd=cwd)


def _calls(tmp_path: Path) -> list:
    log = tmp_path / "calls.log"
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def _state(tmp_path: Path, job: str) -> dict:
    return json.loads((tmp_path / "ops-status" / f"{job}.request.json").read_text(encoding="utf-8"))


def _queue_empty(tmp_path: Path) -> bool:
    root = tmp_path / "ops-requests"
    return not [p for p in root.iterdir() if p.is_file()] and not list((tmp_path / "state" / "processing").iterdir())


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
    rejected = sorted(p.name for p in (tmp_path / "state" / "rejected").iterdir())
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
    assert (tmp_path / "state" / "rejected" / "backup.json").is_symlink()


def test_hidden_temp_files_are_left_for_the_writer(tmp_path):
    (tmp_path / "ops-requests").mkdir()
    temp = tmp_path / "ops-requests" / ".canary.abc.tmp"
    temp.write_text("{", encoding="utf-8")
    _dispatch(tmp_path)
    assert temp.exists() and _calls(tmp_path) == []


def test_stuck_processing_becomes_interrupted(tmp_path):
    processing = tmp_path / "state" / "processing"
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


def test_symlinked_state_dir_stops_the_dispatcher(tmp_path):
    _request(tmp_path, "canary")
    target = tmp_path / "target"
    target.mkdir()
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "rejected").symlink_to(target)
    result = _dispatch(tmp_path)
    assert result.returncode != 0 and _calls(tmp_path) == []
    assert list(target.iterdir()) == []


def test_newline_in_a_file_name_cannot_forge_another_entry(tmp_path):
    sentinel = tmp_path / "sentinel"
    sentinel.write_text("keep", encoding="utf-8")
    (tmp_path / "ops-requests").mkdir()
    hostile = tmp_path / "ops-requests" / ("x" + chr(10) + "sentinel")   # newline in the name
    hostile.write_text("{}", encoding="utf-8")
    result = _dispatch(tmp_path, cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert sentinel.exists() and _calls(tmp_path) == []
    assert not (tmp_path / "state" / "rejected" / "sentinel").exists()


def test_deploy_and_compose_wire_the_queue():
    deploy = (ROOT / "scripts" / "deploy_production.sh").read_text(encoding="utf-8")
    assert "install -d -m 0770 ops-requests" in deploy
    assert "install -d -m 0700 /var/lib/infohub/ops-dispatch" in deploy
    assert "install -m 0644 ops/cron-infohub-ops-dispatcher /etc/cron.d/infohub-ops-dispatcher" in deploy
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "./ops-requests:/app/ops-requests" in compose
    assert "./ops-requests:/app/ops-requests:ro" not in compose
    cron = (ROOT / "ops" / "cron-infohub-ops-dispatcher").read_text(encoding="utf-8")
    assert "* * * * * root /bin/bash /root/infohub/ops/ops-dispatcher.sh" in cron
