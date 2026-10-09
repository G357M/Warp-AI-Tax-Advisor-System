"""Contracts for the backup restore drill (ops/restore-drill-infohub-db.sh)."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY_ROOT / "ops" / "restore-drill-infohub-db.sh"
CRON = REPOSITORY_ROOT / "ops" / "cron-infohub-restore-drill"
DEPLOY = REPOSITORY_ROOT / "scripts" / "deploy_production.sh"
LOGROTATE = REPOSITORY_ROOT / "ops" / "logrotate-infohub"
COMPOSE = REPOSITORY_ROOT / "docker-compose.yml"

LIVE_COUNTS = {"documents": 100, "document_chunks": 900, "users": 10, "decision_facts": 50, "feedback": 3}

needs_posix = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("flock") is None,
    reason="requires bash and flock (Linux CI / production host)",
)

# Stands in for the docker CLI: the live container is infohub-postgres, every
# other exec target is the drill. Each call is appended to calls.log.
FAKE_DOCKER = r"""#!/usr/bin/env bash
here="$(dirname "$0")"
echo "$*" >> "$here/calls.log"
case "$1" in
  inspect) echo "pgvector/pgvector:pg15"; exit 0 ;;
  info) echo "$here"; exit 0 ;;
  volume|run|rm) exit 0 ;;
  exec) ;;
  *) exit 1 ;;
esac
shift
[[ "$1" == "-i" ]] && shift
side=drill; [[ "$1" == "infohub-postgres" ]] && side=live
shift
case "$1" in
  pg_isready) exit 0 ;;
  pg_restore) [[ -f "$here/restore_fails" ]] && { echo "pg_restore: error: could not execute query"; exit 1; }; exit 0 ;;
esac
sql="${@: -1}"
case "$sql" in
  *pg_database_size*) echo 1000 ;;
  *pg_tables*) cut -d' ' -f1 "$here/counts_$side.txt" ;;
  *'count(*) FROM public."'*)
    table="${sql#*public.\"}"; table="${table%%\"*}"
    grep "^$table " "$here/counts_$side.txt" | cut -d' ' -f2 ;;
  *relkind*) printf 'i:6\nr:5\n' ;;
  *indisvalid*) echo 0 ;;
  *pg_extension*) echo "plpgsql 1.0, vector 0.7.0" ;;
  *'ORDER BY embedding'*) echo 5 ;;
  *'embedding IS NOT NULL'*) echo 900 ;;
  *) exit 3 ;;
