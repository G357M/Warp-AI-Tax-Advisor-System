import os
import subprocess
import sys
from pathlib import Path

import scripts.scrape_infohub_api as runner


class _FakeResult:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value


class _FakeSession:
    def __init__(self, value=0, error=None):
        self.value = value
        self.error = error
        self.statements = []
        self.closed = False

    def execute(self, statement):
        self.statements.append(str(statement))
        if self.error:
            raise self.error
        return _FakeResult(self.value)

    def close(self):
        self.closed = True


def test_vector_count_uses_active_embedding_column_and_closes_session(monkeypatch):
    session = _FakeSession(value=123)
    monkeypatch.setattr(runner, "SessionLocal", lambda: session)
    monkeypatch.setenv("INFOHUB_EMBEDDING_V2", "1")

    assert runner._get_vector_count() == 123
    assert session.statements == [
        "SELECT COUNT(*) FROM document_chunks WHERE embedding_v2 IS NOT NULL"
    ]
    assert session.closed


def test_vector_count_defaults_to_primary_embedding_and_fails_soft(monkeypatch):
    session = _FakeSession(error=RuntimeError("database unavailable"))
    monkeypatch.setattr(runner, "SessionLocal", lambda: session)
    monkeypatch.delenv("INFOHUB_EMBEDDING_V2", raising=False)

    assert runner._get_vector_count() == 0
    assert session.statements == [
        "SELECT COUNT(*) FROM document_chunks WHERE embedding IS NOT NULL"
    ]
    assert session.closed


def test_importing_runner_does_not_import_rag_package():
    backend_dir = Path(__file__).resolve().parents[1]
    script_path = backend_dir / "scripts" / "scrape_infohub_api.py"
    probe = (
        "import runpy, sys; "
        f"runpy.run_path({str(script_path)!r}, run_name='scraper_import_probe'); "
        "assert not any(name == 'rag' or name.startswith('rag.') for name in sys.modules), "
        "sorted(name for name in sys.modules if name == 'rag' or name.startswith('rag.'))"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(backend_dir)

    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=backend_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
