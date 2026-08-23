#!/usr/bin/env python3
"""Read-only production disk and Buildx cache pressure audit."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable, Protocol, Sequence


BUILDER_NAME_PATTERN = re.compile(r"^infohub-[A-Za-z0-9][A-Za-z0-9_.-]{0,55}$")
SIZE_PATTERN = re.compile(r"^(\d+(?:\.\d+)?)(b|kb|mb|gb|tb)$", re.IGNORECASE)
SIZE_MULTIPLIERS = {
    "b": 1,
    "kb": 1_000,
    "mb": 1_000_000,
    "gb": 1_000_000_000,
    "tb": 1_000_000_000_000,
}
MAX_CACHE_RECORDS = 10_000
MAX_CACHE_LINE_BYTES = 1_000_000


class StorageAuditError(RuntimeError):
    """Raised when storage state cannot be measured safely."""


class Runner(Protocol):
    def run(
        self,
        command: Sequence[str],
        *,
        check: bool = True,
        capture_output: bool = False,
    ) -> subprocess.CompletedProcess[str]: ...


class SubprocessRunner:
    def run(
        self,
        command: Sequence[str],
        *,
        check: bool = True,
        capture_output: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            list(command),
            check=check,
            capture_output=capture_output,
            text=True,
        )


@dataclass(frozen=True)
class StoragePolicy:
    root_path: Path = Path("/")
    min_free_bytes: int = 25_000_000_000
    max_used_percent: Decimal = Decimal("82")
    project_builder: str = "infohub-production-v1"
    max_project_cache_bytes: int = 18_000_000_000
    legacy_builder: str = "default"
    legacy_observation_ceiling_bytes: int = 60_000_000_000

    def validate(self) -> None:
        if self.root_path != Path("/"):
            raise StorageAuditError("storage audit root must be /")
        if self.min_free_bytes <= 0 or self.max_project_cache_bytes <= 0:
            raise StorageAuditError("storage thresholds must be positive")
        if self.legacy_observation_ceiling_bytes <= 0:
            raise StorageAuditError("legacy observation ceiling must be positive")
        if not Decimal("1") <= self.max_used_percent <= Decimal("99"):
            raise StorageAuditError("max used percent must be between 1 and 99")
        if not BUILDER_NAME_PATTERN.fullmatch(self.project_builder):
            raise StorageAuditError("invalid project Buildx builder name")
        if self.legacy_builder != "default":
            raise StorageAuditError("legacy observation is restricted to default")
        if self.project_builder == self.legacy_builder:
            raise StorageAuditError("project and legacy builders must differ")


@dataclass(frozen=True)
class CacheUsage:
    builder: str
    cache_bytes: int
    record_count: int


def parse_size(value: str) -> int:
    match = SIZE_PATTERN.fullmatch(value.strip())
    if not match:
        raise StorageAuditError("Buildx reported an invalid cache size")
    try:
        amount = Decimal(match.group(1))
    except InvalidOperation as error:  # pragma: no cover - regex filters syntax.
        raise StorageAuditError("Buildx reported an invalid cache size") from error
    if not amount.is_finite() or amount < 0:
        raise StorageAuditError("Buildx reported an invalid cache size")
    return int(amount * SIZE_MULTIPLIERS[match.group(2).lower()])


def _threshold_size(variable: str, default: str) -> int:
    value = os.getenv(variable, default)
    parsed = parse_size(value)
    if parsed <= 0:
        raise StorageAuditError(f"{variable} must be positive")
    return parsed


def _threshold_percent(variable: str, default: str) -> Decimal:
    value = os.getenv(variable, default)
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise StorageAuditError(f"{variable} must be numeric") from error
    if not parsed.is_finite():
        raise StorageAuditError(f"{variable} must be finite")
    return parsed


def policy_from_environment() -> StoragePolicy:
    return StoragePolicy(
        min_free_bytes=_threshold_size(
            "INFOHUB_STORAGE_MIN_FREE_SPACE",
            "25gb",
        ),
        max_used_percent=_threshold_percent(
            "INFOHUB_STORAGE_MAX_USED_PERCENT",
            "82",
        ),
        project_builder=os.getenv(
            "INFOHUB_BUILDX_BUILDER",
            "infohub-production-v1",
        ),
        max_project_cache_bytes=_threshold_size(
            "INFOHUB_PROJECT_CACHE_MAX_USED_SPACE",
            "18gb",
        ),
        legacy_observation_ceiling_bytes=_threshold_size(
            "INFOHUB_LEGACY_CACHE_OBSERVATION_CEILING",
            "60gb",
        ),
    )


def inspect_cache(builder: str, runner: Runner) -> CacheUsage:
    result = runner.run(
        [
            "docker",
            "buildx",
            "du",
            "--builder",
            builder,
            "--format",
            "json",
        ],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise StorageAuditError(f"Buildx cache inspection failed for {builder}")

    cache_bytes = 0
    record_count = 0
    for raw_line in result.stdout.splitlines():
        if not raw_line.strip():
            continue
        if len(raw_line.encode("utf-8")) > MAX_CACHE_LINE_BYTES:
            raise StorageAuditError("Buildx cache record exceeded the safety bound")
        record_count += 1
        if record_count > MAX_CACHE_RECORDS:
            raise StorageAuditError("Buildx cache record count exceeded the safety bound")
        try:
            record = json.loads(raw_line)
        except json.JSONDecodeError as error:
            raise StorageAuditError("Buildx cache output was not valid JSON") from error
        if not isinstance(record, dict) or not isinstance(record.get("Size"), str):
            raise StorageAuditError("Buildx cache record omitted its size")
        cache_bytes += parse_size(record["Size"])

    return CacheUsage(
        builder=builder,
        cache_bytes=cache_bytes,
        record_count=record_count,
    )


def audit_storage(
    policy: StoragePolicy,
    runner: Runner,
    *,
    disk_usage: Callable[[str], object] = shutil.disk_usage,
) -> dict[str, object]:
    policy.validate()
    usage = disk_usage(str(policy.root_path))
    total_bytes = int(getattr(usage, "total"))
    used_bytes = int(getattr(usage, "used"))
    free_bytes = int(getattr(usage, "free"))
    available_scale_bytes = used_bytes + free_bytes
    if (
        total_bytes <= 0
        or available_scale_bytes <= 0
        or min(used_bytes, free_bytes) < 0
        or max(used_bytes, free_bytes) > total_bytes
    ):
        raise StorageAuditError("filesystem usage was invalid")

    # Match df(1) semantics: reserved filesystem blocks are not available to
    # ordinary workloads and therefore must not dilute the pressure percent.
    used_percent = (
        Decimal(used_bytes) * Decimal("100") / Decimal(available_scale_bytes)
    )
    project = inspect_cache(policy.project_builder, runner)
    legacy = inspect_cache(policy.legacy_builder, runner)

    violations: list[str] = []
    if free_bytes < policy.min_free_bytes:
        violations.append("root_free_below_minimum")
    if used_percent > policy.max_used_percent:
        violations.append("root_used_above_maximum")
    if project.cache_bytes > policy.max_project_cache_bytes:
        violations.append("project_cache_above_maximum")
    if legacy.cache_bytes > policy.legacy_observation_ceiling_bytes:
        violations.append("legacy_cache_above_observation_ceiling")

    return {
        "schema_version": 1,
        "status": "healthy" if not violations else "pressure",
        "root": {
            "path": str(policy.root_path),
            "total_bytes": total_bytes,
            "used_bytes": used_bytes,
            "free_bytes": free_bytes,
            "used_percent": float(used_percent.quantize(Decimal("0.01"))),
            "min_free_bytes": policy.min_free_bytes,
            "max_used_percent": float(policy.max_used_percent),
        },
        "project_cache": {
            **asdict(project),
            "max_cache_bytes": policy.max_project_cache_bytes,
            "management": "bounded_named_builder",
        },
        "legacy_cache": {
            **asdict(legacy),
            "observation_ceiling_bytes": policy.legacy_observation_ceiling_bytes,
            "management": "observe_only_no_automatic_prune",
        },
        "violations": violations,
    }


def _parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description=__doc__)


def main(argv: Sequence[str] | None = None) -> int:
    _parser().parse_args(argv)
    try:
        report = audit_storage(
            policy_from_environment(),
            SubprocessRunner(),
        )
    except (AttributeError, OSError, StorageAuditError, TypeError, ValueError) as error:
        print(
            "PRODUCTION_STORAGE_AUDIT="
            + json.dumps(
                {"schema_version": 1, "status": "error", "error": "audit_failed"},
                sort_keys=True,
            )
        )
        print(f"Production storage audit failed: {error}", file=sys.stderr)
        return 2

    print("PRODUCTION_STORAGE_AUDIT=" + json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "healthy" else 1


if __name__ == "__main__":
    raise SystemExit(main())
