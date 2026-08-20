#!/usr/bin/env python
"""Validate completed expert worksheets and emit proposal-only corrections.

This tool is stdlib-only and never connects to PostgreSQL or an LLM. It checks
immutable source columns against the signed bundle, validates reviewer evidence
and second-review rules, and can materialize a non-executable correction
manifest only from a fully completed review.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_ROOT))

import build_decision_facts_full_review_bundle as bundle_builder  # noqa: E402


VERIFICATION_TO_FIELD = {
    "authority_body_correct": "authority_body",
    "dispute_type_correct": "dispute_type",
    "outcome_correct": "outcome",
    "in_favor_correct": "in_favor",
    "decision_number_correct": "decision_number",
    "decision_date_correct": "decision_date",
    "contested_articles_correct": "contested_articles",
    "amount_correct": "amount_gel",
}

ALLOWED_CORRECTION_FIELDS = set(VERIFICATION_TO_FIELD.values()) | {
    "document_number",
    "date_published",
}


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _read_restricted(path: Path) -> bytes:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"input must be a regular file, not a symlink: {path.name}")
    if os.name == "posix":
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:
            raise PermissionError(
                f"input permissions must be 0600-compatible: {path.name} is {mode:04o}"
            )
    return path.read_bytes()


def _load_bundle(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = _read_restricted(path)
    bundle = json.loads(raw.decode("utf-8"))
    if bundle.get("schema_version") != 1:
        raise ValueError("unsupported review bundle schema")
    if bundle.get("bundle_type") != "decision_facts_full_expert_review":
        raise ValueError("input is not a full expert-review bundle")
    if bundle.get("review_contract", {}).get("database_writes_allowed") is not False:
        raise ValueError("review bundle does not prohibit database writes")
    review_items = bundle.get("review_items")
    duplicate_groups = bundle.get("duplicate_groups")
    if not isinstance(review_items, list) or not isinstance(duplicate_groups, list):
        raise ValueError("review bundle queues are missing")
    counts = bundle.get("counts") or {}
    actual_counts = {
        "review_items": len(review_items),
        "duplicate_groups": len(duplicate_groups),
        "duplicate_members": sum(
            len(group.get("members") or []) for group in duplicate_groups
        ),
    }
    if counts != actual_counts:
        raise ValueError("review bundle counts do not match its contents")
    return bundle, raw


def _load_csv(
    path: Path, expected_fields: tuple[str, ...]
) -> tuple[list[dict[str, str]], bytes]:
    raw = _read_restricted(path)
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if tuple(reader.fieldnames or ()) != expected_fields:
        raise ValueError(f"unexpected CSV columns: {path.name}")
    rows = list(reader)
    if any(None in row for row in rows):
        raise ValueError(f"unexpected extra CSV cells: {path.name}")
    return rows, raw


def _expected_review_rows(bundle: dict[str, Any]) -> dict[str, dict[str, str]]:
    rows = {}
    fields = bundle_builder.REVIEW_ITEM_IMMUTABLE_FIELDS
    for item in bundle["review_items"]:
        raw = {field: item.get(field) for field in fields}
        raw["queue_reasons"] = item.get("queue_reasons") or []
        row = {field: bundle_builder._csv_safe(raw.get(field)) for field in fields}
        rows[row["review_id"]] = row
    return rows


def _expected_duplicate_rows(bundle: dict[str, Any]) -> dict[str, dict[str, str]]:
    rows = {}
    fields = bundle_builder.DUPLICATE_GROUP_IMMUTABLE_FIELDS
    for group in bundle["duplicate_groups"]:
        raw = {
            "group_id": group["group_id"],
            "candidate_class": group["candidate_class"],
            "authority_body": group.get("authority_body"),
            "normalized_number": group["normalized_number"],
            "member_count": group["member_count"],
            "signals_json": group["signals"],
        }
        row = {field: bundle_builder._csv_safe(raw.get(field)) for field in fields}
        rows[row["group_id"]] = row
    return rows


def _parse_utc(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    offset = parsed.utcoffset()
    return (
        parsed.tzinfo is not None and offset is not None and offset.total_seconds() == 0
    )


def _parse_json(value: str, expected_type: type, label: str, errors: list[str]) -> Any:
    try:
        payload = json.loads(value or ("{}" if expected_type is dict else "[]"))
    except json.JSONDecodeError:
        errors.append(f"{label}: invalid JSON")
        return expected_type()
    if not isinstance(payload, expected_type):
        errors.append(f"{label}: expected {expected_type.__name__}")
        return expected_type()
    return payload


def _validate_identity_and_immutable(
    rows: list[dict[str, str]],
    expected: dict[str, dict[str, str]],
    key: str,
    immutable_fields: tuple[str, ...],
    errors: list[str],
) -> dict[str, dict[str, str]]:
    actual = {}
    for row in rows:
        identity = row.get(key, "")
        if not identity:
            errors.append(f"{key}: blank identity")
            continue
        if identity in actual:
            errors.append(f"{identity}: duplicate worksheet row")
            continue
        actual[identity] = row
        expected_row = expected.get(identity)
        if expected_row is None:
            errors.append(f"{identity}: unknown worksheet identity")
            continue
        for field in immutable_fields:
            if row.get(field, "") != expected_row[field]:
                errors.append(f"{identity}: immutable field changed: {field}")
    for identity in sorted(set(expected) - set(actual)):
        errors.append(f"{identity}: worksheet row is missing")
    return actual


def _validate_reviewer_fields(
    row: dict[str, str], identity: str, errors: list[str]
) -> None:
    if not row.get("evidence_locator", "").strip():
        errors.append(f"{identity}: evidence_locator is required")
    if row.get("confidence") not in {"high", "medium", "low"}:
        errors.append(f"{identity}: confidence must be high, medium or low")
    if not row.get("reviewer", "").strip():
        errors.append(f"{identity}: reviewer is required")
    if not _parse_utc(row.get("reviewed_at_utc", "")):
        errors.append(f"{identity}: reviewed_at_utc must be an aware UTC timestamp")


def _validate_second_review(
    row: dict[str, str], identity: str, errors: list[str]
) -> None:
    first = row.get("reviewer", "").strip()
    second = row.get("second_reviewer", "").strip()
    if not second:
        errors.append(f"{identity}: distinct second_reviewer is required")
    elif second.casefold() == first.casefold():
        errors.append(f"{identity}: second_reviewer must differ from reviewer")
    if not _parse_utc(row.get("second_reviewed_at_utc", "")):
        errors.append(f"{identity}: second_reviewed_at_utc must be UTC")


def validate_review_items(
    bundle: dict[str, Any], rows: list[dict[str, str]], *, require_complete: bool
) -> tuple[dict[str, int], list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    expected = _expected_review_rows(bundle)
    actual = _validate_identity_and_immutable(
        rows,
        expected,
        "review_id",
        bundle_builder.REVIEW_ITEM_IMMUTABLE_FIELDS,
        errors,
    )
    bundle_by_id = {item["review_id"]: item for item in bundle["review_items"]}
    completed = 0
    pending = 0
    proposals = []
    allowed = {"correct", "incorrect", "not_applicable", "unable_to_verify"}
    for identity, row in actual.items():
        if identity not in expected:
            continue
        state = row.get("review_state", "")
        if state == "pending":
            pending += 1
            if require_complete:
                errors.append(f"{identity}: review is still pending")
            continue
        if state != "complete":
            errors.append(f"{identity}: review_state must be pending or complete")
            continue
        completed += 1
        _validate_reviewer_fields(row, identity, errors)
        verdicts = {}
        for field in bundle_builder.FIELD_VERIFICATIONS:
            verdict = row.get(field, "")
            verdicts[field] = verdict
            if verdict not in allowed:
                errors.append(f"{identity}: invalid verdict for {field}")
        corrections = _parse_json(
            row.get("proposed_corrections_json", ""),
            dict,
            f"{identity} proposed_corrections_json",
            errors,
        )
        unknown_fields = sorted(set(corrections) - ALLOWED_CORRECTION_FIELDS)
        if unknown_fields:
            errors.append(f"{identity}: unknown correction fields: {unknown_fields}")
        required_corrections = {
            target
            for verification, target in VERIFICATION_TO_FIELD.items()
            if verdicts.get(verification) == "incorrect"
        }
        missing = sorted(required_corrections - set(corrections))
        if missing:
            errors.append(f"{identity}: missing proposed corrections: {missing}")
        justified_corrections = set(required_corrections)
        if verdicts.get("identity_correct") == "incorrect":
            justified_corrections.update({"document_number", "date_published"})
            if not corrections:
                errors.append(f"{identity}: incorrect identity requires a correction")
        unjustified = sorted(set(corrections) - justified_corrections)
        if unjustified:
            errors.append(
                f"{identity}: corrections lack matching incorrect verdicts: {unjustified}"
            )
        non_source_incorrect = any(
            verdict == "incorrect"
            for field, verdict in verdicts.items()
            if field != "source_accessible"
        )
        if non_source_incorrect and not row.get("legal_rationale", "").strip():
            errors.append(f"{identity}: legal_rationale is required for corrections")
        if verdicts.get("source_accessible") == "unable_to_verify":
            inappropriate = [
                field
                for field in bundle_builder.FIELD_VERIFICATIONS[1:]
                if verdicts.get(field) not in {"unable_to_verify", "not_applicable"}
            ]
            if inappropriate:
                errors.append(
                    f"{identity}: inaccessible source cannot support field verdicts"
                )
        if (
            verdicts.get("outcome_correct") == "incorrect"
            or verdicts.get("in_favor_correct") == "incorrect"
        ):
            _validate_second_review(row, identity, errors)
        if corrections:
            source = bundle_by_id[identity]
            proposals.append(
                {
                    "review_id": identity,
                    "facts_id": source["facts_id"],
                    "document_id": source["document_id"],
                    "changes": {
                        field: {"current": source.get(field), "proposed": proposed}
                        for field, proposed in sorted(corrections.items())
                    },
                    "evidence_locator": row["evidence_locator"].strip(),
                    "legal_rationale": row.get("legal_rationale", "").strip(),
                    "confidence": row.get("confidence"),
                    "reviewer": row.get("reviewer", "").strip(),
                    "reviewed_at_utc": row.get("reviewed_at_utc"),
                    "second_reviewer": row.get("second_reviewer", "").strip() or None,
                    "second_reviewed_at_utc": row.get("second_reviewed_at_utc") or None,
                }
            )
    return {"completed": completed, "pending": pending}, proposals, errors


def validate_duplicate_groups(
    bundle: dict[str, Any], rows: list[dict[str, str]], *, require_complete: bool
) -> tuple[dict[str, int], list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    expected = _expected_duplicate_rows(bundle)
    actual = _validate_identity_and_immutable(
        rows,
        expected,
        "group_id",
        bundle_builder.DUPLICATE_GROUP_IMMUTABLE_FIELDS,
        errors,
    )
    groups_by_id = {group["group_id"]: group for group in bundle["duplicate_groups"]}
    allowed = {
        "true_duplicate",
        "distinct_decisions",
        "mixed_group",
        "unable_to_verify",
    }
    completed = 0
    pending = 0
    proposals = []
    for identity, row in actual.items():
        group = groups_by_id.get(identity)
        if group is None:
            continue
        state = row.get("review_state", "")
        if state == "pending":
            pending += 1
            if require_complete:
                errors.append(f"{identity}: duplicate review is still pending")
            continue
        if state != "complete":
            errors.append(f"{identity}: review_state must be pending or complete")
            continue
        completed += 1
        _validate_reviewer_fields(row, identity, errors)
        verdict = row.get("duplicate_verdict", "")
        if verdict not in allowed:
            errors.append(f"{identity}: invalid duplicate_verdict")
        if not row.get("legal_rationale", "").strip():
            errors.append(f"{identity}: duplicate verdict requires legal_rationale")
        member_ids = {str(member["document_id"]) for member in group["members"]}
        canonical = row.get("canonical_document_id", "").strip()
        exclusions = _parse_json(
            row.get("proposed_exclusions_json", ""),
            list,
            f"{identity} proposed_exclusions_json",
            errors,
        )
        if len(exclusions) != len(set(map(str, exclusions))):
            errors.append(f"{identity}: proposed exclusions contain duplicates")
        exclusions = [str(value) for value in exclusions]
        unknown = sorted(set(exclusions) - member_ids)
        if unknown:
            errors.append(f"{identity}: exclusions are not group members: {unknown}")
        if verdict in {"true_duplicate", "mixed_group"}:
            if canonical not in member_ids:
                errors.append(
                    f"{identity}: canonical_document_id must be a group member"
                )
            if not exclusions:
                errors.append(f"{identity}: duplicate proposal requires exclusions")
            if canonical in exclusions:
                errors.append(f"{identity}: canonical document cannot be excluded")
            if verdict == "true_duplicate" and set(exclusions) != member_ids - {
                canonical
            }:
                errors.append(
                    f"{identity}: true duplicate must account for every other member"
                )
            if not row.get("legal_rationale", "").strip():
                errors.append(
                    f"{identity}: duplicate proposal requires legal_rationale"
                )
            _validate_second_review(row, identity, errors)
        elif canonical or exclusions:
            errors.append(
                f"{identity}: non-duplicate verdict cannot propose exclusions"
            )
        if verdict in {"true_duplicate", "mixed_group"} and canonical in member_ids:
            proposals.append(
                {
                    "group_id": identity,
                    "candidate_class": group["candidate_class"],
                    "review_verdict": verdict,
                    "canonical_document_id": canonical,
                    "proposed_exclusions": exclusions,
                    "evidence_locator": row["evidence_locator"].strip(),
                    "legal_rationale": row.get("legal_rationale", "").strip(),
                    "confidence": row.get("confidence"),
                    "reviewer": row.get("reviewer", "").strip(),
                    "reviewed_at_utc": row.get("reviewed_at_utc"),
                    "second_reviewer": row.get("second_reviewer", "").strip(),
                    "second_reviewed_at_utc": row.get("second_reviewed_at_utc"),
                }
            )
    return {"completed": completed, "pending": pending}, proposals, errors


def build_validation(
    bundle: dict[str, Any],
    review_rows: list[dict[str, str]],
    duplicate_rows: list[dict[str, str]],
    *,
    require_complete: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    review_counts, corrections, review_errors = validate_review_items(
        bundle, review_rows, require_complete=require_complete
    )
    duplicate_counts, duplicate_proposals, duplicate_errors = validate_duplicate_groups(
        bundle, duplicate_rows, require_complete=require_complete
    )
    summary = {
        "review_items": review_counts,
        "duplicate_groups": duplicate_counts,
        "correction_proposals": len(corrections),
        "duplicate_proposals": len(duplicate_proposals),
        "errors": review_errors + duplicate_errors,
    }
    manifest = {
        "schema_version": 1,
        "manifest_type": "decision_facts_correction_proposals",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "execution_profile": {
            "postgresql_writes_allowed": False,
            "apply_supported": False,
            "proposal_only": True,
        },
        "source": bundle["source"],
        "validation": {key: value for key, value in summary.items() if key != "errors"},
        "fact_correction_proposals": corrections,
        "duplicate_resolution_proposals": duplicate_proposals,
    }
    return summary, manifest


def _write_exclusive(path: Path, payload: dict[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        raise FileExistsError("output already exists; refusing to overwrite it")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    os.chmod(path, 0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--review-items", type=Path, required=True)
    parser.add_argument("--duplicate-groups", type=Path, required=True)
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--expected-input-sha256")
    parser.add_argument("--expected-complete-review-items", type=int)
    parser.add_argument("--expected-complete-duplicate-groups", type=int)
    args = parser.parse_args()

    bundle, bundle_raw = _load_bundle(args.bundle)
    review_fields = (
        bundle_builder.REVIEW_ITEM_IMMUTABLE_FIELDS
        + bundle_builder.REVIEW_ITEM_EDITABLE_FIELDS
    )
    duplicate_fields = (
        bundle_builder.DUPLICATE_GROUP_IMMUTABLE_FIELDS
        + bundle_builder.DUPLICATE_GROUP_EDITABLE_FIELDS
    )
    review_rows, review_raw = _load_csv(args.review_items, review_fields)
    duplicate_rows, duplicate_raw = _load_csv(args.duplicate_groups, duplicate_fields)
    input_hashes = {
        "bundle": _sha256(bundle_raw),
        "review_items": _sha256(review_raw),
        "duplicate_groups": _sha256(duplicate_raw),
    }
    input_sha256 = _sha256(_canonical_json(input_hashes))
    summary, manifest = build_validation(
        bundle,
        review_rows,
        duplicate_rows,
        require_complete=args.require_complete,
    )
    output_summary = {
        **{key: value for key, value in summary.items() if key != "errors"},
        "error_count": len(summary["errors"]),
        "errors": summary["errors"][:20],
        "input_sha256": input_sha256,
    }
    prefix = "DECISION_FACTS_EXPERT_REVIEW_VALIDATION"
    if not args.execute:
        print(prefix + "=" + json.dumps(output_summary, sort_keys=True))
        return 1 if summary["errors"] else 0

    if not args.require_complete:
        parser.error("--execute requires --require-complete")
    if summary["errors"]:
        print(prefix + "=" + json.dumps(output_summary, sort_keys=True))
        return 1
    if args.output is None:
        parser.error("--output is required with --execute")
    if not args.expected_input_sha256:
        parser.error("--expected-input-sha256 is required with --execute")
    if args.expected_input_sha256.lower() != input_sha256:
        raise ValueError("expert-review inputs changed after validation")
    checks = (
        (
            args.expected_complete_review_items,
            summary["review_items"]["completed"],
            "completed review items",
        ),
        (
            args.expected_complete_duplicate_groups,
            summary["duplicate_groups"]["completed"],
            "completed duplicate groups",
        ),
    )
    for expected, actual, label in checks:
        if expected is None or expected != actual:
            raise ValueError(f"{label} changed: expected {expected}, got {actual}")
    manifest["input_hashes"] = input_hashes
    manifest["input_sha256"] = input_sha256
    _write_exclusive(args.output, manifest)
    print(
        prefix
        + "="
        + json.dumps({**output_summary, "output": str(args.output)}, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
