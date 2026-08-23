#!/usr/bin/env python3
"""Retire exact, reviewed InfoHub records from the legacy Buildx builder."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Protocol, Sequence


LEGACY_BUILDER = "default"
EXPECTED_DESCRIPTION = (
    "mount / from exec /bin/sh -c "
    "pip install --no-cache-dir -r requirements-production.txt"
)
DESCRIPTION_SHA256 = hashlib.sha256(EXPECTED_DESCRIPTION.encode("utf-8")).hexdigest()
RECORD_ID_PATTERN = re.compile(r"^[a-z0-9]{20,64}$")
SIZE_PATTERN = re.compile(r"^(\d{1,12}(?:\.\d{1,6})?)(b|kb|mb|gb|tb)$", re.IGNORECASE)
SIZE_MULTIPLIERS = {
    "b": 1,
    "kb": 1_000,
    "mb": 1_000_000,
    "gb": 1_000_000_000,
    "tb": 1_000_000_000_000,
}
MAX_RECORDS = 16


class LegacyRetirementError(RuntimeError):
    """Raised when a candidate or execution guard is not exact."""


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
class ReviewedRecord:
    record_id: str
    size_bytes: int
    created_at: str
    description_sha256: str
    record_type: str


@dataclass(frozen=True)
class RetirementPlan:
    builder: str
    records: tuple[ReviewedRecord, ...]
    record_count: int
    total_bytes: int
    plan_sha256: str


def _parse_size(value: str) -> int:
    match = SIZE_PATTERN.fullmatch(value.strip())
    if not match:
        raise LegacyRetirementError("Buildx reported an invalid cache size")
    try:
        amount = Decimal(match.group(1))
    except InvalidOperation as error:  # pragma: no cover - regex filters syntax.
        raise LegacyRetirementError("Buildx reported an invalid cache size") from error
    parsed = int(amount * SIZE_MULTIPLIERS[match.group(2).lower()])
    if parsed <= 0:
        raise LegacyRetirementError("candidate cache size must be positive")
    return parsed


def _inspect_command(record_id: str) -> list[str]:
    return [
        "docker",
        "buildx",
        "du",
        "--builder",
        LEGACY_BUILDER,
        "--filter",
        f"id={record_id}",
        "--format",
        "json",
    ]


def _load_record(
    record_id: str,
    runner: Runner,
    *,
    allow_missing: bool = False,
) -> ReviewedRecord | None:
    result = runner.run(
        _inspect_command(record_id),
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise LegacyRetirementError("legacy Buildx record inspection failed")

    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if not lines and allow_missing:
        return None
    if len(lines) != 1:
        raise LegacyRetirementError("exact ID selector did not return one record")
    try:
        raw = json.loads(lines[0])
    except json.JSONDecodeError as error:
        raise LegacyRetirementError("Buildx record output was not valid JSON") from error
    if not isinstance(raw, dict) or raw.get("ID") != record_id:
        raise LegacyRetirementError("Buildx returned a different record ID")

    description = raw.get("Description")
    if description != EXPECTED_DESCRIPTION:
        raise LegacyRetirementError("record is not an approved legacy InfoHub dependency layer")
    if raw.get("Type") != "regular":
        raise LegacyRetirementError("candidate record type is not regular")
    if raw.get("Reclaimable") is not True:
        raise LegacyRetirementError("candidate record is not reclaimable")
    if raw.get("Shared") is not False:
        raise LegacyRetirementError("candidate record is shared")
    if raw.get("Mutable") is not False:
        raise LegacyRetirementError("candidate record is mutable")
    if not isinstance(raw.get("CreatedAt"), str) or not raw["CreatedAt"].strip():
        raise LegacyRetirementError("candidate record has no creation timestamp")
    if not isinstance(raw.get("Size"), str):
        raise LegacyRetirementError("candidate record has no size")

    return ReviewedRecord(
        record_id=record_id,
        size_bytes=_parse_size(raw["Size"]),
        created_at=raw["CreatedAt"],
        description_sha256=DESCRIPTION_SHA256,
        record_type="regular",
    )


def _plan_hash(builder: str, records: Sequence[ReviewedRecord]) -> str:
    payload = {
        "builder": builder,
        "records": [asdict(record) for record in records],
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def build_plan(record_ids: Sequence[str], runner: Runner) -> RetirementPlan:
    if not record_ids or len(record_ids) > MAX_RECORDS:
        raise LegacyRetirementError(f"record count must be between 1 and {MAX_RECORDS}")
    if len(set(record_ids)) != len(record_ids):
        raise LegacyRetirementError("duplicate record IDs are not allowed")
    if any(not RECORD_ID_PATTERN.fullmatch(record_id) for record_id in record_ids):
        raise LegacyRetirementError("invalid Buildx record ID")

    loaded: list[ReviewedRecord] = []
    for record_id in sorted(record_ids):
        record = _load_record(record_id, runner)
        if record is None:  # pragma: no cover - missing is rejected above.
            raise LegacyRetirementError("candidate record is missing")
        loaded.append(record)
    records = tuple(loaded)
    return RetirementPlan(
        builder=LEGACY_BUILDER,
        records=records,
        record_count=len(records),
        total_bytes=sum(record.size_bytes for record in records),
        plan_sha256=_plan_hash(LEGACY_BUILDER, records),
    )


def _prune_command(record_id: str) -> list[str]:
    return [
        "docker",
        "buildx",
        "prune",
        "--builder",
        LEGACY_BUILDER,
        "--filter",
        f"id={record_id}",
        "--filter",
        "inuse!=true",
        "--filter",
        "shared!=true",
        "--filter",
        "mutable!=true",
        "--filter",
        "immutable!=false",
        "--filter",
        "type=regular",
        "--filter",
        "description~=requirements-production[.]txt",
        "--force",
    ]


def execute_plan(
    plan: RetirementPlan,
    runner: Runner,
    *,
    expected_record_count: int,
    expected_total_bytes: int,
    expected_plan_sha256: str,
) -> None:
    if expected_record_count != plan.record_count:
        raise LegacyRetirementError("record count changed after review")
    if expected_total_bytes != plan.total_bytes:
        raise LegacyRetirementError("total bytes changed after review")
    if expected_plan_sha256 != plan.plan_sha256:
        raise LegacyRetirementError("plan SHA-256 changed after review")

    for record in plan.records:
        runner.run(_prune_command(record.record_id))
        if _load_record(record.record_id, runner, allow_missing=True) is not None:
            raise LegacyRetirementError(
                f"record {record.record_id} remained after exact-ID prune"
            )


def plan_summary(plan: RetirementPlan, *, execute: bool) -> dict[str, object]:
    return {
        "builder": plan.builder,
        "execute": execute,
        "plan_sha256": plan.plan_sha256,
        "record_count": plan.record_count,
        "records": [
            {
                "id": record.record_id,
                "size_bytes": record.size_bytes,
                "description_sha256": record.description_sha256,
            }
            for record in plan.records
        ],
        "scope": "exact_non_shared_immutable_infohub_dependency_records",
        "total_bytes": plan.total_bytes,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--record-id",
        action="append",
        required=True,
        help=f"Reviewed legacy BuildKit record ID; repeat up to {MAX_RECORDS} times",
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--expected-record-count", type=int)
    parser.add_argument("--expected-total-bytes", type=int)
    parser.add_argument("--expected-plan-sha256")
    return parser


def _validate_execution_args(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> None:
    expected = (
        args.expected_record_count,
        args.expected_total_bytes,
        args.expected_plan_sha256,
    )
    if not args.execute:
        if any(value is not None for value in expected):
            parser.error("expected values require --execute")
        return
    if args.expected_record_count is None or args.expected_record_count < 1:
        parser.error("--execute requires --expected-record-count")
    if args.expected_total_bytes is None or args.expected_total_bytes < 1:
        parser.error("--execute requires --expected-total-bytes")
    if not args.expected_plan_sha256 or not re.fullmatch(
        r"[0-9a-f]{64}", args.expected_plan_sha256
    ):
        parser.error("--execute requires a lowercase 64-character plan SHA-256")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    _validate_execution_args(args, parser)
    runner = SubprocessRunner()
    try:
        plan = build_plan(args.record_id, runner)
        if args.execute:
            execute_plan(
                plan,
                runner,
                expected_record_count=args.expected_record_count,
                expected_total_bytes=args.expected_total_bytes,
                expected_plan_sha256=args.expected_plan_sha256,
            )
        print(
            "INFOHUB_LEGACY_BUILDKIT_RETIREMENT="
            + json.dumps(plan_summary(plan, execute=args.execute), sort_keys=True)
        )
        return 0
    except (LegacyRetirementError, OSError, subprocess.CalledProcessError) as error:
        print(f"Legacy BuildKit retirement failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
