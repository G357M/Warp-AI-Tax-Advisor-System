"""Contracts for the nightly production database backup (ops/backup-infohub-db.sh)."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY_ROOT / "ops" / "backup-infohub-db.sh"
CRON = REPOSITORY_ROOT / "ops" / "cron-infohub-db-backup"
DEPLOY = REPOSITORY_ROOT / "scripts" / "deploy_production.sh"

FULL_TOC = """;
; Archive created at 2026-10-03
;
3001; 0 16400 TABLE DATA public documents infohub_user
3002; 0 16410 TABLE DATA public document_chunks infohub_user
3003; 0 16420 TABLE DATA public users infohub_user
"""

needs_posix = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("flock") is None,
    reason="requires bash and flock (Linux CI / production host)",
)


def _fake_docker(bin_dir: Path, toc: str) -> None:
    (bin_dir / "toc.txt").write_text(toc, encoding="utf-8")
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        'if [[ " $* " == *" pg_dump "* ]]; then printf "PGDMP-fake-archive"; exit 0; fi\n'
        'if [[ " $* " == *" pg_restore "* ]]; then cat >/dev/null; cat "$(dirname "$0")/toc.txt"; exit 0; fi\n'
        "exit 1\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)


FAKE_ALERT = r'''printf "%s|%s\n" "$1" "$2" >> "$(dirname "$0")/alerts.log"
'''


def _fake_alert(bin_dir: Path) -> Path:
    alert = bin_dir / "alert.sh"
    alert.write_text(FAKE_ALERT, encoding="utf-8", newline="\n")
    return alert


def _alerts(tmp_path: Path) -> str:
    log = tmp_path / "bin" / "alerts.log"
    return log.read_text(encoding="utf-8") if log.exists() else ""


def _run(tmp_path: Path, toc: str = FULL_TOC, keep: str = "2") -> subprocess.CompletedProcess:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    _fake_docker(bin_dir, toc)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "INFOHUB_DB_BACKUP_DIR": str(tmp_path / "backups"),
        "INFOHUB_DB_BACKUP_KEEP": keep,
        "INFOHUB_DB_BACKUP_LOCK": str(tmp_path / "backup.lock"),
        "INFOHUB_OPS_ALERT": str(_fake_alert(bin_dir)),
    }
    return subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True)


@needs_posix
def test_backup_writes_verified_dump_with_checksum(tmp_path):
    result = _run(tmp_path)

    assert result.returncode == 0, result.stderr
    dumps = sorted((tmp_path / "backups").glob("infohub_ai-*.dump"))
    assert len(dumps) == 1
    assert dumps[0].read_bytes() == b"PGDMP-fake-archive"
    checksum = dumps[0].with_name(dumps[0].name + ".sha256").read_text(encoding="utf-8")
    assert dumps[0].name in checksum
    assert not list((tmp_path / "backups").glob("*.partial"))
    assert _alerts(tmp_path) == ""


@needs_posix
def test_backup_rotation_keeps_newest(tmp_path):
    backups = tmp_path / "backups"
    backups.mkdir()
    for i, stamp in enumerate(("20260901T013000Z", "20260902T013000Z", "20260903T013000Z")):
        old = backups / f"infohub_ai-{stamp}.dump"
        old.write_bytes(b"old")
        (backups / f"{old.name}.sha256").write_text("x", encoding="utf-8")
        os.utime(old, (1_700_000_000 + i, 1_700_000_000 + i))

    result = _run(tmp_path, keep="2")

    assert result.returncode == 0, result.stderr
    remaining = sorted(p.name for p in backups.glob("infohub_ai-*.dump"))
    assert len(remaining) == 2
    assert "infohub_ai-20260903T013000Z.dump" in remaining
    assert not (backups / "infohub_ai-20260901T013000Z.dump.sha256").exists()


@needs_posix
def test_unverifiable_dump_never_replaces_good_backups(tmp_path):
    backups = tmp_path / "backups"
    backups.mkdir()
    good = backups / "infohub_ai-20260901T013000Z.dump"
    good.write_bytes(b"good")

    toc_without_chunks = "\n".join(line for line in FULL_TOC.splitlines() if "document_chunks" not in line)
    result = _run(tmp_path, toc=toc_without_chunks, keep="1")

    assert result.returncode != 0
    assert "document_chunks" in result.stdout + result.stderr
    assert [p.name for p in backups.iterdir()] == [good.name]
    assert _alerts(tmp_path).startswith(
        "nightly DB backup|exit 1: verification failed: no data entry for table 'document_chunks'"
    )


@needs_posix
def test_failed_pg_dump_alerts_with_the_failing_command(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8", newline="\n")
    docker.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "INFOHUB_DB_BACKUP_DIR": str(tmp_path / "backups"),
        "INFOHUB_DB_BACKUP_LOCK": str(tmp_path / "backup.lock"),
        "INFOHUB_OPS_ALERT": str(_fake_alert(bin_dir)),
    }

    result = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True)

    assert result.returncode != 0
    alerts = _alerts(tmp_path)
    assert "command failed: docker exec" in alerts
    assert "pg_dump" in alerts
    assert not list((tmp_path / "backups").glob("*.partial"))


@needs_posix
def test_invalid_keep_is_rejected(tmp_path):
    assert _run(tmp_path, keep="0").returncode == 2
    assert "INFOHUB_DB_BACKUP_KEEP must be a positive integer" in _alerts(tmp_path)


ALERT_SCRIPT = REPOSITORY_ROOT / "ops" / "ops_alert.sh"
FAKE_CURL = r'''#!/usr/bin/env bash
printf "%s\n" "$@" >> "$(dirname "$0")/curl.log"
'''


def _run_ops_alert(tmp_path: Path, env_lines: str) -> tuple[subprocess.CompletedProcess, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    curl = bin_dir / "curl"
    curl.write_text(FAKE_CURL, encoding="utf-8", newline="\n")
    curl.chmod(0o755)
    env_file = tmp_path / ".env"
    env_file.write_text(env_lines, encoding="utf-8", newline="\n")
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "INFOHUB_ENV_FILE": str(env_file)}
    result = subprocess.run(
        ["bash", str(ALERT_SCRIPT), "nightly DB backup", "exit 1: disk full"],
        env=env, capture_output=True, text=True,
    )
    log = bin_dir / "curl.log"
    return result, log.read_text(encoding="utf-8") if log.exists() else ""


@needs_posix
def test_ops_alert_sends_job_and_reason_to_telegram(tmp_path):
    result, curl = _run_ops_alert(tmp_path, 'TELEGRAM_BOT_TOKEN="123:abc"\nTELEGRAM_CHAT_ID=42\n')

    assert result.returncode == 0
    assert "https://api.telegram.org/bot123:abc/sendMessage" in curl
    assert "chat_id=42" in curl
    assert "InfoHub nightly DB backup FAILED" in curl
    assert "exit 1: disk full" in curl


@needs_posix
def test_ops_alert_without_credentials_logs_and_succeeds(tmp_path):
    result, curl = _run_ops_alert(tmp_path, "OTHER=1\n")

    assert result.returncode == 0
    assert curl == ""
    assert "would have sent" in result.stdout


def test_ops_scripts_have_unix_line_endings():
    for script in (SCRIPT, ALERT_SCRIPT):
        assert b"\r" not in script.read_bytes(), script


def test_deploy_installs_backup_cron():
    deploy = DEPLOY.read_text(encoding="utf-8")
    assert "install -m 0644 ops/cron-infohub-db-backup /etc/cron.d/infohub-db-backup" in deploy


def test_cron_entry_runs_as_root_before_nightly_scraper():
    lines = [l for l in CRON.read_text(encoding="utf-8").splitlines() if l and not l.startswith("#")]
    jobs = [l for l in lines if "=" not in l.split()[0]]
    assert len(jobs) == 1
    minute, hour, dom, month, dow, user, command = jobs[0].split(None, 6)
    assert (minute, hour, dom, month, dow, user) == ("30", "1", "*", "*", "*", "root")
    assert command.startswith("/root/infohub/ops/backup-infohub-db.sh")
    assert CRON.read_bytes().endswith(b"\n") and b"\r" not in CRON.read_bytes()
