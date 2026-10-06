"""Runs every SQL query of the restore drill against a real PostgreSQL.

The unit contracts in test_db_restore_drill.py fake the docker CLI and never
parse SQL; the first production drill then failed on a query PostgreSQL
rejected ("char" || unknown). Here the fake docker forwards each psql call,
for both the live and the drill side, to a scratch database on the CI
pgvector service.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY_ROOT / "ops" / "restore-drill-infohub-db.sh"
ADMIN_URL = os.getenv("DATABASE_URL", "")

# Opt-in, but once enabled a missing tool is a failure, not a silent skip.
pytestmark = pytest.mark.skipif(
    os.getenv("RESTORE_DRILL_POSTGRES_TESTS") != "1",
    reason="requires the disposable CI PostgreSQL job",
)

FIXTURE_SQL = """
CREATE EXTENSION vector;
CREATE TABLE documents (id serial PRIMARY KEY, title text);
CREATE TABLE users (id serial PRIMARY KEY, email text);
CREATE TABLE decision_facts (id serial PRIMARY KEY, document_id int REFERENCES documents(id));
CREATE TABLE document_chunks (
    id serial PRIMARY KEY,
    document_id int REFERENCES documents(id),
    embedding vector(3)
);
CREATE INDEX document_chunks_embedding_idx ON document_chunks USING hnsw (embedding vector_cosine_ops);
CREATE VIEW recent_documents AS SELECT id FROM documents;
INSERT INTO documents (title) SELECT 'd' || g FROM generate_series(1, 4) g;
INSERT INTO users (email) VALUES ('a@example.test');
INSERT INTO decision_facts (document_id) VALUES (1), (2);
INSERT INTO document_chunks (document_id, embedding)
    SELECT 1 + g % 4, ARRAY[g, g + 1, g + 2]::vector FROM generate_series(1, 8) g;
"""

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
shift
case "$1" in
  pg_isready|pg_restore) exit 0 ;;
  psql) exec psql "$DRILL_TEST_DB_URL" -XAtq -v ON_ERROR_STOP=1 -c "${@: -1}" ;;
esac
exit 1
"""


def _psql(url: str, sql: str) -> None:
    subprocess.run(["psql", url, "-XAtq", "-v", "ON_ERROR_STOP=1", "-c", sql], check=True, capture_output=True)


@pytest.fixture
def scratch_db():
    name = f"restore_drill_{uuid4().hex[:12]}"
    _psql(ADMIN_URL, f"CREATE DATABASE {name}")
    url = ADMIN_URL.rsplit("/", 1)[0] + f"/{name}"
    try:
        subprocess.run(["psql", url, "-Xq", "-v", "ON_ERROR_STOP=1"], input=FIXTURE_SQL, text=True, check=True, capture_output=True)
        yield url
    finally:
        _psql(ADMIN_URL, f"DROP DATABASE IF EXISTS {name}")


def test_drill_queries_run_on_real_postgres(tmp_path, scratch_db):
    assert ADMIN_URL, "DATABASE_URL must point at the CI PostgreSQL service"
    missing = [tool for tool in ("bash", "flock", "psql") if shutil.which(tool) is None]
    assert not missing, f"missing tools: {missing}"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(FAKE_DOCKER, encoding="utf-8", newline="\n")
    docker.chmod(0o755)

    backups = tmp_path / "backups"
    backups.mkdir()
    dump = backups / "infohub_ai-20261007T013000Z.dump"
    dump.write_bytes(b"PGDMP-fake-archive")
    subprocess.run(
        f"sha256sum {dump.name} > {dump.name}.sha256", shell=True, cwd=backups, check=True
    )

    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "INFOHUB_DB_BACKUP_DIR": str(backups),
        "INFOHUB_DB_BACKUP_LOCK": str(tmp_path / "backup.lock"),
        "DRILL_TEST_DB_URL": scratch_db,
    }
    result = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True)

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "ERROR" not in output
    objects = output.split("restored [", 1)[1].split("]", 1)[0].split()
    assert sorted(objects) == ["S:4", "i:5", "r:4", "v:1"]
    assert "schema object counts differ" not in output
    assert "vector " in output
    assert "pgvector ok: 8 chunks with embeddings, nearest-neighbour query returned 5 rows" in output
    assert (backups / "restore-drill-last.txt").read_text(encoding="utf-8").startswith("ok ")
