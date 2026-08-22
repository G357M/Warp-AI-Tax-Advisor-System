"""Contracts for the deterministic production-readiness/cache audit."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.embedding_model_loader import CachedModelLocation
from core.production_readiness import (
    PROBE_TEXTS,
    ProductionReadinessError,
    audit_embedding_probe,
    audit_production_readiness,
    build_cache_manifest,
)
from scripts import audit_production_readiness as audit_cli


class _StableModel:
    def __init__(self, rows=None):
        self.rows = rows or [[1.0, 2.0, 3.0] for _ in PROBE_TEXTS]

    def encode(self, texts, **kwargs):
        assert texts == list(PROBE_TEXTS)
        assert kwargs == {
            "batch_size": len(PROBE_TEXTS),
            "show_progress_bar": False,
            "convert_to_numpy": True,
        }
        return self.rows


class _DriftingModel(_StableModel):
    def __init__(self):
        super().__init__()
        self.calls = 0

    def encode(self, texts, **kwargs):
        rows = super().encode(texts, **kwargs)
        self.calls += 1
        return [[value + self.calls * 1e-3 for value in row] for row in rows]


class _BrokenModel:
    def encode(self, _texts, **_kwargs):
        raise RuntimeError("broken model")


def _model_cache(root: Path) -> Path:
    root.mkdir()
    files = {
        "config.json": b"{}\n",
        "modules.json": b"[]\n",
        "tokenizer.json": b'{"version":"1.0"}\n',
        "model.safetensors": b"deterministic-test-weights",
    }
    for name, content in files.items():
        (root / name).write_bytes(content)
    return root


def _settings(**overrides):
    values = {
        "ENVIRONMENT": "production",
        "DEBUG": False,
        "OPENAI_API_KEY": "configured-not-exported",
        "EMBEDDING_ALLOW_DOWNLOAD": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _torch():
    return SimpleNamespace(
        __version__="2.13.0+cpu",
        version=SimpleNamespace(cuda=None),
        cuda=SimpleNamespace(is_available=lambda: False),
    )


def _generator(model):
    return SimpleNamespace(
        model=model,
        model_name="sentence-transformers/test-model",
        model_source="local_path",
        dimension=3,
    )


def test_cache_manifest_is_content_addressed_and_order_independent(tmp_path):
    first = _model_cache(tmp_path / "first")
    second = _model_cache(tmp_path / "second")

    first_manifest = build_cache_manifest(first, source="local_path")
    second_manifest = build_cache_manifest(second, source="local_path")

    assert first_manifest["file_count"] == 4
    assert first_manifest["total_bytes"] > 0
    assert first_manifest["manifest_sha256"] == second_manifest["manifest_sha256"]
    assert len(first_manifest["manifest_sha256"]) == 64

    (second / "config.json").write_text('{"changed":true}\n', encoding="utf-8")
    changed_manifest = build_cache_manifest(second, source="local_path")
    assert changed_manifest["manifest_sha256"] != first_manifest["manifest_sha256"]


def test_cache_manifest_requires_loadable_model_assets(tmp_path):
    cache = _model_cache(tmp_path / "cache")
    (cache / "modules.json").unlink()

    with pytest.raises(ProductionReadinessError, match="modules.json"):
        build_cache_manifest(cache, source="local_path")


@pytest.mark.skipif(os.name == "nt", reason="symlink creation is not portable")
def test_cache_manifest_rejects_symlink_escape(tmp_path):
    cache = _model_cache(tmp_path / "cache")
    external = tmp_path / "external-modules.json"
    external.write_text("[]\n", encoding="utf-8")
    (cache / "modules.json").unlink()
    (cache / "modules.json").symlink_to(external)

    with pytest.raises(ProductionReadinessError, match="escapes"):
        build_cache_manifest(cache, source="local_path")


def test_cache_manifest_enforces_explicit_bounds(tmp_path):
    cache = _model_cache(tmp_path / "cache")

    with pytest.raises(ProductionReadinessError, match="file audit bound"):
        build_cache_manifest(cache, source="local_path", max_files=3)
    with pytest.raises(ProductionReadinessError, match="byte audit bound"):
        build_cache_manifest(cache, source="local_path", max_total_bytes=3)


def test_embedding_probe_checks_dimension_finiteness_and_repeatability():
    probe = audit_embedding_probe(_StableModel(), expected_dimension=3)

    assert probe["probe_count"] == 3
    assert probe["dimension"] == 3
    assert probe["minimum_vector_norm"] > 0
    assert probe["maximum_repeat_delta"] == 0

    with pytest.raises(ProductionReadinessError, match="wrong dimension"):
        audit_embedding_probe(_StableModel([[1.0, 2.0]] * 3), expected_dimension=3)
    with pytest.raises(ProductionReadinessError, match="non-finite"):
        audit_embedding_probe(
            _StableModel([[1.0, float("nan"), 3.0]] * 3),
            expected_dimension=3,
        )
    with pytest.raises(ProductionReadinessError, match="not repeatable"):
        audit_embedding_probe(_DriftingModel(), expected_dimension=3)
    with pytest.raises(ProductionReadinessError, match="execution failed"):
        audit_embedding_probe(_BrokenModel(), expected_dimension=3)


def test_production_audit_is_cache_only_read_only_and_complete(tmp_path):
    cache = _model_cache(tmp_path / "cache")
    database_calls = []
    generator = _generator(_StableModel())

    report = audit_production_readiness(
        settings=_settings(),
        app=SimpleNamespace(docs_url=None),
        torch_module=_torch(),
        embedding_generator=generator,
        cache_resolver=lambda model_name: CachedModelLocation(
            path=str(cache), source="local_path"
        ),
        database_probe=lambda: database_calls.append("SELECT 1"),
        deployed_commit="abcdef123456",
    )

    assert database_calls == ["SELECT 1"]
    assert report["result"] == "pass"
    assert report["execution_profile"] == {
        "external_network_calls_allowed": False,
        "llm_calls_allowed": False,
        "postgresql_writes_allowed": False,
    }
    assert report["embeddings"]["model_source"] == "local_path"
    assert report["embeddings"]["cache"]["file_count"] == 4
    assert report["database"]["select_one"] == "pass"


def test_production_audit_fails_before_database_when_downloads_are_enabled(tmp_path):
    cache = _model_cache(tmp_path / "cache")
    database_calls = []

    with pytest.raises(ProductionReadinessError, match="downloads must be disabled"):
        audit_production_readiness(
            settings=_settings(EMBEDDING_ALLOW_DOWNLOAD=True),
            app=SimpleNamespace(docs_url=None),
            torch_module=_torch(),
            embedding_generator=_generator(_StableModel()),
            cache_resolver=lambda _name: CachedModelLocation(
                path=str(cache), source="local_path"
            ),
            database_probe=lambda: database_calls.append("SELECT 1"),
            deployed_commit="abcdef123456",
        )

    assert database_calls == []


def test_evidence_write_requires_exact_scope_and_refuses_overwrite(tmp_path):
    report = {
        "embeddings": {
            "cache": {
                "manifest_sha256": "a" * 64,
                "file_count": 4,
                "total_bytes": 123,
            }
        }
    }
    output_dir = tmp_path / "evidence"
    output_dir.mkdir()
    if os.name != "nt":
        output_dir.chmod(0o700)
    output = output_dir / "readiness.json"
    args = SimpleNamespace(
        expected_cache_sha256="a" * 64,
        expected_cache_files=4,
        expected_cache_bytes=123,
    )

    audit_cli._verify_expected_scope(args, report)
    audit_cli._write_evidence(output, report)

    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["generated_at_utc"].endswith("+00:00")
    if os.name != "nt":
        assert stat.S_IMODE(output.stat().st_mode) == 0o600
    with pytest.raises(ProductionReadinessError, match="already exists"):
        audit_cli._write_evidence(output, report)

    args.expected_cache_sha256 = hashlib.sha256(b"changed").hexdigest()
    with pytest.raises(ProductionReadinessError, match="changed after review"):
        audit_cli._verify_expected_scope(args, report)


def test_deploy_and_ci_use_the_versioned_audit():
    repository_root = Path(__file__).resolve().parents[2]
    deploy_script = (repository_root / "scripts" / "deploy_production.sh").read_text(
        encoding="utf-8"
    )
    workflow = (repository_root / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )

    assert "python scripts/audit_production_readiness.py" in deploy_script
    assert 'settings.EMBEDDING_ALLOW_DOWNLOAD is False' not in deploy_script
    assert "scripts/audit_production_readiness.py" in workflow
    assert "tests/test_production_readiness_audit.py" in workflow
