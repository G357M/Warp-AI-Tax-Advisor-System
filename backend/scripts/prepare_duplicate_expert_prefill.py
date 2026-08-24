#!/usr/bin/env python
"""Prepare a safe technical prefill for duplicate expert review.

The tool combines an immutable expert-review bundle with a technical InfoHub
verification report.  It may fill only blank ``evidence_locator`` and ``notes``
cells on pending rows.  It never creates a legal verdict, canonical selection,
exclusion, confidence statement or reviewer sign-off.

Dry-run is the default. Execute is pinned to every input SHA-256, row/change
counts and the exact expected output SHA-256, and refuses overwrites.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import stat
from pathlib import Path
from typing import Any

try:  # package import in tests
    from scripts import build_decision_facts_full_review_bundle as bundle_builder
except ModuleNotFoundError:  # direct ``python backend/scripts/...`` execution
    import build_decision_facts_full_review_bundle as bundle_builder


FIELDS = (
    bundle_builder.DUPLICATE_GROUP_IMMUTABLE_FIELDS
    + bundle_builder.DUPLICATE_GROUP_EDITABLE_FIELDS
)
MACHINE_EDITABLE_FIELDS = {"evidence_locator", "notes"}
PROTECTED_LEGAL_FIELDS = set(bundle_builder.DUPLICATE_GROUP_EDITABLE_FIELDS) - (
    MACHINE_EDITABLE_FIELDS | {"review_state"}
)
SAFE_ASSESSMENTS = {
    "official_content_identical",
    "official_content_high_overlap",
    "official_content_near_identical",
    "same_content_identity_mismatch",
    "official_content_differs",
    "verification_incomplete",
}


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_restricted(path: Path) -> bytes:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"input must be a regular file, not a symlink: {path.name}")
    if os.name == "posix":
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:
            raise PermissionError(
                f"input permissions must be 0600-compatible, got {mode:04o}: {path.name}"
            )
    return path.read_bytes()


def _load_json(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = _read_restricted(path)
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON input must contain an object: {path.name}")
    return payload, raw


def _parse_csv(raw: bytes) -> list[dict[str, str]]:
    stream = io.StringIO(raw.decode("utf-8-sig"), newline="")
    reader = csv.DictReader(stream)
    if tuple(reader.fieldnames or ()) != FIELDS:
        raise ValueError("duplicate-review CSV columns do not match the protected contract")
    rows = list(reader)
    if any(None in row for row in rows):
        raise ValueError("duplicate-review CSV contains unexpected extra columns")
    return rows


def _expected_rows(bundle: dict[str, Any]) -> list[dict[str, str]]:
    return _parse_csv(bundle_builder.render_duplicate_groups(bundle))


def _validate_bundle(bundle: dict[str, Any]) -> None:
    if bundle.get("schema_version") != 1:
        raise ValueError("unsupported expert-review bundle schema")
    if bundle.get("bundle_type") != "decision_facts_full_expert_review":
        raise ValueError("input is not a full expert-review bundle")
    if bundle.get("review_contract", {}).get("database_writes_allowed") is not False:
        raise ValueError("expert-review bundle must prohibit database writes")
    groups = bundle.get("duplicate_groups")
    if not isinstance(groups, list):
        raise ValueError("duplicate groups are missing from expert-review bundle")
    if (bundle.get("counts") or {}).get("duplicate_groups") != len(groups):
        raise ValueError("expert-review bundle duplicate-group count is invalid")


def _validate_report(report: dict[str, Any], *, bundle_sha256: str) -> None:
    if report.get("schema_version") != 1:
        raise ValueError("unsupported technical-verification report schema")
    if report.get("report_type") != "infohub_duplicate_technical_verification":
        raise ValueError("input is not an InfoHub duplicate technical-verification report")
    if (report.get("source") or {}).get("bundle_sha256") != bundle_sha256:
        raise ValueError("technical report was not created from this expert-review bundle")

    profile = report.get("execution_profile") or {}
    for field in (
        "llm_calls_allowed",
        "postgresql_writes_allowed",
        "legal_verdicts_allowed",
        "automatic_exclusions_allowed",
    ):
        if profile.get(field) is not False:
            raise ValueError(f"technical report has unsafe execution profile: {field}")
    legal_effect = report.get("legal_effect") or {}
    for field in (
        "legal_verdicts_created",
        "database_changes_created",
        "automatic_exclusions_created",
    ):
        if legal_effect.get(field) is not False:
            raise ValueError(f"technical report claims an unsafe legal effect: {field}")
    if legal_effect.get("expert_confirmation_required") is not True:
        raise ValueError("technical report must require expert confirmation")


def _validate_review_rows(
    review_rows: list[dict[str, str]], expected_rows: list[dict[str, str]]
) -> None:
    expected_by_id = {row["group_id"]: row for row in expected_rows}
    if len(review_rows) != len(expected_rows):
        raise ValueError("duplicate-review CSV row count does not match the bundle")
    if len({row.get("group_id") for row in review_rows}) != len(review_rows):
        raise ValueError("duplicate-review CSV group IDs are not unique")
    for row in review_rows:
        group_id = row.get("group_id") or ""
        expected = expected_by_id.get(group_id)
        if expected is None:
            raise ValueError(f"duplicate-review CSV has an unknown group: {group_id}")
        for field in bundle_builder.DUPLICATE_GROUP_IMMUTABLE_FIELDS:
            if row.get(field, "") != expected.get(field, ""):
                raise ValueError(f"immutable duplicate field changed: {group_id}.{field}")
        if row.get("review_state") not in {"pending", "complete"}:
            raise ValueError(f"invalid review_state for duplicate group: {group_id}")


def _validated_report_groups(
    report: dict[str, Any], bundle: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    bundle_groups = {str(group["group_id"]): group for group in bundle["duplicate_groups"]}
    report_groups: dict[str, dict[str, Any]] = {}
    for item in report.get("groups") or []:
        group_id = str(item.get("group_id") or "")
        if not group_id or group_id in report_groups:
            raise ValueError("technical report group IDs are missing or duplicated")
        group = bundle_groups.get(group_id)
        if group is None:
            raise ValueError(f"technical report contains an unknown group: {group_id}")
        if item.get("candidate_class") != group.get("candidate_class"):
            raise ValueError(f"technical report candidate class changed: {group_id}")
        members = group.get("members") or []
        if int(item.get("member_count") or -1) != len(members):
            raise ValueError(f"technical report member count changed: {group_id}")
        if item.get("technical_assessment") not in SAFE_ASSESSMENTS:
            raise ValueError(f"unknown technical assessment: {group_id}")

        member_ids = {str(member.get("document_id") or "") for member in members}
        suggested_ids = {
            str(item.get("technical_canonical_document_id") or ""),
            *(
                str(value)
                for value in item.get("technical_exclusion_candidates") or []
            ),
        } - {""}
        if not suggested_ids.issubset(member_ids):
            raise ValueError(f"technical suggestions reference nonmembers: {group_id}")
        report_groups[group_id] = item
    return report_groups


def _technical_text(
    item: dict[str, Any], *, report_sha256: str
) -> tuple[str, str]:
    urls = [str(value).strip() for value in item.get("source_urls") or [] if str(value).strip()]
    locator = (
        f"Official InfoHub records: {' | '.join(urls)}; technical report SHA-256 "
        f"{report_sha256}; group {item['group_id']}."
    )
    parts = [
        "Machine technical suggestion; expert verification required.",
        f"assessment={item['technical_assessment']}",
        f"technical_confidence={item.get('technical_confidence') or 'not_set'}",
    ]
    canonical = str(item.get("technical_canonical_document_id") or "").strip()
    exclusions = [
        str(value).strip()
        for value in item.get("technical_exclusion_candidates") or []
        if str(value).strip()
    ]
    if canonical:
        parts.append(f"technical canonical candidate={canonical}")
    if exclusions:
        parts.append("technical exclusion candidates=" + ", ".join(exclusions))
    summary = str(item.get("evidence_summary") or "").strip()
    if summary:
        parts.append(summary)
    parts.append("No legal verdict, canonical selection or exclusion was applied.")
    return locator, "; ".join(parts)


def build_prefilled_rows(
    *,
    bundle: dict[str, Any],
    report: dict[str, Any],
    report_sha256: str,
    review_rows: list[dict[str, str]] | None = None,
) -> tuple[list[dict[str, str]], int]:
    expected = _expected_rows(bundle)
    rows = [dict(row) for row in (review_rows if review_rows is not None else expected)]
    _validate_review_rows(rows, expected)
    report_groups = _validated_report_groups(report, bundle)
    changed_rows = 0
    for row in rows:
        item = report_groups.get(row["group_id"])
        if row["review_state"] != "pending" or item is None:
            continue
        before = dict(row)
        locator, notes = _technical_text(item, report_sha256=report_sha256)
        if not row.get("evidence_locator", "").strip():
            row["evidence_locator"] = locator
        if not row.get("notes", "").strip():
            row["notes"] = notes
        for field in PROTECTED_LEGAL_FIELDS:
            if row.get(field, "") != before.get(field, ""):
                raise AssertionError(f"protected legal field changed: {row['group_id']}.{field}")
        if row != before:
            changed_rows += 1
    return rows, changed_rows


def _csv_safe(value: Any) -> str:
    text = "" if value is None else str(value)
    if text.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def render_rows(rows: list[dict[str, str]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=FIELDS, extrasaction="raise")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: _csv_safe(row.get(field, "")) for field in FIELDS})
    return ("\ufeff" + stream.getvalue()).encode("utf-8")


def _write_exclusive(path: Path, payload: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise FileExistsError("output file already exists; refusing overwrite")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
    os.chmod(path, 0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--technical-report", type=Path, required=True)
    parser.add_argument("--review-csv", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--expected-bundle-sha256")
    parser.add_argument("--expected-report-sha256")
    parser.add_argument("--expected-review-sha256")
    parser.add_argument("--expected-rows", type=int)
    parser.add_argument("--expected-prefilled-rows", type=int)
    parser.add_argument("--expected-output-sha256")
    args = parser.parse_args()

    bundle, bundle_raw = _load_json(args.bundle)
    report, report_raw = _load_json(args.technical_report)
    bundle_sha256 = _sha256(bundle_raw)
    report_sha256 = _sha256(report_raw)
    _validate_bundle(bundle)
    _validate_report(report, bundle_sha256=bundle_sha256)

    review_rows = None
    review_sha256 = None
    if args.review_csv:
        review_raw = _read_restricted(args.review_csv)
        review_sha256 = _sha256(review_raw)
        review_rows = _parse_csv(review_raw)

    rows, prefilled_rows = build_prefilled_rows(
        bundle=bundle,
        report=report,
        report_sha256=report_sha256,
        review_rows=review_rows,
    )
    output = render_rows(rows)
    output_sha256 = _sha256(output)
    plan = {
        "bundle_sha256": bundle_sha256,
        "technical_report_sha256": report_sha256,
        "review_csv_sha256": review_sha256,
        "rows": len(rows),
        "prefilled_rows": prefilled_rows,
        "output_sha256": output_sha256,
        "legal_verdicts_created": 0,
        "automatic_exclusions_created": 0,
    }
    prefix = "DUPLICATE_EXPERT_PREFILL"
    if not args.execute:
        print(prefix + "_PLAN=" + json.dumps(plan, sort_keys=True))
        return 0

    required = {
        "--expected-bundle-sha256": args.expected_bundle_sha256,
        "--expected-report-sha256": args.expected_report_sha256,
        "--expected-rows": args.expected_rows,
        "--expected-prefilled-rows": args.expected_prefilled_rows,
        "--expected-output-sha256": args.expected_output_sha256,
    }
    if args.review_csv:
        required["--expected-review-sha256"] = args.expected_review_sha256
    missing = [name for name, value in required.items() if value is None]
    if missing:
        parser.error("execute requires " + ", ".join(missing))
    if args.output is None:
        parser.error("--output is required with --execute")

    checks = (
        (args.expected_bundle_sha256, bundle_sha256, "expert-review bundle"),
        (args.expected_report_sha256, report_sha256, "technical report"),
        (args.expected_review_sha256, review_sha256, "review CSV"),
        (args.expected_rows, len(rows), "row count"),
        (args.expected_prefilled_rows, prefilled_rows, "prefilled row count"),
        (args.expected_output_sha256, output_sha256, "output"),
    )
    for expected, actual, label in checks:
        if expected is not None and str(expected).lower() != str(actual).lower():
            raise ValueError(f"{label} changed after dry run")

    _write_exclusive(args.output, output)
    print(prefix + "_RESULT=" + json.dumps({**plan, "output": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
