#!/usr/bin/env python
"""Audit production policy, embedding cache integrity and runtime readiness.

The default invocation is read-only and prints a machine-readable plan. Evidence
is written only after the operator supplies the exact cache hash, file count and
byte count observed in that plan.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from core.production_readiness import (  # noqa: E402
    DEFAULT_MAX_CACHE_BYTES,
    DEFAULT_MAX_CACHE_FILES,
    ProductionReadinessError,
    audit_production_readiness,
    audit_summary,
)


COMMIT_RE = re.compile(r"^[0-9a-f]{7,40}$")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True, help="Deployed Git commit SHA")
    parser.add_argument("--max-cache-files", type=int, default=DEFAULT_MAX_CACHE_FILES)
    parser.add_argument("--max-cache-bytes", type=int, default=DEFAULT_MAX_CACHE_BYTES)
    parser.add_argument("--execute", action="store_true", help="Write pinned evidence")
    parser.add_argument("--output", type=Path, help="New evidence JSON path")
    parser.add_argument("--expected-cache-sha256")
    parser.add_argument("--expected-cache-files", type=int)
    parser.add_argument("--expected-cache-bytes", type=int)
    return parser


def _validate_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if not COMMIT_RE.fullmatch(args.commit):
        parser.error("--commit must be a 7-40 character lowercase hexadecimal SHA")
    if args.max_cache_files <= 0 or args.max_cache_bytes <= 0:
        parser.error("cache audit bounds must be positive")
    if not args.execute:
        if args.output is not None or any(
            value is not None
            for value in (
                args.expected_cache_sha256,
                args.expected_cache_files,
                args.expected_cache_bytes,
            )
        ):
            parser.error("evidence arguments require --execute")
        return
    if args.output is None:
        parser.error("--execute requires --output")
    if not args.expected_cache_sha256 or not re.fullmatch(
        r"[0-9a-f]{64}", args.expected_cache_sha256
    ):
        parser.error("--execute requires a lowercase 64-character cache SHA-256")
    if args.expected_cache_files is None or args.expected_cache_files < 1:
        parser.error("--execute requires --expected-cache-files")
    if args.expected_cache_bytes is None or args.expected_cache_bytes < 1:
        parser.error("--execute requires --expected-cache-bytes")


def _verify_expected_scope(args: argparse.Namespace, report: dict[str, Any]) -> None:
    cache = report["embeddings"]["cache"]
    expected = (
        ("cache SHA-256", args.expected_cache_sha256, cache["manifest_sha256"]),
        ("cache file count", args.expected_cache_files, cache["file_count"]),
        ("cache byte count", args.expected_cache_bytes, cache["total_bytes"]),
    )
    for label, wanted, actual in expected:
        if wanted != actual:
            raise ProductionReadinessError(
                f"{label} changed after review: expected {wanted}, got {actual}"
            )


def _write_evidence(output: Path, report: dict[str, Any]) -> None:
    if output.exists() or output.is_symlink():
        raise ProductionReadinessError("evidence target already exists")
    parent = output.parent.resolve(strict=True)
    if not parent.is_dir() or output.parent.is_symlink():
        raise ProductionReadinessError("evidence parent must be a real directory")
    if os.name != "nt" and stat.S_IMODE(parent.stat().st_mode) & 0o077:
        raise ProductionReadinessError(
            "evidence parent must not be accessible to group or other users"
        )

    evidence = dict(report)
    evidence["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    payload = (
        json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(output, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
    except Exception:
        try:
            output.unlink()
        except OSError:
            pass
        raise
    if os.name != "nt":
        output.chmod(0o600)


def _runtime_report(args: argparse.Namespace) -> dict[str, Any]:
    # Enforce offline behavior before importing libraries that know about the Hub.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"

    import torch
    from sqlalchemy import text

    from api.main import app
    from core.config import settings
    from core.database import SessionLocal
    from core.embedding_model_loader import resolve_cached_model
    from rag.embeddings import embeddings_generator

    def database_probe() -> None:
        database = SessionLocal()
        try:
            value = database.execute(text("SELECT 1")).scalar()
            if value != 1:
                raise ProductionReadinessError("database SELECT 1 returned no value")
        finally:
            database.close()

    return audit_production_readiness(
        settings=settings,
        app=app,
        torch_module=torch,
        embedding_generator=embeddings_generator,
        cache_resolver=resolve_cached_model,
        database_probe=database_probe,
        deployed_commit=args.commit,
        max_cache_files=args.max_cache_files,
        max_cache_bytes=args.max_cache_bytes,
    )


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    _validate_args(args, parser)

    try:
        report = _runtime_report(args)
        summary = audit_summary(report, execute=args.execute)
        if args.execute:
            _verify_expected_scope(args, report)
            _write_evidence(args.output, report)
            summary["evidence_path"] = str(args.output)
        print(
            "PRODUCTION_READINESS_AUDIT="
            + json.dumps(summary, ensure_ascii=False, sort_keys=True)
        )
        return 0
    except (OSError, ProductionReadinessError) as exc:
        print(f"Production readiness audit failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
