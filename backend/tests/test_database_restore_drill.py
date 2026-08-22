"""Safety contract for the isolated database restore drill."""

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "test_database_restore.sh"
BACKUP_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "backup_database.ps1"


def test_restore_drill_never_references_production_resources():
    text = SCRIPT.read_text(encoding="utf-8")

    assert "--network none" in text
    assert '"published_ports": false' in text
    assert '"schema_version": 2' in text
    assert '"host_bind_mounts": false' in text
    assert '"production_volumes": false' in text
    assert '"ephemeral_database_volume": true' in text
    assert "infohub-restore-drill-" in text
    assert 'docker rm -f -v "$CONTAINER_NAME"' in text
    assert "unexpectedly has host bind mounts" in text
    assert "reused a pre-existing volume" in text
    assert "docker compose" not in text
    assert "infohub-postgres" not in text
    assert "postgres_data" not in text
    assert "--expected-sha256" in text
    assert "evidence target already exists" in text
    assert "MSYS_NO_PATHCONV=1" in text
    assert 'DOCKER_BACKUP_PATH="$(cygpath -w "$BACKUP_PATH")"' in text


def test_owner_backup_has_no_embedded_password_and_pins_artifact():
    text = BACKUP_SCRIPT.read_text(encoding="utf-8")

    assert 'PGPASSWORD = "changeme"' not in text
    assert "--no-password" in text
    assert ".partial" in text
    assert "Get-FileHash" in text
    assert "SHA-256" in text


@pytest.mark.skipif(os.name == "nt", reason="GNU restore plan contract runs in CI")
def test_plain_sql_dry_run_is_read_only_and_machine_readable(tmp_path):
    bash = shutil.which("bash")
    assert bash is not None
    backup = tmp_path / "infohub_ai_fixture.sql"
    backup.write_text("-- PostgreSQL database dump\nSELECT 1;\n", encoding="utf-8")

    result = subprocess.run(
        [bash, str(SCRIPT), "--backup", str(backup)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    prefix = "DATABASE_RESTORE_DRILL_PLAN="
    assert result.stdout.startswith(prefix)
    plan = json.loads(result.stdout.removeprefix(prefix))
    assert plan["format"] == "plain_sql"
    assert plan["fresh"] is True
    assert plan["execute"] is False
    assert len(plan["sha256"]) == 64
    assert list(tmp_path.iterdir()) == [backup]


@pytest.mark.skipif(os.name == "nt", reason="GNU restore plan contract runs in CI")
def test_execute_requires_hash_before_docker_or_evidence(tmp_path):
    bash = shutil.which("bash")
    assert bash is not None
    backup = tmp_path / "infohub_ai_fixture.sql"
    evidence = tmp_path / "evidence.json"
    backup.write_text("-- PostgreSQL database dump\nSELECT 1;\n", encoding="utf-8")

    result = subprocess.run(
        [
            bash,
            str(SCRIPT),
            "--backup",
            str(backup),
            "--execute",
            "--evidence",
            str(evidence),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "execute requires --expected-sha256" in result.stderr
    assert not evidence.exists()
