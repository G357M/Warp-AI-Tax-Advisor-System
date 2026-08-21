#!/usr/bin/env python
"""Safely import an expert-review XLSX worksheet into a validator-ready CSV.

The importer is stdlib-only, never connects to PostgreSQL or an LLM, and is
dry-run-first.  It accepts plain-text OOXML cells only, rejects formulas,
macros and external relationships, verifies immutable columns against the
signed review bundle, normalizes JSON fields and writes a new mode-0600 CSV
only when every dry-run hash and count is supplied explicitly.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import posixpath
import re
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any
from xml.etree import ElementTree


SCRIPT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_ROOT))

import build_decision_facts_full_review_bundle as bundle_builder  # noqa: E402
import validate_decision_facts_expert_review as review_validator  # noqa: E402


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CELL_REFERENCE = re.compile(r"^([A-Z]+)([1-9][0-9]*)$")
MAX_WORKBOOK_BYTES = 25 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 256
MAX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_XML_BYTES = 50 * 1024 * 1024


REVIEW_TYPES = {
    "duplicate-groups": {
        "default_sheet": "duplicate_groups completed",
        "identity": "group_id",
        "immutable": bundle_builder.DUPLICATE_GROUP_IMMUTABLE_FIELDS,
        "editable": bundle_builder.DUPLICATE_GROUP_EDITABLE_FIELDS,
        "json_fields": {"proposed_exclusions_json": list},
    },
    "review-items": {
        "default_sheet": "review_items completed",
        "identity": "review_id",
        "immutable": bundle_builder.REVIEW_ITEM_IMMUTABLE_FIELDS,
        "editable": bundle_builder.REVIEW_ITEM_EDITABLE_FIELDS,
        "json_fields": {"proposed_corrections_json": dict},
    },
}


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_restricted(path: Path, *, label: str) -> bytes:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{label} must be a regular file, not a symlink")
    if os.name == "posix":
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:
            raise PermissionError(
                f"{label} permissions must be 0600-compatible, got {mode:04o}"
            )
    payload = path.read_bytes()
    if label == "workbook" and len(payload) > MAX_WORKBOOK_BYTES:
        raise ValueError("workbook exceeds the 25 MiB safety limit")
    return payload


def _safe_xml(payload: bytes, *, member: str) -> ElementTree.Element:
    if len(payload) > MAX_XML_BYTES:
        raise ValueError(f"XLSX XML member is too large: {member}")
    lowered = payload[:4096].lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise ValueError(f"DTD/entity declarations are prohibited: {member}")
    try:
        return ElementTree.fromstring(payload)
    except ElementTree.ParseError as exc:
        raise ValueError(f"invalid XLSX XML: {member}") from exc


def _validate_archive(archive: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    infos = archive.infolist()
    if len(infos) > MAX_ARCHIVE_MEMBERS:
        raise ValueError("XLSX contains too many archive members")
    members: dict[str, zipfile.ZipInfo] = {}
    total = 0
    for info in infos:
        name = info.filename
        pure = PurePosixPath(name)
        if (
            not name
            or "\\" in name
            or pure.is_absolute()
            or ".." in pure.parts
            or name in members
        ):
            raise ValueError(f"unsafe XLSX archive member: {name!r}")
        if info.flag_bits & 0x1:
            raise ValueError("encrypted XLSX members are prohibited")
        total += info.file_size
        if total > MAX_UNCOMPRESSED_BYTES:
            raise ValueError("XLSX uncompressed content exceeds the safety limit")
        members[name] = info
    required = {
        "[Content_Types].xml",
        "xl/workbook.xml",
        "xl/_rels/workbook.xml.rels",
    }
    missing = sorted(required - set(members))
    if missing:
        raise ValueError(f"XLSX is missing required members: {missing}")
    lowered_names = {name.lower() for name in members}
    if "xl/vbaproject.bin" in lowered_names or any(
        name.startswith("xl/externallinks/") for name in lowered_names
    ):
        raise ValueError("macros and external workbook links are prohibited")
    return members


def _read_member(
    archive: zipfile.ZipFile,
    members: dict[str, zipfile.ZipInfo],
    name: str,
) -> bytes:
    if name not in members:
        raise ValueError(f"XLSX member is missing: {name}")
    return archive.read(members[name])


def _reject_active_content(
    archive: zipfile.ZipFile, members: dict[str, zipfile.ZipInfo]
) -> None:
    content_types = _read_member(archive, members, "[Content_Types].xml")
    lowered = content_types.lower()
    if b"macroenabled" in lowered or b"vbaproject" in lowered:
        raise ValueError("macro-enabled XLSX content is prohibited")
    for name in sorted(member for member in members if member.endswith(".rels")):
        root = _safe_xml(_read_member(archive, members, name), member=name)
        for relationship in root.findall(f"{{{PACKAGE_REL_NS}}}Relationship"):
            if relationship.get("TargetMode", "").casefold() == "external":
                raise ValueError("external XLSX relationships are prohibited")
    for name in sorted(
        member
        for member in members
        if member.startswith("xl/worksheets/") and member.endswith(".xml")
    ):
        root = _safe_xml(_read_member(archive, members, name), member=name)
        if root.find(f".//{{{MAIN_NS}}}f") is not None:
            raise ValueError(f"worksheet formulas are prohibited: {name}")


def _worksheet_member(
    archive: zipfile.ZipFile,
    members: dict[str, zipfile.ZipInfo],
    sheet_name: str,
) -> str:
    workbook = _safe_xml(
        _read_member(archive, members, "xl/workbook.xml"),
        member="xl/workbook.xml",
    )
    relationship_id = None
    for sheet in workbook.findall(f".//{{{MAIN_NS}}}sheet"):
        if sheet.get("name") == sheet_name:
            relationship_id = sheet.get(f"{{{OFFICE_REL_NS}}}id")
            break
    if not relationship_id:
        available = [
            sheet.get("name", "")
            for sheet in workbook.findall(f".//{{{MAIN_NS}}}sheet")
        ]
        raise ValueError(
            f"worksheet {sheet_name!r} not found; available sheets: {available}"
        )
    relationships = _safe_xml(
        _read_member(archive, members, "xl/_rels/workbook.xml.rels"),
        member="xl/_rels/workbook.xml.rels",
    )
    target = None
    for relationship in relationships.findall(f"{{{PACKAGE_REL_NS}}}Relationship"):
        if relationship.get("Id") == relationship_id:
            target = relationship.get("Target")
            break
    if not target:
        raise ValueError("worksheet relationship target is missing")
    if ".." in PurePosixPath(target.lstrip("/")).parts:
        raise ValueError("worksheet relationship target is unsafe")
    if target.startswith("/"):
        normalized = posixpath.normpath(target.lstrip("/"))
    else:
        normalized = posixpath.normpath(posixpath.join("xl", target))
    if not normalized.startswith("xl/worksheets/") or normalized not in members:
        raise ValueError("worksheet relationship target is unsafe")
    return normalized


def _shared_strings(
    archive: zipfile.ZipFile, members: dict[str, zipfile.ZipInfo]
) -> list[str]:
    name = "xl/sharedStrings.xml"
    if name not in members:
        return []
    root = _safe_xml(_read_member(archive, members, name), member=name)
    return [
        "".join(text.text or "" for text in item.iter(f"{{{MAIN_NS}}}t"))
        for item in root.findall(f"{{{MAIN_NS}}}si")
    ]


def _column_index(letters: str) -> int:
    index = 0
    for letter in letters:
        index = index * 26 + ord(letter) - ord("A") + 1
    return index


def _cell_text(cell: ElementTree.Element, shared: list[str], reference: str) -> str:
    cell_type = cell.get("t")
    value_node = cell.find(f"{{{MAIN_NS}}}v")
    if cell_type == "s":
        if value_node is None or value_node.text is None:
            raise ValueError(f"shared-string cell is missing its index: {reference}")
        try:
            index = int(value_node.text)
            return shared[index]
        except (ValueError, IndexError) as exc:
            raise ValueError(f"invalid shared-string index: {reference}") from exc
    if cell_type == "inlineStr":
        inline = cell.find(f"{{{MAIN_NS}}}is")
        if inline is None:
            return ""
        return "".join(text.text or "" for text in inline.iter(f"{{{MAIN_NS}}}t"))
    if cell_type == "str":
        return "" if value_node is None or value_node.text is None else value_node.text
    if value_node is None or value_node.text in {None, ""}:
        return ""
    raise ValueError(
        f"all populated worksheet cells must be stored as text: {reference}"
    )


def read_text_worksheet(
    workbook_payload: bytes, *, sheet_name: str, expected_columns: int
) -> list[list[str]]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(workbook_payload))
    except zipfile.BadZipFile as exc:
        raise ValueError("workbook is not a valid XLSX ZIP container") from exc
    with archive:
        members = _validate_archive(archive)
        _reject_active_content(archive, members)
        sheet_member = _worksheet_member(archive, members, sheet_name)
        shared = _shared_strings(archive, members)
        sheet = _safe_xml(
            _read_member(archive, members, sheet_member), member=sheet_member
        )
        if sheet.find(f".//{{{MAIN_NS}}}mergeCell") is not None:
            raise ValueError("merged worksheet cells are prohibited")
        cells: dict[tuple[int, int], str] = {}
        maximum_row = 0
        for cell in sheet.findall(f".//{{{MAIN_NS}}}c"):
            reference = (cell.get("r") or "").upper()
            match = CELL_REFERENCE.fullmatch(reference)
            if not match:
                raise ValueError(f"invalid worksheet cell reference: {reference!r}")
            column = _column_index(match.group(1))
            row = int(match.group(2))
            value = _cell_text(cell, shared, reference)
            if column > expected_columns:
                if value:
                    raise ValueError(
                        f"unexpected populated cell outside the review table: {reference}"
                    )
                continue
            identity = (row, column)
            if identity in cells:
                raise ValueError(f"duplicate worksheet cell: {reference}")
            cells[identity] = value
            if value:
                maximum_row = max(maximum_row, row)
        if maximum_row < 1:
            raise ValueError("worksheet is empty")
        return [
            [cells.get((row, column), "") for column in range(1, expected_columns + 1)]
            for row in range(1, maximum_row + 1)
        ]


def _expected_rows(
    bundle: dict[str, Any], review_type: str
) -> tuple[dict[str, dict[str, str]], list[str]]:
    if review_type == "duplicate-groups":
        expected = review_validator._expected_duplicate_rows(bundle)
        order = [group["group_id"] for group in bundle["duplicate_groups"]]
    else:
        expected = review_validator._expected_review_rows(bundle)
        order = [item["review_id"] for item in bundle["review_items"]]
    return expected, order


def _normalize_json(value: str, expected_type: type, label: str) -> str:
    raw = value.strip() or ("[]" if expected_type is list else "{}")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label}: invalid JSON") from exc
    if not isinstance(payload, expected_type):
        raise ValueError(f"{label}: expected {expected_type.__name__}")
    if expected_type is list and any(not isinstance(item, str) for item in payload):
        raise ValueError(f"{label}: every list item must be a string")
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def _validate_attribution_pairs(row: dict[str, str], identity: str) -> None:
    pairs = (
        ("reviewer", "reviewed_at_utc"),
        ("second_reviewer", "second_reviewed_at_utc"),
    )
    for reviewer_field, timestamp_field in pairs:
        reviewer = row[reviewer_field].strip()
        timestamp = row[timestamp_field].strip()
        if bool(reviewer) != bool(timestamp):
            raise ValueError(
                f"{identity}: {reviewer_field} and {timestamp_field} must be filled together"
            )
        if timestamp and not review_validator._parse_utc(timestamp):
            raise ValueError(
                f"{identity}: {timestamp_field} must be an aware UTC timestamp"
            )


def _validate_pending_duplicate(
    bundle: dict[str, Any], row: dict[str, str], identity: str
) -> None:
    allowed_verdicts = {
        "",
        "true_duplicate",
        "distinct_decisions",
        "mixed_group",
        "unable_to_verify",
    }
    verdict = row["duplicate_verdict"].strip()
    if verdict not in allowed_verdicts:
        raise ValueError(f"{identity}: invalid duplicate_verdict")
    group = next(
        group for group in bundle["duplicate_groups"] if group["group_id"] == identity
    )
    members = {str(member["document_id"]) for member in group["members"]}
    canonical = row["canonical_document_id"].strip()
    exclusions = json.loads(row["proposed_exclusions_json"])
    if len(exclusions) != len(set(exclusions)):
        raise ValueError(f"{identity}: proposed exclusions contain duplicates")
    if set(exclusions) - members:
        raise ValueError(f"{identity}: exclusions are not group members")
    if verdict in {"true_duplicate", "mixed_group"}:
        if canonical not in members:
            raise ValueError(
                f"{identity}: canonical_document_id must be a group member"
            )
        if not exclusions or canonical in exclusions:
            raise ValueError(f"{identity}: invalid duplicate exclusion proposal")
        if verdict == "true_duplicate" and set(exclusions) != members - {canonical}:
            raise ValueError(
                f"{identity}: true duplicate must account for every other member"
            )
    elif canonical or exclusions:
        raise ValueError(
            f"{identity}: non-duplicate or blank verdict cannot propose exclusions"
        )


def _validate_pending_review_item(row: dict[str, str], identity: str) -> None:
    allowed_verdicts = {
        "",
        "correct",
        "incorrect",
        "not_applicable",
        "unable_to_verify",
    }
    for field in bundle_builder.FIELD_VERIFICATIONS:
        if row[field].strip() not in allowed_verdicts:
            raise ValueError(f"{identity}: invalid verdict for {field}")
    corrections = json.loads(row["proposed_corrections_json"])
    unknown = sorted(set(corrections) - review_validator.ALLOWED_CORRECTION_FIELDS)
    if unknown:
        raise ValueError(f"{identity}: unknown correction fields: {unknown}")


def build_import(
    bundle: dict[str, Any],
    matrix: list[list[str]],
    *,
    review_type: str,
) -> tuple[list[dict[str, str]], bytes, dict[str, int]]:
    contract = REVIEW_TYPES[review_type]
    fields = tuple(contract["immutable"]) + tuple(contract["editable"])
    headers = tuple(value.removeprefix("\ufeff") for value in matrix[0])
    if headers != fields:
        raise ValueError("unexpected workbook columns or column order")
    source_rows = [dict(zip(fields, values, strict=True)) for values in matrix[1:]]
    expected, order = _expected_rows(bundle, review_type)
    if len(source_rows) != len(expected):
        raise ValueError(
            f"worksheet row count changed: expected {len(expected)}, got {len(source_rows)}"
        )
    identity_field = str(contract["identity"])
    actual: dict[str, dict[str, str]] = {}
    for row in source_rows:
        identity = row[identity_field].strip()
        if not identity:
            raise ValueError(f"{identity_field}: blank worksheet identity")
        if identity in actual:
            raise ValueError(f"{identity}: duplicate worksheet row")
        if identity not in expected:
            raise ValueError(f"{identity}: unknown worksheet identity")
        for field in contract["immutable"]:
            if row[field] != expected[identity][field]:
                raise ValueError(f"{identity}: immutable field changed: {field}")
        actual[identity] = row
    missing = sorted(set(expected) - set(actual))
    if missing:
        raise ValueError(f"worksheet rows are missing: {missing[:5]}")

    output_rows = []
    for identity in order:
        source = actual[identity]
        row = dict(expected[identity])
        row.update({field: source[field] for field in contract["editable"]})
        state = row["review_state"].strip()
        if state not in {"pending", "complete"}:
            raise ValueError(f"{identity}: review_state must be pending or complete")
        for field, expected_type in contract["json_fields"].items():
            row[field] = _normalize_json(
                row[field], expected_type, f"{identity} {field}"
            )
        _validate_attribution_pairs(row, identity)
        if review_type == "duplicate-groups":
            _validate_pending_duplicate(bundle, row, identity)
        else:
            _validate_pending_review_item(row, identity)
        output_rows.append(row)

    if review_type == "duplicate-groups":
        counts, _, errors = review_validator.validate_duplicate_groups(
            bundle, output_rows, require_complete=False
        )
        prefilled = sum(
            row["review_state"] == "pending"
            and any(
                row[field].strip()
                for field in contract["editable"]
                if field not in {"review_state", "proposed_exclusions_json"}
            )
            for row in output_rows
        )
    else:
        counts, _, errors = review_validator.validate_review_items(
            bundle, output_rows, require_complete=False
        )
        prefilled = sum(
            row["review_state"] == "pending"
            and any(
                row[field].strip()
                for field in contract["editable"]
                if field not in {"review_state", "proposed_corrections_json"}
            )
            for row in output_rows
        )
    if errors:
        raise ValueError("workbook review validation failed: " + "; ".join(errors[:10]))

    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="raise")
    writer.writeheader()
    for row in output_rows:
        writer.writerow(
            {field: bundle_builder._csv_safe(row[field]) for field in fields}
        )
    payload = ("\ufeff" + stream.getvalue()).encode("utf-8")
    summary_counts = {
        "rows": len(output_rows),
        "completed": counts["completed"],
        "pending": counts["pending"],
        "prefilled_pending": prefilled,
    }
    return output_rows, payload, summary_counts


def _write_exclusive(path: Path, payload: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise FileExistsError("output already exists; refusing to overwrite it")
    if not path.parent.is_dir() or path.parent.is_symlink():
        raise ValueError("output parent must be an existing regular directory")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
    os.chmod(path, 0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--review-type", choices=tuple(REVIEW_TYPES), required=True)
    parser.add_argument("--sheet-name")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--expected-bundle-sha256")
    parser.add_argument("--expected-workbook-sha256")
    parser.add_argument("--expected-output-sha256")
    parser.add_argument("--expected-rows", type=int)
    args = parser.parse_args()

    bundle, bundle_raw = review_validator._load_bundle(args.bundle)
    workbook_raw = _read_restricted(args.workbook, label="workbook")
    contract = REVIEW_TYPES[args.review_type]
    sheet_name = args.sheet_name or str(contract["default_sheet"])
    column_count = len(contract["immutable"]) + len(contract["editable"])
    matrix = read_text_worksheet(
        workbook_raw, sheet_name=sheet_name, expected_columns=column_count
    )
    _, output_payload, counts = build_import(
        bundle, matrix, review_type=args.review_type
    )
    summary = {
        "review_type": args.review_type,
        "sheet_name": sheet_name,
        **counts,
        "bundle_sha256": _sha256(bundle_raw),
        "workbook_sha256": _sha256(workbook_raw),
        "output_sha256": _sha256(output_payload),
        "postgresql_writes_allowed": False,
        "llm_calls_allowed": False,
    }
    prefix = "DECISION_FACTS_REVIEW_WORKBOOK_IMPORT"
    if not args.execute:
        print(prefix + "_PLAN=" + json.dumps(summary, sort_keys=True))
        return 0

    if args.output is None:
        parser.error("--output is required with --execute")
    expected = {
        "bundle_sha256": args.expected_bundle_sha256,
        "workbook_sha256": args.expected_workbook_sha256,
        "output_sha256": args.expected_output_sha256,
    }
    for field, supplied in expected.items():
        if not supplied:
            parser.error(
                f"--expected-{field.replace('_', '-')} is required with --execute"
            )
        if supplied.lower() != summary[field]:
            raise ValueError(f"{field} changed after dry run")
    if args.expected_rows is None or args.expected_rows != summary["rows"]:
        raise ValueError(
            f"worksheet row count changed: expected {args.expected_rows}, got {summary['rows']}"
        )
    _write_exclusive(args.output, output_payload)
    print(
        prefix
        + "="
        + json.dumps({**summary, "output": str(args.output)}, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
