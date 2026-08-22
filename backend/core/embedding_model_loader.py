"""Deterministic loading policy for cached embedding models."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal, Optional


logger = logging.getLogger(__name__)

ModelSource = Literal["local_path", "cache", "download"]


class EmbeddingModelUnavailable(RuntimeError):
    """Raised when the configured model cannot be loaded under the active policy."""


@dataclass(frozen=True)
class CachedModelLocation:
    """A local directory that can be loaded without contacting the model hub."""

    path: str
    source: Literal["local_path", "cache"]


@dataclass(frozen=True)
class LoadedEmbeddingModel:
    """A loaded model together with its non-sensitive provenance."""

    model: Any
    source: ModelSource


def resolve_cached_model(
    model_name_or_path: str,
    *,
    snapshot_resolver: Optional[Callable[..., str]] = None,
) -> Optional[CachedModelLocation]:
    """Resolve a local model or cached Hub snapshot without network access."""

    local_candidate = Path(model_name_or_path).expanduser()
    if local_candidate.is_dir():
        return CachedModelLocation(
            path=str(local_candidate.resolve()),
            source="local_path",
        )

    if snapshot_resolver is None:
        from huggingface_hub import snapshot_download

        snapshot_resolver = snapshot_download

    try:
        snapshot_path = snapshot_resolver(
            repo_id=model_name_or_path,
            local_files_only=True,
        )
    except Exception as exc:
        logger.info(
            "Embedding model is not available in the local cache: %s (%s)",
            model_name_or_path,
            type(exc).__name__,
        )
        return None

    if not snapshot_path or not Path(snapshot_path).is_dir():
        logger.warning(
            "Embedding cache resolver returned no usable directory for %s",
            model_name_or_path,
        )
        return None

    return CachedModelLocation(path=str(snapshot_path), source="cache")


def load_embedding_model(
    model_name_or_path: str,
    *,
    model_loader: Callable[[str], Any],
    allow_download: bool,
    cache_resolver: Callable[[str], Optional[CachedModelLocation]] = resolve_cached_model,
) -> LoadedEmbeddingModel:
    """Load from a verified local path first, optionally falling back to the Hub."""

    cached_location = cache_resolver(model_name_or_path)
    if cached_location is not None:
        try:
            return LoadedEmbeddingModel(
                model=model_loader(cached_location.path),
                source=cached_location.source,
            )
        except Exception as exc:
            if not allow_download:
                raise EmbeddingModelUnavailable(
                    "Cached embedding model could not be loaded and downloads are disabled"
                ) from exc
            logger.warning(
                "Cached embedding model could not be loaded; online repair is enabled",
                exc_info=True,
            )

    if not allow_download:
        raise EmbeddingModelUnavailable(
            "Embedding model is not cached and downloads are disabled"
        )

    try:
        return LoadedEmbeddingModel(
            model=model_loader(model_name_or_path),
            source="download",
        )
    except Exception as exc:
        raise EmbeddingModelUnavailable(
            "Embedding model could not be loaded from the model hub"
        ) from exc
