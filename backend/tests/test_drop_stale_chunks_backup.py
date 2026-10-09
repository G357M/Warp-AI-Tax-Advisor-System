"""Contracts for ops/drop-stale-chunks-backup.sh."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY_ROOT / "ops" / "drop-stale-chunks-backup.sh"

needs_posix = pytest.mark.skipif(shutil.which("bash") is None, reason="requires bash")

# Answers the script's psql calls; every call is appended to calls.log.
FAKE_DOCKER = r"""#!/usr/bin/env bash
here="$(dirname "$0")"
sql="${@: -1}"
echo "$sql" >> "$here/calls.log"
case "$sql" in
  *to_regclass*) [[ -f "$here/table_exists" ]] && echo t || echo f ;;
  *'count(*)'*) echo 48210 ;;
  *pg_size_pretty*) echo "412 MB" ;;
  'DROP TABLE public.document_chunks_backup_20260630') rm -f "$here/table_exists" ;;
  *) exit 3 ;;
esac
"""


def _setup(tmp_path: Path, *, table: bool = True, backup_age_hours: float | None = 2, checksum: bool = True) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(FAKE_DOCKER, encoding="utf-8", newline="\n")
    docker.chmod(0o755)
    if table:
        (bin_dir / "table_exists").touch()
    backups = tmp_path / "backups"
    backups.mkdir()
    if backup_age_hours is not None:
        dump = backups / "infohub_ai-20261009T013000Z.dump"
        dump.write_bytes(b"PGDMP")
        if checksum:
            (backups / f"{dump.name}.sha256").write_text("x", encoding="utf-8")
        stamp = time.time() - backup_age_hours * 3600
        os.utime(dump, (stamp, stamp))


def _run(tmp_path: Path, *args: str) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "PATH": f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}",
        "INFOHUB_DB_BACKUP_DIR": str(tmp_path / "backups"),
    }
    return subprocess.run(["bash", str(SCRIPT), *args], env=env, capture_output=True, text=True)


def _dropped(tmp_path: Path) -> bool:
    log = tmp_path / "bin" / "calls.log"
    return log.exists() and any(l.startswith("DROP TABLE") for l in log.read_text(encoding="utf-8").splitlines())


@needs_posix
def test_dry_run_reports_and_does_not_drop(tmp_path):
    _setup(tmp_path)

    result = _run(tmp_path)

    assert result.returncode == 0, result.stderr
    assert "48210 rows, 412 MB" in result.stdout
    assert "dry run" in result.stdout
    assert not _dropped(tmp_path)


@needs_posix
def test_apply_drops_with_a_fresh_backup(tmp_path):
    _setup(tmp_path)

    result = _run(tmp_path, "--apply")

    assert result.returncode == 0, result.stderr
    assert _dropped(tmp_path)
    assert "dropped public.document_chunks_backup_20260630" in result.stdout


@needs_posix
@pytest.mark.parametrize(("age", "checksum"), [(None, True), (48, True), (2, False)])
def test_apply_refuses_without_a_fresh_checksummed_backup(tmp_path, age, checksum):
    _setup(tmp_path, backup_age_hours=age, checksum=checksum)

    result = _run(tmp_path, "--apply")

    assert result.returncode == 1
    assert "refusing" in result.stderr
    assert not _dropped(tmp_path)


@needs_posix
def test_missing_table_is_a_no_op(tmp_path):
    _setup(tmp_path, table=False)

    result = _run(tmp_path, "--apply")

    assert result.returncode == 0
    assert "nothing to do" in result.stdout
    assert not _dropped(tmp_path)


@needs_posix
def test_unknown_argument_is_rejected(tmp_path):
    _setup(tmp_path)

    assert _run(tmp_path, "--force").returncode == 2


def test_script_has_unix_line_endings():
    assert b"\r" not in SCRIPT.read_bytes()
