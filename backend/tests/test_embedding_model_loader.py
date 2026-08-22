"""Regression tests for cache-first embedding model startup."""

from pathlib import Path
from unittest.mock import patch

import pytest

from core.embedding_model_loader import (
    CachedModelLocation,
    EmbeddingModelUnavailable,
    load_embedding_model,
    resolve_cached_model,
)


def test_existing_local_model_path_never_calls_snapshot_resolver():
    model_dir = Path("local-model")
    resolved_model_dir = Path("resolved-local-model")

    def unexpected_snapshot_resolver(**_kwargs):
        raise AssertionError("Hub cache resolver must not be called for local paths")

    with (
        patch.object(Path, "is_dir", return_value=True),
        patch.object(Path, "resolve", return_value=resolved_model_dir),
    ):
        location = resolve_cached_model(
            str(model_dir),
            snapshot_resolver=unexpected_snapshot_resolver,
        )

    assert location == CachedModelLocation(
        path=str(resolved_model_dir),
        source="local_path",
    )


def test_cached_snapshot_is_resolved_without_network():
    snapshot_dir = Path("C:/cache/snapshots/abc123")
    calls = []

    def snapshot_resolver(**kwargs):
        calls.append(kwargs)
        return str(snapshot_dir)

    def is_snapshot_directory(candidate):
        return candidate == snapshot_dir

    with patch.object(Path, "is_dir", autospec=True, side_effect=is_snapshot_directory):
        location = resolve_cached_model(
            "sentence-transformers/example",
            snapshot_resolver=snapshot_resolver,
        )

    assert calls == [
        {
            "repo_id": "sentence-transformers/example",
            "local_files_only": True,
        }
    ]
    assert location == CachedModelLocation(
        path=str(snapshot_dir),
        source="cache",
    )


def test_cached_model_is_loaded_by_resolved_path():
    loader_calls = []
    expected_model = object()

    def model_loader(path):
        loader_calls.append(path)
        return expected_model

    loaded = load_embedding_model(
        "sentence-transformers/example",
        model_loader=model_loader,
        allow_download=False,
        cache_resolver=lambda _name: CachedModelLocation(
            path="/cache/snapshots/abc123",
            source="cache",
        ),
    )

    assert loader_calls == ["/cache/snapshots/abc123"]
    assert loaded.model is expected_model
    assert loaded.source == "cache"


def test_cache_miss_fails_fast_when_downloads_are_disabled():
    with pytest.raises(EmbeddingModelUnavailable, match="not cached"):
        load_embedding_model(
            "sentence-transformers/example",
            model_loader=lambda _path: object(),
            allow_download=False,
            cache_resolver=lambda _name: None,
        )


def test_cache_miss_can_use_explicit_online_bootstrap():
    loader_calls = []
    expected_model = object()

    def model_loader(path):
        loader_calls.append(path)
        return expected_model

    loaded = load_embedding_model(
        "sentence-transformers/example",
        model_loader=model_loader,
        allow_download=True,
        cache_resolver=lambda _name: None,
    )

    assert loader_calls == ["sentence-transformers/example"]
    assert loaded.model is expected_model
    assert loaded.source == "download"


def test_corrupt_cache_does_not_fall_back_online_when_disabled():
    def broken_loader(_path):
        raise ValueError("invalid model")

    with pytest.raises(EmbeddingModelUnavailable, match="Cached embedding model"):
        load_embedding_model(
            "sentence-transformers/example",
            model_loader=broken_loader,
            allow_download=False,
            cache_resolver=lambda _name: CachedModelLocation(
                path="/cache/snapshots/broken",
                source="cache",
            ),
        )


def test_production_compose_disables_embedding_downloads_by_default():
    repository_root = Path(__file__).resolve().parents[2]
    compose = (repository_root / "docker-compose.yml").read_text(encoding="utf-8")

    assert (
        "EMBEDDING_ALLOW_DOWNLOAD=${EMBEDDING_ALLOW_DOWNLOAD:-false}" in compose
    )


def test_deploy_preflight_requires_a_cached_embedding_model():
    repository_root = Path(__file__).resolve().parents[2]
    deploy_script = (repository_root / "scripts" / "deploy_production.sh").read_text(
        encoding="utf-8"
    )

    assert "settings.EMBEDDING_ALLOW_DOWNLOAD" in deploy_script
    assert "embeddings_generator.model_source in {'cache', 'local_path'}" in deploy_script