esac
"""


def _setup(tmp_path: Path, drill_counts: dict[str, int] | None = None, good_checksum: bool = True) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(FAKE_DOCKER, encoding="utf-8", newline="\n")
    docker.chmod(0o755)
    for side, counts in (("live", LIVE_COUNTS), ("drill", drill_counts or LIVE_COUNTS)):
        lines = "".join(f"{table} {count}\n" for table, count in sorted(counts.items()))
        (bin_dir / f"counts_{side}.txt").write_text(lines, encoding="utf-8", newline="\n")

    backups = tmp_path / "backups"
    backups.mkdir()
    dump = backups / "infohub_ai-20261006T013001Z.dump"
    dump.write_bytes(b"PGDMP-fake-archive")
    digest = hashlib.sha256(dump.read_bytes() if good_checksum else b"other").hexdigest()
    (backups / f"{dump.name}.sha256").write_text(f"{digest}  {dump.name}\n", encoding="utf-8", newline="\n")
    return bin_dir


FAKE_ALERT = r'''printf "%s|%s\n" "$1" "$2" >> "$(dirname "$0")/alerts.log"
'''


def _run(tmp_path: Path, *args: str, **extra_env: str) -> subprocess.CompletedProcess:
    alert = tmp_path / "bin" / "alert.sh"
    alert.write_text(FAKE_ALERT, encoding="utf-8", newline="\n")
    env = {
        **os.environ,
        "PATH": f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}",
        "INFOHUB_DB_BACKUP_DIR": str(tmp_path / "backups"),
        "INFOHUB_DB_BACKUP_LOCK": str(tmp_path / "backup.lock"),
        "INFOHUB_OPS_ALERT": str(alert),
        **extra_env,
    }
    return subprocess.run(["bash", str(SCRIPT), *args], env=env, capture_output=True, text=True)


def _calls(tmp_path: Path) -> list[str]:
    log = tmp_path / "bin" / "calls.log"
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def _alerts(tmp_path: Path) -> str:
    log = tmp_path / "bin" / "alerts.log"
    return log.read_text(encoding="utf-8") if log.exists() else ""


def _marker(tmp_path: Path) -> str:
    return (tmp_path / "backups" / "restore-drill-last.txt").read_text(encoding="utf-8")


def _assert_cleaned_up(calls: list[str]) -> None:
    assert any(c.startswith("rm -f infohub-restore-drill-") for c in calls)
    assert any(c.startswith("volume rm infohub-restore-drill-") for c in calls)


@needs_posix
def test_drill_restores_isolated_copy_and_records_success(tmp_path):
    _setup(tmp_path)

    result = _run(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert _marker(tmp_path).startswith("ok infohub_ai-20261006T013001Z.dump ")
    calls = _calls(tmp_path)
    run = next(c for c in calls if c.startswith("run "))
    assert "--network none" in run
    assert ":/backups:ro" in run
    assert "--cpus 1 --memory 2g --shm-size 1g" in run
    assert run.endswith("pgvector/pgvector:pg15")
    _assert_cleaned_up(calls)
    assert "pgvector ok" in result.stdout
    assert _alerts(tmp_path) == ""


@needs_posix
def test_checksum_mismatch_stops_before_any_container(tmp_path):
    _setup(tmp_path, good_checksum=False)

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "sha256 mismatch" in result.stderr
    assert not any(c.startswith(("run ", "volume ")) for c in _calls(tmp_path))
    assert _marker(tmp_path).startswith("failed ")
    assert _alerts(tmp_path).startswith("monthly restore drill|exit 1: sha256 mismatch")


@needs_posix
def test_empty_core_table_fails_and_still_cleans_up(tmp_path):
    _setup(tmp_path, drill_counts={**LIVE_COUNTS, "document_chunks": 0})

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "EMPTY" in result.stdout
    assert _marker(tmp_path).startswith("failed ")
    _assert_cleaned_up(_calls(tmp_path))
    assert "1 check(s) failed" in _alerts(tmp_path)


@needs_posix
def test_core_table_far_below_live_fails(tmp_path):
    _setup(tmp_path, drill_counts={**LIVE_COUNTS, "documents": 50})

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "differs from live" in result.stdout


@needs_posix
def test_missing_core_table_fails(tmp_path):
    _setup(tmp_path, drill_counts={k: v for k, v in LIVE_COUNTS.items() if k != "decision_facts"})

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "core table 'decision_facts' missing" in result.stderr


@needs_posix
def test_pg_restore_errors_fail_the_drill(tmp_path):
    _setup(tmp_path)
    (tmp_path / "bin" / "restore_fails").touch()

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "could not execute query" in result.stderr
    _assert_cleaned_up(_calls(tmp_path))


@needs_posix
def test_explicit_dump_argument_and_missing_dump(tmp_path):
    _setup(tmp_path)
    dump = tmp_path / "backups" / "infohub_ai-20261006T013001Z.dump"

    assert _run(tmp_path, str(dump)).returncode == 0
    missing = _run(tmp_path, str(tmp_path / "backups" / "nope.dump"))
    assert missing.returncode == 1
    assert "dump not found" in missing.stderr


@needs_posix
def test_invalid_numeric_setting_is_rejected(tmp_path):
    _setup(tmp_path)

    assert _run(tmp_path, INFOHUB_RESTORE_DRILL_JOBS="0").returncode == 2
    assert "numeric settings must be positive integers" in _alerts(tmp_path)


@needs_posix
def test_drill_skipped_by_held_lock_alerts(tmp_path):
    _setup(tmp_path)
    lock = tmp_path / "backup.lock"
    holder = subprocess.Popen(["flock", str(lock), "-c", "echo held; sleep 30"], stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "held"
        result = _run(tmp_path)
    finally:
        holder.kill()
        holder.wait()

    assert result.returncode == 75
    assert "skipped: a backup or another drill holds the lock" in _alerts(tmp_path)
    assert not any(c.startswith("run ") for c in _calls(tmp_path))


def test_script_has_unix_line_endings():
    assert b"\r" not in SCRIPT.read_bytes()


def _cron_job() -> list[str]:
    lines = [l for l in CRON.read_text(encoding="utf-8").splitlines() if l and not l.startswith("#")]
    jobs = [l for l in lines if "=" not in l.split()[0]]
    assert len(jobs) == 1
    return jobs[0].split(None, 6)


def test_deploy_installs_restore_drill_cron_and_log_rotation():
    deploy = DEPLOY.read_text(encoding="utf-8")
    assert "install -m 0644 ops/cron-infohub-restore-drill /etc/cron.d/infohub-restore-drill" in deploy
    assert "/root/infohub/logs/restore-drill.log" in LOGROTATE.read_text(encoding="utf-8").splitlines()[0]


def test_restore_drill_cron_runs_monthly_between_refresh_and_backup():
    minute, hour, dom, month, dow, user, command = _cron_job()
    # 22:15 UTC: after the 21:17 ingest refresh, ~3 h before the 01:30 backup.
    assert (minute, hour, dom, month, dow, user) == ("15", "22", "1-7", "*", "*", "root")
    assert "/root/infohub/ops/restore-drill-infohub-db.sh >> /root/infohub/logs/restore-drill.log 2>&1" in command
    assert CRON.read_bytes().endswith(b"\n") and b"\r" not in CRON.read_bytes()


@needs_posix
@pytest.mark.parametrize(("weekday", "runs"), [("6", True), ("7", False), ("1", False)])
def test_restore_drill_cron_runs_only_on_saturday(tmp_path, weekday, runs):
    *_, command = _cron_job()
    # cron turns "\%" into "%" before handing the line to SHELL.
    command = command.replace(r"\%", "%").split(";", 1)[0] + "; echo DRILL"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_date = bin_dir / "date"
    fake_date.write_text(f"#!/usr/bin/env bash\necho {weekday}\n", encoding="utf-8", newline="\n")
    fake_date.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}

    result = subprocess.run(["bash", "-c", command], env=env, capture_output=True, text=True)

    assert result.returncode == 0
    assert ("DRILL" in result.stdout) is runs


def test_production_postgres_has_room_for_parallel_index_builds():
    compose = COMPOSE.read_text(encoding="utf-8")
    service = compose.split("\n  postgres:\n", 1)[1].split("\n  redis:\n", 1)[0]
    assert "\n    shm_size: 1g\n" in service
