#!/usr/bin/env python
"""Build protected expert worksheets from a full decision-facts review export.

This stdlib-only host tool never connects to PostgreSQL or an LLM. Dry-run is
the default; execute is pinned to the exact restricted export SHA-256 and row
counts and refuses every overwrite.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FIELD_VERIFICATIONS = (
    "source_accessible",
    "identity_correct",
    "authority_body_correct",
    "dispute_type_correct",
    "outcome_correct",
    "in_favor_correct",
    "decision_number_correct",
    "decision_date_correct",
    "contested_articles_correct",
    "amount_correct",
)

REVIEW_ITEM_IMMUTABLE_FIELDS = (
    "review_id",
    "queue_reasons",
    "facts_id",
    "document_id",
    "title",
    "source_url",
    "document_number",
    "date_published",
    "file_hash",
    "content_length",
    "content_md5",
    "normalized_content_md5",
    "authority_body",
    "dispute_type",
    "outcome",
    "in_favor",
    "decision_number",
    "decision_date",
    "case_number",
    "contested_articles",
    "amount_gel",
)

REVIEW_ITEM_EDITABLE_FIELDS = (
    "review_state",
    *FIELD_VERIFICATIONS,
    "evidence_locator",
    "proposed_corrections_json",
    "legal_rationale",
    "confidence",
    "reviewer",
    "reviewed_at_utc",
    "second_reviewer",
    "second_reviewed_at_utc",
    "notes",
)

DUPLICATE_GROUP_IMMUTABLE_FIELDS = (
    "group_id",
    "candidate_class",
    "authority_body",
    "normalized_number",
    "member_count",
    "signals_json",
)

DUPLICATE_GROUP_EDITABLE_FIELDS = (
    "review_state",
    "duplicate_verdict",
    "canonical_document_id",
    "proposed_exclusions_json",
    "evidence_locator",
    "legal_rationale",
    "confidence",
    "reviewer",
    "reviewed_at_utc",
    "second_reviewer",
    "second_reviewed_at_utc",
    "notes",
)

DUPLICATE_MEMBER_FIELDS = (
    "group_id",
    "candidate_class",
    "member_index",
    "facts_id",
    "document_id",
    "title",
    "source_url",
    "document_number",
    "date_published",
    "file_hash",
    "content_length",
    "content_md5",
    "normalized_content_md5",
    "authority_body",
    "dispute_type",
    "outcome",
    "in_favor",
    "decision_number",
    "decision_date",
    "case_number",
)


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_restricted_export(path: Path) -> tuple[dict[str, Any], str]:
    if not path.is_file() or path.is_symlink():
        raise ValueError("input must be an existing regular file, not a symlink")
    if os.name == "posix":
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:
            raise PermissionError(
                f"operational export permissions must be 0600-compatible, got {mode:04o}"
            )
    raw = path.read_bytes()
    report = json.loads(raw.decode("utf-8"))
    if report.get("schema_version") != 1:
        raise ValueError("unsupported full expert-review export schema")
    if report.get("report_type") != "decision_facts_full_expert_review":
        raise ValueError("input is not a full expert-review export")
    profile = report.get("execution_profile") or {}
    if profile.get("llm_calls_allowed") is not False:
        raise ValueError("expert-review export must prohibit LLM calls")
    if profile.get("postgresql_writes_allowed") is not False:
        raise ValueError("expert-review export must prohibit PostgreSQL writes")
    if not isinstance(report.get("review_items"), list):
        raise ValueError("review_items are missing")
    if not isinstance(report.get("duplicate_groups"), list):
        raise ValueError("duplicate_groups are missing")
    snapshot = _sha256(
        _canonical_json(
            {
                "review_items": report["review_items"],
                "duplicate_groups": report["duplicate_groups"],
            }
        )
    )
    if snapshot != report.get("source_snapshot_sha256"):
        raise ValueError("full export source snapshot hash is invalid")
    return report, _sha256(raw)


def _stable_id(prefix: str, contract_version: str, identity: str) -> str:
    digest = hashlib.sha256(
        f"{contract_version}|{identity}".encode("utf-8")
    ).hexdigest()[:16]
    return f"{prefix}-{digest.upper()}"


def build_bundle(
    report: dict[str, Any], report_sha256: str, *, generated_at: datetime | None = None
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc)
    contract_version = str(report["contract_version"])
    review_items = []
    seen_document_ids: set[str] = set()
    for row in report["review_items"]:
        document_id = str(row.get("document_id") or "")
        if not document_id:
            raise ValueError("review item is missing document_id")
        if document_id in seen_document_ids:
            raise ValueError(f"duplicate review document_id: {document_id}")
        seen_document_ids.add(document_id)
        review_items.append(
            {
                **row,
                "review_id": _stable_id("DFR", contract_version, document_id),
                "review": {
                    "review_state": "pending",
                    **{field: None for field in FIELD_VERIFICATIONS},
                    "evidence_locator": "",
                    "proposed_corrections_json": {},
                    "legal_rationale": "",
                    "confidence": "",
                    "reviewer": "",
                    "reviewed_at_utc": "",
                    "second_reviewer": "",
                    "second_reviewed_at_utc": "",
                    "notes": "",
                },
            }
        )
    review_items.sort(key=lambda item: item["review_id"])

    duplicate_groups = []
    member_count = 0
    seen_group_ids: set[str] = set()
    for group in report["duplicate_groups"]:
        group_id = str(group.get("group_id") or "")
        if not group_id:
            raise ValueError("duplicate group is missing group_id")
        if group_id in seen_group_ids:
            raise ValueError(f"duplicate duplicate-group ID: {group_id}")
        seen_group_ids.add(group_id)
        members = group.get("members") or []
        if len(members) != int(group.get("member_count") or 0):
            raise ValueError(
                f"duplicate group member count mismatch: {group.get('group_id')}"
            )
        member_ids = [str(member.get("document_id") or "") for member in members]
        if any(not member_id for member_id in member_ids):
            raise ValueError(
                f"duplicate group contains a blank document_id: {group_id}"
            )
        if len(member_ids) != len(set(member_ids)):
            raise ValueError(f"duplicate group repeats a document_id: {group_id}")
        member_count += len(members)
        duplicate_groups.append(
            {
                **group,
                "review": {
                    "review_state": "pending",
                    "duplicate_verdict": "",
                    "canonical_document_id": "",
                    "proposed_exclusions_json": [],
                    "evidence_locator": "",
                    "legal_rationale": "",
                    "confidence": "",
                    "reviewer": "",
                    "reviewed_at_utc": "",
                    "second_reviewer": "",
                    "second_reviewed_at_utc": "",
                    "notes": "",
                },
            }
        )
    duplicate_groups.sort(key=lambda group: group["group_id"])
    return {
        "schema_version": 1,
        "bundle_type": "decision_facts_full_expert_review",
        "generated_at_utc": generated_at.astimezone(timezone.utc).isoformat(),
        "source": {
            "report_sha256": report_sha256,
            "source_snapshot_sha256": report["source_snapshot_sha256"],
            "contract_version": contract_version,
            "contract_sha256": report["contract_sha256"],
            "deployed_commit": report.get("deployed_commit"),
            "report_generated_at_utc": report.get("generated_at_utc"),
        },
        "review_contract": {
            "field_verdicts": [
                "correct",
                "incorrect",
                "not_applicable",
                "unable_to_verify",
            ],
            "duplicate_verdicts": [
                "true_duplicate",
                "distinct_decisions",
                "mixed_group",
                "unable_to_verify",
            ],
            "confidence_values": ["high", "medium", "low"],
            "database_writes_allowed": False,
        },
        "counts": {
            "review_items": len(review_items),
            "duplicate_groups": len(duplicate_groups),
            "duplicate_members": member_count,
        },
        "review_items": review_items,
        "duplicate_groups": duplicate_groups,
    }


def _csv_safe(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    elif isinstance(value, bool):
        text = "true" if value else "false"
    else:
        text = str(value)
    if text.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def _render_rows(fieldnames: tuple[str, ...], rows: list[dict[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="raise")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: _csv_safe(row.get(field)) for field in fieldnames})
    return ("\ufeff" + stream.getvalue()).encode("utf-8")


def render_review_items(bundle: dict[str, Any]) -> bytes:
    rows = []
    for item in bundle["review_items"]:
        row = {field: item.get(field) for field in REVIEW_ITEM_IMMUTABLE_FIELDS}
        row["queue_reasons"] = item.get("queue_reasons") or []
        row.update(item["review"])
        rows.append(row)
    return _render_rows(
        REVIEW_ITEM_IMMUTABLE_FIELDS + REVIEW_ITEM_EDITABLE_FIELDS, rows
    )


def render_duplicate_groups(bundle: dict[str, Any]) -> bytes:
    rows = []
    for group in bundle["duplicate_groups"]:
        row = {
            "group_id": group["group_id"],
            "candidate_class": group["candidate_class"],
            "authority_body": group.get("authority_body"),
            "normalized_number": group["normalized_number"],
            "member_count": group["member_count"],
            "signals_json": group["signals"],
            **group["review"],
        }
        rows.append(row)
    return _render_rows(
        DUPLICATE_GROUP_IMMUTABLE_FIELDS + DUPLICATE_GROUP_EDITABLE_FIELDS, rows
    )


def render_duplicate_members(bundle: dict[str, Any]) -> bytes:
    rows = []
    for group in bundle["duplicate_groups"]:
        for index, member in enumerate(group["members"], start=1):
            rows.append(
                {
                    "group_id": group["group_id"],
                    "candidate_class": group["candidate_class"],
                    "member_index": index,
                    **member,
                }
            )
    return _render_rows(DUPLICATE_MEMBER_FIELDS, rows)


def render_instructions(bundle: dict[str, Any]) -> bytes:
    counts = bundle["counts"]
    text = f"""# Full decision-facts expert review

