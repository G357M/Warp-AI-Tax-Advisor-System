"""Deterministic production-readiness checks for the embedding runtime."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Callable, Mapping

from core.embedding_model_loader import CachedModelLocation


AUDIT_SCHEMA_VERSION = 1
DEFAULT_MAX_CACHE_FILES = 2_048
DEFAULT_MAX_CACHE_BYTES = 16 * 1024**3
PROBE_TEXTS = (
    "საქართველოს საგადასახადო კოდექსი",
    "Налоговый кодекс Грузии",
    "Georgian Tax Code",
)
PROBE_SET_SHA256 = hashlib.sha256(
    json.dumps(
        PROBE_TEXTS,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()


class ProductionReadinessError(RuntimeError):
    """Raised when a production-readiness invariant is not satisfied."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cache_trust_root(model_dir: Path, source: str) -> Path:
    """Allow normal Hugging Face snapshot symlinks, but not arbitrary escapes."""

    resolved = model_dir.resolve(strict=True)
    if source != "cache":
        return resolved

    for candidate in (resolved, *resolved.parents):
        if candidate.name == "snapshots":
            return candidate.parent.resolve(strict=True)
    return resolved


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def build_cache_manifest(
    model_dir: str | Path,
    *,
    source: str,
    max_files: int = DEFAULT_MAX_CACHE_FILES,
    max_total_bytes: int = DEFAULT_MAX_CACHE_BYTES,
) -> dict[str, Any]:
    """Hash one resolved model snapshot with explicit size and file bounds."""

    if max_files <= 0 or max_total_bytes <= 0:
        raise ValueError("cache audit bounds must be positive")

    root = Path(model_dir).resolve(strict=True)
    if not root.is_dir():
        raise ProductionReadinessError("resolved embedding cache is not a directory")

    trust_root = _cache_trust_root(root, source)
    entries: list[dict[str, Any]] = []
    total_bytes = 0

    paths = sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix())
    for path in paths:
        relative_path = path.relative_to(root).as_posix()
        if path.is_symlink():
            try:
                target = path.resolve(strict=True)
            except FileNotFoundError as exc:
                raise ProductionReadinessError(
                    f"embedding cache contains a broken symlink: {relative_path}"
                ) from exc
            if not _is_relative_to(target, trust_root):
                raise ProductionReadinessError(
                    f"embedding cache symlink escapes its model repository: {relative_path}"
                )
            if not target.is_file():
                raise ProductionReadinessError(
                    f"embedding cache symlink is not a regular file: {relative_path}"
                )
        elif path.is_dir():
            continue
        elif not path.is_file():
            raise ProductionReadinessError(
                f"embedding cache contains a non-regular entry: {relative_path}"
            )

        size = path.stat().st_size
        total_bytes += size
        if len(entries) + 1 > max_files:
            raise ProductionReadinessError(
                f"embedding cache exceeds the {max_files}-file audit bound"
            )
        if total_bytes > max_total_bytes:
            raise ProductionReadinessError(
                f"embedding cache exceeds the {max_total_bytes}-byte audit bound"
            )
        entries.append(
            {
                "path": relative_path,
                "bytes": size,
                "sha256": _sha256_file(path),
            }
        )

    relative_paths = {entry["path"] for entry in entries}
    filenames = {Path(path).name for path in relative_paths}
    missing_assets = []
    for required in ("config.json", "modules.json"):
        if required not in relative_paths:
            missing_assets.append(required)
    if not any(
        name == "tokenizer.json"
        or name == "tokenizer.model"
        or name == "sentencepiece.bpe.model"
        or name == "vocab.txt"
        for name in filenames
    ):
        missing_assets.append("tokenizer asset")
    if not any(
        name.endswith(".safetensors") or name == "pytorch_model.bin"
        for name in filenames
    ):
        missing_assets.append("model weights")
    if missing_assets:
        raise ProductionReadinessError(
            "embedding cache is missing required assets: " + ", ".join(missing_assets)
        )

    manifest_payload = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "files": entries,
    }
    manifest_sha256 = hashlib.sha256(
        json.dumps(
            manifest_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return {
        "snapshot": root.name,
        "file_count": len(entries),
        "total_bytes": total_bytes,
        "manifest_sha256": manifest_sha256,
        "max_files": max_files,
        "max_total_bytes": max_total_bytes,
        "files": entries,
    }


def _embedding_rows(value: Any) -> list[list[float]]:
    if hasattr(value, "tolist"):
        value = value.tolist()
    if not isinstance(value, (list, tuple)):
        raise ProductionReadinessError("embedding probe returned a non-matrix value")

    rows: list[list[float]] = []
    for row in value:
        if hasattr(row, "tolist"):
            row = row.tolist()
        if not isinstance(row, (list, tuple)):
            raise ProductionReadinessError("embedding probe returned a non-vector row")
        try:
            rows.append([float(item) for item in row])
        except (TypeError, ValueError) as exc:
            raise ProductionReadinessError(
                "embedding probe returned a non-numeric value"
            ) from exc
    return rows


def audit_embedding_probe(model: Any, *, expected_dimension: int) -> dict[str, Any]:
    """Run fixed multilingual probes twice and validate stable finite vectors."""

    if expected_dimension <= 0:
        raise ValueError("expected embedding dimension must be positive")

    def encode() -> list[list[float]]:
        try:
            return _embedding_rows(
                model.encode(
                    list(PROBE_TEXTS),
                    batch_size=len(PROBE_TEXTS),
                    show_progress_bar=False,
                    convert_to_numpy=True,
                )
            )
        except ProductionReadinessError:
            raise
        except Exception as exc:
            raise ProductionReadinessError("embedding probe execution failed") from exc

    first = encode()
    second = encode()
    if len(first) != len(PROBE_TEXTS) or len(second) != len(PROBE_TEXTS):
        raise ProductionReadinessError("embedding probe returned the wrong row count")

    min_norm = math.inf
    max_repeat_delta = 0.0
    for first_row, second_row in zip(first, second):
        if len(first_row) != expected_dimension or len(second_row) != expected_dimension:
            raise ProductionReadinessError(
                "embedding probe returned a vector with the wrong dimension"
            )
        if not all(math.isfinite(value) for value in (*first_row, *second_row)):
            raise ProductionReadinessError("embedding probe returned a non-finite value")
        norm = math.sqrt(sum(value * value for value in first_row))
        min_norm = min(min_norm, norm)
        max_repeat_delta = max(
            max_repeat_delta,
            max(abs(left - right) for left, right in zip(first_row, second_row)),
        )

    if min_norm <= 0.0:
        raise ProductionReadinessError("embedding probe returned a zero vector")
    if max_repeat_delta > 1e-6:
        raise ProductionReadinessError(
            "embedding probe is not repeatable within the 1e-6 tolerance"
        )

    return {
        "probe_count": len(PROBE_TEXTS),
        "probe_set_sha256": PROBE_SET_SHA256,
        "dimension": expected_dimension,
        "minimum_vector_norm": round(min_norm, 9),
        "maximum_repeat_delta": round(max_repeat_delta, 12),
        "repeat_tolerance": 1e-6,
    }


def audit_production_readiness(
    *,
    settings: Any,
    app: Any,
    torch_module: Any,
    embedding_generator: Any,
    cache_resolver: Callable[[str], CachedModelLocation | None],
    database_probe: Callable[[], None],
    deployed_commit: str,
    max_cache_files: int = DEFAULT_MAX_CACHE_FILES,
    max_cache_bytes: int = DEFAULT_MAX_CACHE_BYTES,
) -> dict[str, Any]:
    """Validate production policy, CPU runtime, cache integrity and DB reachability."""

    if settings.ENVIRONMENT != "production":
        raise ProductionReadinessError("ENVIRONMENT must be production")
    if settings.DEBUG is not False or app.docs_url is not None:
        raise ProductionReadinessError("debug routes must be disabled in production")
    if not settings.OPENAI_API_KEY:
        raise ProductionReadinessError("OPENAI_API_KEY must be configured")
    if settings.EMBEDDING_ALLOW_DOWNLOAD is not False:
        raise ProductionReadinessError("embedding downloads must be disabled")

    torch_version = str(torch_module.__version__)
    if not torch_version.endswith("+cpu"):
        raise ProductionReadinessError("PyTorch must use the pinned CPU-only wheel")
    if torch_module.version.cuda is not None or torch_module.cuda.is_available():
        raise ProductionReadinessError("CUDA must be absent from the production runtime")

    if embedding_generator.model is None:
        raise ProductionReadinessError("embedding model is unavailable")
    if embedding_generator.model_source not in {"cache", "local_path"}:
        raise ProductionReadinessError("embedding model was not loaded from local storage")

    location = cache_resolver(embedding_generator.model_name)
    if location is None:
        raise ProductionReadinessError("embedding cache could not be resolved locally")
    if location.source != embedding_generator.model_source:
        raise ProductionReadinessError(
            "loaded embedding source does not match the resolved cache source"
        )

    cache_manifest = build_cache_manifest(
        location.path,
        source=location.source,
        max_files=max_cache_files,
        max_total_bytes=max_cache_bytes,
    )
    probe = audit_embedding_probe(
        embedding_generator.model,
        expected_dimension=embedding_generator.dimension,
    )
    try:
        database_probe()
    except ProductionReadinessError:
        raise
    except Exception as exc:
        raise ProductionReadinessError("database SELECT 1 failed") from exc

    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "result": "pass",
        "deployed_commit": deployed_commit,
        "execution_profile": {
            "external_network_calls_allowed": False,
            "llm_calls_allowed": False,
            "postgresql_writes_allowed": False,
        },
        "application": {
            "environment": settings.ENVIRONMENT,
            "debug": settings.DEBUG,
            "docs_enabled": app.docs_url is not None,
            "openai_key_configured": bool(settings.OPENAI_API_KEY),
        },
        "torch": {
            "version": torch_version,
            "cuda_runtime": torch_module.version.cuda,
            "cuda_available": bool(torch_module.cuda.is_available()),
        },
        "embeddings": {
            "model_identifier": embedding_generator.model_name,
            "model_source": embedding_generator.model_source,
            "downloads_allowed": settings.EMBEDDING_ALLOW_DOWNLOAD,
            "cache": cache_manifest,
            "probe": probe,
        },
        "database": {"select_one": "pass"},
    }


def audit_summary(report: Mapping[str, Any], *, execute: bool) -> dict[str, Any]:
    cache = report["embeddings"]["cache"]
    probe = report["embeddings"]["probe"]
    return {
        "schema_version": report["schema_version"],
        "result": report["result"],
        "deployed_commit": report["deployed_commit"],
        "model_identifier": report["embeddings"]["model_identifier"],
        "model_source": report["embeddings"]["model_source"],
        "embedding_dimension": probe["dimension"],
        "cache_file_count": cache["file_count"],
        "cache_total_bytes": cache["total_bytes"],
        "cache_manifest_sha256": cache["manifest_sha256"],
        "probe_set_sha256": probe["probe_set_sha256"],
        "execute": execute,
    }
