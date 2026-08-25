#!/usr/bin/env python3
"""Compare an InfoHub ingest summary with the prior official catalog totals.

The audit is intentionally aggregate-only.  It persists only per-species
catalog totals and reports when the upstream catalog grows without any document
being added to the corpus.  Document titles, URLs and text never enter the
state file or machine summary.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence


SUMMARY_PREFIX = "INFOHUB_INGEST_SUMMARY="
REPORT_PREFIX = "INFOHUB_INGEST_FRESHNESS="
SCHEMA_VERSION = 1
MAX_INPUT_BYTES = 32_768
COUNT_FIELDS = (
    "source_total",
    "pages_visited",
    "known",
    "unseen",
    "ingested",
    "skipped_short",
    "detail_failures",
    "processing_errors",
)


class FreshnessAuditError(ValueError):
    """Raised when summary or state input violates the bounded contract."""


def _nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FreshnessAuditError(f"{label} must be a non-negative integer")
    return value


def parse_summary_line(raw: str) -> dict[str, object]:
    if not isinstance(raw, str):
        raise FreshnessAuditError("summary must be text")
    if len(raw.encode("utf-8")) > MAX_INPUT_BYTES:
        raise FreshnessAuditError("summary exceeded the size limit")
    if "\n" in raw or "\r" in raw:
        raise FreshnessAuditError("summary must be a single line")
    if raw.startswith(SUMMARY_PREFIX):
        raw = raw[len(SUMMARY_PREFIX) :]
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise FreshnessAuditError("summary is not valid JSON") from error
    if not isinstance(parsed, dict):
        raise FreshnessAuditError("summary root must be an object")

    species = parsed.get("species")
    if not isinstance(species, dict) or not species:
        raise FreshnessAuditError("summary species must be a non-empty object")
    normalized_species: dict[str, dict[str, int]] = {}
    for name, raw_stats in species.items():
        if not isinstance(name, str) or not name or len(name) > 80:
            raise FreshnessAuditError("summary contains an invalid species name")
        if not isinstance(raw_stats, dict):
            raise FreshnessAuditError(f"species {name} stats must be an object")
        normalized_species[name] = {
            field: _nonnegative_int(raw_stats.get(field), f"{name}.{field}")
            for field in COUNT_FIELDS
        }

    documents_scraped = _nonnegative_int(
        parsed.get("documents_scraped"), "documents_scraped"
    )
    if documents_scraped != sum(
        stats["ingested"] for stats in normalized_species.values()
    ):
        raise FreshnessAuditError(
            "documents_scraped does not match the per-species ingested total"
        )
    return {
        "documents_scraped": documents_scraped,
        "species": normalized_species,
    }


def parse_state(raw: object) -> dict[str, int]:
    if raw is None:
        return {}
    if not isinstance(raw, dict) or raw.get("schema_version") != SCHEMA_VERSION:
        raise FreshnessAuditError("state has an unsupported schema")
    species = raw.get("species")
    if not isinstance(species, dict):
        raise FreshnessAuditError("state species must be an object")
    result: dict[str, int] = {}
    for name, item in species.items():
        if not isinstance(name, str) or not isinstance(item, dict):
            raise FreshnessAuditError("state contains invalid species data")
        result[name] = _nonnegative_int(
            item.get("source_total"), f"state.{name}.source_total"
        )
    return result


def evaluate_freshness(
    summary: Mapping[str, object],
    previous_totals: Mapping[str, int],
    *,
    evaluated_at: datetime | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    species = summary["species"]
    if not isinstance(species, Mapping):  # Defensive for direct library use.
        raise FreshnessAuditError("summary species must be a mapping")

    violations: list[str] = []
    report_species: dict[str, dict[str, int | None]] = {}
    state_species: dict[str, dict[str, int]] = {}
    baseline_count = 0
    for name in sorted(species):
        stats = species[name]
        if not isinstance(stats, Mapping):
            raise FreshnessAuditError(f"species {name} stats must be a mapping")
        current_total = _nonnegative_int(stats.get("source_total"), f"{name}.source_total")
        pages_visited = _nonnegative_int(
            stats.get("pages_visited"), f"{name}.pages_visited"
        )
        ingested = _nonnegative_int(stats.get("ingested"), f"{name}.ingested")
        previous_total = previous_totals.get(name)
        if previous_total is None:
            delta = None
            baseline_count += 1
        else:
            previous_total = _nonnegative_int(
                previous_total, f"state.{name}.source_total"
            )
            delta = current_total - previous_total
            if delta < 0:
                violations.append(f"{name}:source_total_decreased")
            elif delta > 0 and ingested == 0:
                violations.append(f"{name}:source_grew_without_ingest")

        source_observed = current_total > 0 and pages_visited > 0
        if not source_observed:
            violations.append(f"{name}:source_unavailable")

        detail_failures = _nonnegative_int(
            stats.get("detail_failures"), f"{name}.detail_failures"
        )
        processing_errors = _nonnegative_int(
            stats.get("processing_errors"), f"{name}.processing_errors"
        )
        if detail_failures:
            violations.append(f"{name}:detail_failures")
        if processing_errors:
            violations.append(f"{name}:processing_errors")

        report_species[name] = {
            "previous_source_total": previous_total,
            "source_total": current_total,
            "source_delta": delta,
            "pages_visited": pages_visited,
            "unseen": _nonnegative_int(stats.get("unseen"), f"{name}.unseen"),
            "ingested": ingested,
            "skipped_short": _nonnegative_int(
                stats.get("skipped_short"), f"{name}.skipped_short"
            ),
            "detail_failures": detail_failures,
            "processing_errors": processing_errors,
        }
        # A transient API failure reports total=0.  Never replace the last good
        # baseline with that value, otherwise recovery would look like catalog
        # growth without ingestion on the following night.
        if source_observed and (delta is None or delta >= 0):
            state_species[name] = {"source_total": current_total}
        elif previous_total is not None:
            state_species[name] = {"source_total": previous_total}

    now = evaluated_at or datetime.now(timezone.utc)
    timestamp = now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if violations:
        status = "warning"
    elif baseline_count == len(report_species):
        status = "baseline"
    else:
        status = "healthy"
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "evaluated_at_utc": timestamp,
        "documents_ingested": _nonnegative_int(
            summary.get("documents_scraped"), "documents_scraped"
        ),
        "species": report_species,
        "violations": violations,
    }
    state = {
        "schema_version": SCHEMA_VERSION,
        "updated_at_utc": timestamp,
        "species": state_species,
    }
    return report, state


def read_state(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    if path.is_symlink() or not path.is_file():
        raise FreshnessAuditError("state must be a regular file, not a symlink")
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise FreshnessAuditError("state exceeded the size limit")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FreshnessAuditError("state is not readable valid JSON") from error
    return parse_state(raw)


def write_state(path: Path, state_data: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists() and (path.is_symlink() or not path.is_file()):
        raise FreshnessAuditError("state must be a regular file, not a symlink")
    payload = json.dumps(state_data, sort_keys=True, separators=(",", ":")) + "\n"
    temp_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_name = handle.name
            os.chmod(temp_name, stat.S_IRUSR | stat.S_IWUSR)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    finally:
        if temp_name:
            try:
                Path(temp_name).unlink(missing_ok=True)
            except OSError:
                pass


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary-line", required=True)
    parser.add_argument(
        "--state-file",
        type=Path,
        default=Path("/root/infohub/.state/infohub_ingestion_freshness.json"),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        summary = parse_summary_line(args.summary_line)
        prior = read_state(args.state_file)
        report, state_data = evaluate_freshness(summary, prior)
        write_state(args.state_file, state_data)
    except (FreshnessAuditError, OSError, TypeError, ValueError) as error:
        print(
            REPORT_PREFIX
            + json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "status": "error",
                    "violations": ["audit_failed"],
                },
                sort_keys=True,
            )
        )
        print(f"InfoHub ingestion freshness audit failed: {error}", file=sys.stderr)
        return 2

    print(REPORT_PREFIX + json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 1 if report["violations"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