Restricted scope: {counts['review_items']} fact-review items and
{counts['duplicate_groups']} duplicate-candidate groups containing
{counts['duplicate_members']} member documents.

1. Preserve the generated files as immutable evidence. Copy `review_items.csv`
   to `review_items.completed.csv` and `duplicate_groups.csv` to
   `duplicate_groups.completed.csv` before editing.
2. Open every official `source_url`; a title or candidate class is not evidence.
3. Complete every field verdict with only: `correct`, `incorrect`,
   `not_applicable`, `unable_to_verify`.
4. For an incorrect field, put a JSON object in `proposed_corrections_json`,
   add an exact `evidence_locator` and explain the legal basis.
5. A duplicate group verdict is only a proposal. List document IDs proposed
   for exclusion in `proposed_exclusions_json`; never edit `duplicate_members.csv`.
6. Outcome/in-favor corrections and duplicate exclusions require a distinct
   second reviewer. Set `review_state=complete` only after source verification.
7. Run the repository validator. Its correction manifest is proposal-only and
   cannot write to PostgreSQL.
8. `exact`, `likely` and `ambiguous` describe machine-comparison signals only;
   none of them is a legal duplicate verdict. Verify the act, authority, date,
   operative part and official source before choosing a verdict.
"""
    return text.encode("utf-8")


def _write_exclusive(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
    os.chmod(path, 0o600)


def materialize(output_dir: Path, bundle: dict[str, Any]) -> dict[str, str]:
    if output_dir.exists():
        raise FileExistsError(
            "output directory already exists; refusing to overwrite it"
        )
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(mode=0o700)
    os.chmod(output_dir, 0o700)
    payloads = {
        "review_bundle.json": json.dumps(bundle, ensure_ascii=False, indent=2).encode(
            "utf-8"
        )
        + b"\n",
        "review_items.csv": render_review_items(bundle),
        "duplicate_groups.csv": render_duplicate_groups(bundle),
        "duplicate_members.csv": render_duplicate_members(bundle),
        "REVIEW_INSTRUCTIONS.md": render_instructions(bundle),
    }
    hashes = {}
    for name, payload in payloads.items():
        _write_exclusive(output_dir / name, payload)
        hashes[name] = _sha256(payload)
    checksums = "".join(
        f"{digest}  {name}\n" for name, digest in sorted(hashes.items())
    )
    _write_exclusive(output_dir / "SHA256SUMS", checksums.encode("ascii"))
    return hashes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--expected-report-sha256")
    parser.add_argument("--expected-review-items", type=int)
    parser.add_argument("--expected-duplicate-groups", type=int)
    parser.add_argument("--expected-duplicate-members", type=int)
    args = parser.parse_args()

    report, report_sha256 = _read_restricted_export(args.input)
    bundle = build_bundle(report, report_sha256)
    summary = {**bundle["counts"], "report_sha256": report_sha256}
    prefix = "DECISION_FACTS_FULL_REVIEW_BUNDLE"
    if not args.execute:
        print(prefix + "_PLAN=" + json.dumps(summary, sort_keys=True))
        return 0

    if args.output_dir is None:
        parser.error("--output-dir is required with --execute")
    if not args.expected_report_sha256:
        parser.error("--expected-report-sha256 is required with --execute")
    if args.expected_report_sha256.lower() != report_sha256:
        raise ValueError("full expert-review report changed after dry run")
    checks = (
        (args.expected_review_items, bundle["counts"]["review_items"], "review items"),
        (
            args.expected_duplicate_groups,
            bundle["counts"]["duplicate_groups"],
            "duplicate groups",
        ),
        (
            args.expected_duplicate_members,
            bundle["counts"]["duplicate_members"],
            "duplicate members",
        ),
    )
    for expected, actual, label in checks:
        if expected is None or expected != actual:
            raise ValueError(f"{label} changed: expected {expected}, got {actual}")
    hashes = materialize(args.output_dir, bundle)
    print(
        prefix
        + "="
        + json.dumps(
            {**summary, "output_dir": str(args.output_dir), "files": hashes},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
