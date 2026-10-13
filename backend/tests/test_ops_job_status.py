"""Host ops status writer: atomic JSON for the admin System page."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("write_job_status", ROOT / "ops" / "write_job_status.py")
writer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(writer)


@pytest.fixture
def status_dir(tmp_path, monkeypatch):
    out = tmp_path / "ops-status"
    monkeypatch.setenv("INFOHUB_OPS_STATUS_DIR", str(out))
    monkeypatch.delenv("INFOHUB_JOB_TRIGGER", raising=False)
    monkeypatch.delenv("INFOHUB_JOB_SKIPPED", raising=False)
    return out


def _log(tmp_path, lines):
    path = tmp_path / "job.log"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def test_writes_status_json(status_dir, tmp_path):
    log = _log(tmp_path, [f"line {i}" for i in range(100)])
    assert writer.main(["w", "scraper", "2026-10-12T03:00:02Z", "0", "+3 new docs (full)", log]) == 0
    data = json.loads((status_dir / "scraper.json").read_text(encoding="utf-8"))
    assert data["schema_version"] == 1 and data["job"] == "scraper"
    assert data["started_at"] == "2026-10-12T03:00:02Z"
    assert data["finished_at"].endswith("Z") and data["exit_code"] == 0
    assert data["summary"] == "+3 new docs (full)"
    assert data["trigger"] == "cron" and data["skipped"] is False
    assert data["log_tail"] == [f"line {i}" for i in range(60, 100)]


def test_trigger_and_skipped_come_from_env(status_dir, tmp_path, monkeypatch):
    monkeypatch.setenv("INFOHUB_JOB_TRIGGER", "manual")
    monkeypatch.setenv("INFOHUB_JOB_SKIPPED", "1")
    writer.main(["w", "backup", "2026-10-12T01:30:00Z", "0", "", _log(tmp_path, ["skipped"])])
    data = json.loads((status_dir / "backup.json").read_text(encoding="utf-8"))
    assert data["trigger"] == "manual" and data["skipped"] is True


def test_unknown_trigger_falls_back_to_cron(status_dir, tmp_path, monkeypatch):
    monkeypatch.setenv("INFOHUB_JOB_TRIGGER", "evil")
    writer.main(["w", "canary", "", "1", "CANARY: 8/10", _log(tmp_path, [])])
    data = json.loads((status_dir / "canary.json").read_text(encoding="utf-8"))
    assert data["trigger"] == "cron" and data["started_at"] is None and data["exit_code"] == 1


def test_unknown_job_and_bad_usage_exit_2(status_dir, tmp_path):
    assert writer.main(["w", "rm -rf", "", "0", "", "/dev/null"]) == 2
    assert writer.main(["w", "scraper"]) == 2
    assert not status_dir.exists()


def test_non_numeric_exit_code_is_minus_one(status_dir, tmp_path):
    writer.main(["w", "scraper", "", "?", "", _log(tmp_path, [])])
    assert json.loads((status_dir / "scraper.json").read_text(encoding="utf-8"))["exit_code"] == -1


def test_redacts_secrets():
    assert writer.redact("TELEGRAM_BOT_TOKEN=123:abcDEF") == "TELEGRAM_BOT_TOKEN=[redacted]"
    assert writer.redact("Authorization: Bearer abc.def") == "Authorization=[redacted]"
    assert writer.redact("password = hunter2 rest") == "password=[redacted] rest"
    assert writer.redact("url https://api.telegram.org/bot123456:AAH-x_y/sendMessage") == \
        "url https://api.telegram.org/bot[redacted]/sendMessage"
    assert writer.redact("duplicate key violates unique constraint") == "duplicate key violates unique constraint"


def test_long_lines_truncated_and_missing_log_is_empty(tmp_path):
    log = _log(tmp_path, ["x" * 1000])
    assert writer.tail(log) == ["x" * 300]
    assert writer.tail(str(tmp_path / "missing.log")) == []


def test_write_is_atomic_and_leaves_no_temp(status_dir, tmp_path):
    log = _log(tmp_path, ["a"])
    for _ in range(3):
        writer.main(["w", "restore_drill", "", "0", "ok", log])
    assert sorted(p.name for p in status_dir.iterdir()) == ["restore_drill.json"]
    assert oct((status_dir / "restore_drill.json").stat().st_mode & 0o777) in ("0o644", "0o666")


def test_write_failure_never_fails_caller(tmp_path, monkeypatch):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("INFOHUB_OPS_STATUS_DIR", str(blocker / "sub"))
    assert writer.main(["w", "scraper", "", "0", "", "/dev/null"]) == 0


def _text(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def test_scraper_writes_scraper_and_canary_status():
    text = _text("run_scraper.sh")
    assert 'STATUS_WRITER="$SCRIPT_DIR/ops/write_job_status.py"' in text
    assert "trap write_scraper_status EXIT" in text
    assert 'python3 "$STATUS_WRITER" canary "$CANARY_STARTED_AT" "$CANARY_EXIT"' in text
    # The trap is installed only after the lock: a skipped overlapping run must not overwrite the status.
    assert text.index("flock -n 9") < text.index("trap write_scraper_status EXIT")


def test_backup_and_drill_write_status_from_exit_trap():
    for rel, job in (("ops/backup-infohub-db.sh", "backup"), ("ops/restore-drill-infohub-db.sh", "restore_drill")):
        text = _text(rel)
        finish = text[text.index("finish() {"):text.index("trap finish EXIT")]
        assert f'"$STATUS_WRITER" {job} "$started_at" "$rc"' in finish, rel
        assert 'INFOHUB_JOB_SKIPPED="$skipped"' in finish, rel
        assert "|| true" in finish, rel


def test_status_dir_is_mounted_read_only_and_created_on_deploy():
    assert "- ./ops-status:/app/ops-status:ro" in _text("docker-compose.yml")
    deploy = _text("scripts/deploy_production.sh")
    assert "install -d -m 0755 ops-status" in deploy
    assert deploy.index("install -d -m 0755 ops-status") < deploy.index("docker compose config --quiet")
