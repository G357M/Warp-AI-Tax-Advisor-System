#!/usr/bin/env python3
"""Retire exact, reviewed InfoHub records from the legacy Buildx builder."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Callable, Protocol, Sequence


LEGACY_BUILDER = "default"
EXPECTED_DESCRIPTION = (
    "mount / from exec /bin/sh -c "
    "pip install --no-cache-dir -r requirements-production.txt"
)
DEPENDENT_DESCRIPTION = "[6/6] COPY . ."
DESCRIPTION_SHA256 = hashlib.sha256(EXPECTED_DESCRIPTION.encode("utf-8")).hexdigest()
DEPENDENT_DESCRIPTION_SHA256 = hashlib.sha256(
    DEPENDENT_DESCRIPTION.encode("utf-8")
).hexdigest()
ROOT_ROLE = "dependency_root"
DEPENDENT_ROLE = "copy_leaf"
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
PRUNE_ATTEMPTS = 3
PRUNE_RETRY_SECONDS = 1.0


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
    role: str
    parent_ids: tuple[str, ...]


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
    role: str = ROOT_ROLE,
    approved_root_ids: frozenset[str] = frozenset(),
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

    if role == ROOT_ROLE:
        expected_description = EXPECTED_DESCRIPTION
        description_sha256 = DESCRIPTION_SHA256
    elif role == DEPENDENT_ROLE:
        expected_description = DEPENDENT_DESCRIPTION
        description_sha256 = DEPENDENT_DESCRIPTION_SHA256
    else:  # pragma: no cover - roles are internal constants.
        raise LegacyRetirementError("unknown reviewed record role")

    description = raw.get("Description")
    if description != expected_description:
        raise LegacyRetirementError("record is not an approved legacy InfoHub layer")
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
    raw_parents = raw.get("Parents", [])
    if not isinstance(raw_parents, list) or any(
        not isinstance(parent_id, str) or not RECORD_ID_PATTERN.fullmatch(parent_id)
        for parent_id in raw_parents
    ):
        raise LegacyRetirementError("candidate record has invalid parent IDs")
    parent_ids = tuple(raw_parents)
    if role == DEPENDENT_ROLE and (
        len(parent_ids) != 1 or parent_ids[0] not in approved_root_ids
    ):
        raise LegacyRetirementError(
            "dependent record must have exactly one approved dependency root"
        )

    return ReviewedRecord(
        record_id=record_id,
        size_bytes=_parse_size(raw["Size"]),
        created_at=raw["CreatedAt"],
        description_sha256=description_sha256,
        record_type="regular",
        role=role,
        parent_ids=parent_ids,
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


def build_plan(
    record_ids: Sequence[str],
    runner: Runner,
    *,
    dependent_record_ids: Sequence[str] = (),
) -> RetirementPlan:
    all_record_ids = [*record_ids, *dependent_record_ids]
    if not record_ids or len(all_record_ids) > MAX_RECORDS:
        raise LegacyRetirementError(f"record count must be between 1 and {MAX_RECORDS}")
    if len(set(all_record_ids)) != len(all_record_ids):
        raise LegacyRetirementError("duplicate record IDs are not allowed")
    if any(not RECORD_ID_PATTERN.fullmatch(record_id) for record_id in all_record_ids):
        raise LegacyRetirementError("invalid Buildx record ID")

    approved_root_ids = frozenset(record_ids)
    loaded: list[ReviewedRecord] = []
    for record_id in sorted(dependent_record_ids):
        record = _load_record(
            record_id,
            runner,
            role=DEPENDENT_ROLE,
            approved_root_ids=approved_root_ids,
        )
        if record is None:  # pragma: no cover - missing is rejected above.
            raise LegacyRetirementError("dependent record is missing")
        loaded.append(record)
    for record_id in sorted(record_ids):
        record = _load_record(record_id, runner, role=ROOT_ROLE)
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


def _prune_command(record: ReviewedRecord) -> list[str]:
    description_filter = (
        "description~=COPY"
        if record.role == DEPENDENT_ROLE
        else "description~=requirements-production[.]txt"
    )
    return [
        "docker",
        "buildx",
        "prune",
        "--builder",
        LEGACY_BUILDER,
        "--filter",
        f"id={record.record_id}",
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
        description_filter,
        "--force",
    ]


def execute_plan(
    plan: RetirementPlan,
    runner: Runner,
    *,
    expected_record_count: int,
    expected_total_bytes: int,
    expected_plan_sha256: str,
    sleeper: Callable[[float], None] = time.sleep,
) -> None:
    if expected_record_count != plan.record_count:
        raise LegacyRetirementError("record count changed after review")
    if expected_total_bytes != plan.total_bytes:
        raise LegacyRetirementError("total bytes changed after review")
    if expected_plan_sha256 != plan.plan_sha256:
        raise LegacyRetirementError("plan SHA-256 changed after review")

    approved_root_ids = frozenset(
        record.record_id for record in plan.records if record.role == ROOT_ROLE
    )
    for record in plan.records:
        for attempt in range(1, PRUNE_ATTEMPTS + 1):
            current = _load_record(
                record.record_id,
                runner,
                role=record.role,
                approved_root_ids=approved_root_ids,
                allow_missing=True,
            )
            if current is None:
                break
            if current != record:
                raise LegacyRetirementError(
                    f"record {record.record_id} metadata changed during retirement"
                )

            runner.run(_prune_command(record))
            if _load_record(
                record.record_id,
                runner,
                role=record.role,
                approved_root_ids=approved_root_ids,
                allow_missing=True,
            ) is None:
                break
            if attempt == PRUNE_ATTEMPTS:
                raise LegacyRetirementError(
                    f"record {record.record_id} remained after "
                    f"{PRUNE_ATTEMPTS} exact-ID prune attempts"
                )
            sleeper(PRUNE_RETRY_SECONDS)


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
                "role": record.role,
                "parent_ids": list(record.parent_ids),
            }
            for record in plan.records
        ],
        "scope": "exact_reviewed_non_shared_immutable_infohub_record_graph",
        "total_bytes": plan.total_bytes,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--record-id",
        action="append",
        required=True,
        help="Reviewed legacy dependency-root ID; repeat for every approved root",
    )
    parser.add_argument(
        "--dependent-record-id",
        action="append",
        default=[],
        help=(
            "Reviewed COPY leaf whose single parent is an approved --record-id; "
            f"combined record limit is {MAX_RECORDS}"
        ),
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
        plan = build_plan(
            args.record_id,
            runner,
            dependent_record_ids=args.dependent_record_id,
        )
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
