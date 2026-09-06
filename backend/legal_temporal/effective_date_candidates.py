"""Draft and approve effective-date metadata from captured Matsne edition hints.

The drafting stage extracts only exact, visible Matsne publication intervals.  It
does not mark any date as legally reviewed.  The approval stage requires an
explicit expert attestation and binds it to the exact plan, candidate report,
metadata and captured evidence.
"""

from __future__ import annotations

import csv
from datetime import UTC, date, datetime
import hashlib
import html
import io
import json
from pathlib import Path
import re
from typing import Any

from legal_temporal.publication_capture import (
    METADATA_FIELDS,
    _inspect_date_evidence,
    _read_metadata,
    _reviewed_at,
    read_capture_plan,
)
from legal_temporal.publication_editions import (
    MAX_SOURCE_BYTES,
    PublicationEditionValidationError,
    _bundle_file,
    _contains_block_page,
    _load_json_bytes,
    _read_bounded,
    _text,
    sha256_json,
)


EFFECTIVE_DATE_CANDIDATES_CONTRACT = "matsne-effective-date-candidates-v1"
EFFECTIVE_DATE_APPROVAL_CONTRACT = "matsne-effective-date-batch-approval-v1"
EFFECTIVE_DATE_CANDIDATE_IMPLEMENTATION = "publication-hint-chain-2026-09-06.1"
APPROVAL_PHRASE = "I_REVIEWED_THE_OFFICIAL_DATE_EVIDENCE"
MAX_REPORT_BYTES = 32 * 1024 * 1024

_DATE_FRAGMENT = r"\d{2}/\d{2}/\d{4}"
_HINT_RE = re.compile(
    r"<div\b(?=[^>]*\bclass=[\"'][^\"']*\bpublicationHint\b[^\"']*[\"'])"
    r"[^>]*>(?P<body>[\s\S]{0,8000}?)</div>",
    re.IGNORECASE,
)
_INTERVAL_RE = re.compile(
    rf"(?P<quote>(?:პირველადი\s+სახე|კონსოლიდირებული\s+ვერსია)\s*"
    rf"\(\s*(?P<start>{_DATE_FRAGMENT})\s*-\s*(?P<end>{_DATE_FRAGMENT})\s*\))"
)
_FINAL_RE = re.compile(r"კონსოლიდირებული\s+ვერსია\s*\(\s*საბოლოო\s*\)")
_ANCHOR_RE = re.compile(
    r"<a\b(?P<attrs>[^>]{0,4096})>(?P<body>[\s\S]{0,512}?)</a>",
    re.IGNORECASE,
)
_HREF_RE = re.compile(r"\bhref=[\"'](?P<value>[^\"']+)[\"']", re.IGNORECASE)
_CLASS_RE = re.compile(r"\bclass=[\"'](?P<value>[^\"']+)[\"']", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


def _date_from_display(value: str, field: str) -> date:
    try:
        return datetime.strptime(value, "%d/%m/%Y").date()
    except ValueError as exc:
        raise PublicationEditionValidationError(
            f"{field} must be a real DD/MM/YYYY date"
        ) from exc


def _display_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG_RE.sub(" ", value))).strip()


def _active_publication_date(
    source: str, *, document_id: str, publication: int
) -> str | None:
    expected_href = f"/ka/document/view/{document_id}?publication={publication}"
    matches: list[str] = []
    for anchor in _ANCHOR_RE.finditer(source):
        attrs = anchor.group("attrs")
        href = _HREF_RE.search(attrs)
        classes = _CLASS_RE.search(attrs)
        if href is None or href.group("value") != expected_href or classes is None:
            continue
        class_names = set(classes.group("value").split())
        if "active" not in class_names or "list-group-item" not in class_names:
            continue
        visible = _display_text(anchor.group("body"))
        if re.fullmatch(_DATE_FRAGMENT, visible):
            matches.append(visible)
    if len(matches) > 1:
        raise PublicationEditionValidationError(
            f"publication {publication} has multiple active sidebar dates"
        )
    return matches[0] if matches else None


def _inspect_page_hint(
    raw: bytes, *, document_id: str, publication: int
) -> dict[str, Any]:
    try:
        source = raw.decode("utf-8-sig")
    except UnicodeError as exc:
        raise PublicationEditionValidationError(
            f"publication {publication} page is not UTF-8"
        ) from exc
    if _contains_block_page(source[:200_000]):
        raise PublicationEditionValidationError(
            f"publication {publication} page is an access/challenge response"
        )
    hints = list(_HINT_RE.finditer(source))
    if len(hints) != 1:
        raise PublicationEditionValidationError(
            f"publication {publication} must have exactly one publication hint"
        )
    body = hints[0].group("body")
    intervals = list(_INTERVAL_RE.finditer(body))
    finals = list(_FINAL_RE.finditer(body))
    if len(intervals) > 1 or len(finals) > 1 or (intervals and finals):
        raise PublicationEditionValidationError(
            f"publication {publication} hint is ambiguous"
        )
    active_display = _active_publication_date(
        source, document_id=document_id, publication=publication
    )
    if intervals:
        match = intervals[0]
        start = _date_from_display(match.group("start"), "publication interval start")
        end = _date_from_display(match.group("end"), "publication interval end")
        return {
            "hint_kind": "bounded_interval",
            "visible_hint": _display_text(body),
            "quote": match.group("quote"),
            "start": start,
            "end": end,
            "reverse_interval": end < start,
            "active_date": (
                _date_from_display(active_display, "active publication date")
                if active_display
                else None
            ),
        }
    if len(finals) == 1:
        return {
            "hint_kind": "final",
            "visible_hint": _display_text(body),
            "quote": finals[0].group(0),
            "start": None,
            "end": None,
            "active_date": (
                _date_from_display(active_display, "active publication date")
                if active_display
                else None
            ),
        }
    raise PublicationEditionValidationError(
        f"publication {publication} hint has no supported exact interval"
    )


def _metadata_bytes(rows: list[dict[str, str]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=METADATA_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(
        {field: row.get(field, "") for field in METADATA_FIELDS} for row in rows
    )
    return b"\xef\xbb\xbf" + buffer.getvalue().encode("utf-8")


def _outside_bundle(path: Path, bundle: Path, *, label: str) -> None:
    candidate = path.resolve()
    root = bundle.resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return
    raise PublicationEditionValidationError(f"{label} must be outside the evidence bundle")


def _new_outputs(paths: tuple[Path, ...], bundle: Path) -> None:
    for path in paths:
        _outside_bundle(path, bundle, label=path.name)
        if path.exists() or path.is_symlink():
            raise PublicationEditionValidationError(f"output already exists: {path.name}")
        if not path.parent.is_dir() or path.parent.is_symlink():
            raise PublicationEditionValidationError(
                f"output parent must be an existing regular directory: {path.name}"
            )


def _write_new(path: Path, raw: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(raw)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _metadata_is_blank_candidate_target(row: dict[str, str]) -> bool:
    return (
        row["valid_from"] == ""
        and row["effective_date_quote"] == ""
        and row["date_evidence_state"] == "pending"
        and row["reviewer"] == ""
        and row["reviewed_at_utc"] == ""
        and row["rationale"] == ""
    )


def draft_effective_date_candidates(
    plan_path: Path,
    metadata_path: Path,
    bundle: Path,
    *,
    expected_plan_sha256: str,
    output_metadata: Path,
    report_output: Path,
) -> dict[str, Any]:
    """Create reviewable metadata candidates without confirming legal dates."""

    _new_outputs((output_metadata, report_output), bundle)
    if bundle.is_symlink() or not bundle.is_dir():
        raise PublicationEditionValidationError("capture bundle must be a regular directory")
    plan, plan_file_sha = read_capture_plan(plan_path)
    if plan["plan_sha256"] != expected_plan_sha256:
        raise PublicationEditionValidationError("capture plan identity pin mismatch")
    rows, input_metadata_sha = _read_metadata(metadata_path, plan)
    observations: list[dict[str, Any]] = []
    for item in plan["items"]:
        page_path = _bundle_file(bundle, item["page_file"], field="page file")
        raw = _read_bounded(
            page_path,
            MAX_SOURCE_BYTES,
            label=f"publication {item['publication']} page",
        )
        try:
            hint = _inspect_page_hint(
                raw,
                document_id=plan["act"]["document_id"],
                publication=item["publication"],
            )
            errors: list[str] = []
        except PublicationEditionValidationError as exc:
            hint = None
            errors = [str(exc)]
        observations.append(
            {
                "item": item,
                "page_sha256": hashlib.sha256(raw).hexdigest(),
                "hint": hint,
                "errors": errors,
            }
        )

    candidates: list[dict[str, Any]] = []
    output_rows = [dict(row) for row in rows]
    for index, (observation, row) in enumerate(
        zip(observations, output_rows, strict=True)
    ):
        item = observation["item"]
        publication = item["publication"]
        errors = list(observation["errors"])
        hint = observation["hint"]
        candidate_class: str | None = None
        valid_from: date | None = None
        interval_end: date | None = None
        evidence_item = item
        evidence_sha = observation["page_sha256"]
        evidence_quote: str | None = None
        active_match: bool | None = None
        chain_match: bool | None = None

        if not _metadata_is_blank_candidate_target(row):
            errors.append("metadata row already contains review work; it was not overwritten")
        if hint is not None and hint["hint_kind"] == "bounded_interval":
            candidate_class = "direct_publication_interval"
            valid_from = hint["start"]
            interval_end = hint["end"]
            evidence_quote = hint["quote"]
            if hint["reverse_interval"]:
                errors.append(
                    "official publication interval ends before it starts; "
                    "bitemporal legal review is required"
                )
            if hint["active_date"] is not None:
                active_match = hint["active_date"] == valid_from
                if not active_match:
                    errors.append("active sidebar date does not match interval start")
            elif publication != plan["range"]["first_publication"]:
                errors.append("non-initial bounded publication has no active sidebar date")
        elif hint is not None and hint["hint_kind"] == "final":
            candidate_class = "terminal_publication_chain"
            if index == 0:
                errors.append("terminal publication has no preceding interval")
            else:
                previous = observations[index - 1]
                previous_hint = previous["hint"]
                if (
                    previous_hint is None
                    or previous_hint["hint_kind"] != "bounded_interval"
                ):
                    errors.append("terminal publication has no exact preceding interval")
                else:
                    valid_from = previous_hint["end"]
                    evidence_quote = previous_hint["quote"]
                    evidence_item = previous["item"]
                    evidence_sha = previous["page_sha256"]
                    active_match = hint["active_date"] == valid_from
                    if hint["active_date"] is None:
                        errors.append("terminal publication has no active sidebar date")
                    elif not active_match:
                        errors.append(
                            "terminal active date does not match preceding interval end"
                        )

        if index > 0 and hint is not None and hint["hint_kind"] == "bounded_interval":
            previous_hint = observations[index - 1]["hint"]
            if previous_hint is not None and previous_hint["hint_kind"] == "bounded_interval":
                chain_match = previous_hint["end"] == hint["start"]
                if not chain_match:
                    errors.append("preceding interval end does not match interval start")

        if valid_from is None or evidence_quote is None:
            if not errors:
                errors.append("no exact effective-date candidate")
        candidates.append(
            {
                "publication": publication,
                "status": "candidate" if not errors else "blocked",
                "candidate_class": candidate_class,
                "valid_from": valid_from.isoformat() if valid_from else None,
                "interval_end": interval_end.isoformat() if interval_end else None,
                "evidence": (
                    {
                        "official_url": evidence_item["page_url"],
                        "file": evidence_item["page_file"],
                        "sha256": evidence_sha,
                        "quote": evidence_quote,
                    }
                    if evidence_quote is not None
                    else None
                ),
                "checks": {
                    "active_sidebar_matches": active_match,
                    "preceding_interval_chain_matches": chain_match,
                },
                "errors": errors,
            }
        )

    previous_safe_date: str | None = None
    for current in candidates:
        if current["status"] != "candidate":
            continue
        if previous_safe_date is not None and previous_safe_date > current["valid_from"]:
            current["status"] = "blocked"
            current["errors"].append(
                "candidate effective date precedes the last non-blocked publication; "
                "bitemporal legal review is required"
            )
            continue
        previous_safe_date = current["valid_from"]

    for row, candidate in zip(output_rows, candidates, strict=True):
        if candidate["status"] != "candidate":
            continue
        evidence = candidate["evidence"]
        row.update(
            {
                "valid_from": candidate["valid_from"],
                "effective_date_evidence_url": evidence["official_url"],
                "effective_date_evidence_file": evidence["file"],
                "effective_date_quote": evidence["quote"],
            }
        )

    candidate_count = sum(item["status"] == "candidate" for item in candidates)
    blocked_count = len(candidates) - candidate_count
    metadata_raw = _metadata_bytes(output_rows)
    output_metadata_sha = hashlib.sha256(metadata_raw).hexdigest()
    unsigned_report = {
        "contract": EFFECTIVE_DATE_CANDIDATES_CONTRACT,
        "kind": "non_executable_effective_date_review_candidates",
        "implementation": EFFECTIVE_DATE_CANDIDATE_IMPLEMENTATION,
        "plan_sha256": plan["plan_sha256"],
        "plan_file_sha256": plan_file_sha,
        "input_metadata_sha256": input_metadata_sha,
        "output_metadata_sha256": output_metadata_sha,
        "act": plan["act"],
        "summary": {
            "planned_editions": len(plan["items"]),
            "candidate_editions": candidate_count,
            "direct_interval_candidates": sum(
                item["status"] == "candidate"
                and item["candidate_class"] == "direct_publication_interval"
                for item in candidates
            ),
            "terminal_chain_candidates": sum(
                item["status"] == "candidate"
                and item["candidate_class"] == "terminal_publication_chain"
                for item in candidates
            ),
            "blocked_editions": blocked_count,
            "date_evidence_confirmed": 0,
        },
        "complete": blocked_count == 0,
        "candidates": candidates,
        "database_writes_allowed": False,
        "public_answer_routing_changed": False,
        "expert_approval_required": True,
    }
    report = unsigned_report | {"report_sha256": sha256_json(unsigned_report)}
    report_raw = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode(
        "utf-8"
    )
    _write_new(output_metadata, metadata_raw)
    _write_new(report_output, report_raw)
    report["report_file_sha256"] = hashlib.sha256(report_raw).hexdigest()
    return report


def approve_effective_date_candidates(
    plan_path: Path,
    candidate_metadata_path: Path,
    candidate_report_path: Path,
    bundle: Path,
    *,
    expected_plan_sha256: str,
    expected_report_file_sha256: str,
    approval_phrase: str,
    reviewer: str,
    reviewed_at_utc: str,
    rationale: str,
    output_metadata: Path,
    approval_output: Path,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Apply one explicit expert attestation to a complete pinned candidate set."""

    _new_outputs((output_metadata, approval_output), bundle)
    now = now or datetime.now(UTC)
    if approval_phrase != APPROVAL_PHRASE:
        raise PublicationEditionValidationError("explicit expert approval phrase mismatch")
    plan, plan_file_sha = read_capture_plan(plan_path)
    if plan["plan_sha256"] != expected_plan_sha256:
        raise PublicationEditionValidationError("capture plan identity pin mismatch")
    report_raw = _read_bounded(
        candidate_report_path, MAX_REPORT_BYTES, label="effective-date candidate report"
    )
    if hashlib.sha256(report_raw).hexdigest() != expected_report_file_sha256:
        raise PublicationEditionValidationError("candidate report file hash pin mismatch")
    report = _load_json_bytes(report_raw, label="effective-date candidate report")
    embedded_report_sha = report.get("report_sha256")
    unsigned_report = dict(report)
    unsigned_report.pop("report_sha256", None)
    if (
        report.get("contract") != EFFECTIVE_DATE_CANDIDATES_CONTRACT
        or set(report)
        != {
            "contract",
            "kind",
            "implementation",
            "plan_sha256",
            "plan_file_sha256",
            "input_metadata_sha256",
            "output_metadata_sha256",
            "act",
            "summary",
            "complete",
            "candidates",
            "database_writes_allowed",
            "public_answer_routing_changed",
            "expert_approval_required",
            "report_sha256",
        }
        or embedded_report_sha != sha256_json(unsigned_report)
    ):
        raise PublicationEditionValidationError("candidate report contract or identity mismatch")
    if (
        report["plan_sha256"] != plan["plan_sha256"]
        or report["plan_file_sha256"] != plan_file_sha
        or report["act"] != plan["act"]
    ):
        raise PublicationEditionValidationError("candidate report plan binding mismatch")
    if report["summary"]["candidate_editions"] < 1:
        raise PublicationEditionValidationError("candidate report has no approvable rows")
    rows, candidate_metadata_sha = _read_metadata(candidate_metadata_path, plan)
    if candidate_metadata_sha != report["output_metadata_sha256"]:
        raise PublicationEditionValidationError("candidate metadata hash mismatch")
    candidates = report["candidates"]
    if not isinstance(candidates, list) or len(candidates) != len(rows):
        raise PublicationEditionValidationError("candidate report coverage mismatch")

    normalized_reviewer = _text(reviewer, "reviewer", 3, 255)
    normalized_reviewed_at = _reviewed_at(reviewed_at_utc, now=now)
    normalized_rationale = _text(rationale, "rationale", 20, 6000)
    confirmed_rows: list[dict[str, str]] = []
    previous_date: date | None = None
    approved_editions = 0
    pending_editions = 0
    for item, row, candidate in zip(plan["items"], rows, candidates, strict=True):
        evidence = candidate.get("evidence")
        if candidate.get("status") == "blocked":
            if not isinstance(candidate.get("errors"), list) or not candidate["errors"]:
                raise PublicationEditionValidationError(
                    f"blocked candidate has no reason at publication {item['publication']}"
                )
            confirmed_rows.append(dict(row))
            pending_editions += 1
            continue
        if (
            candidate.get("publication") != item["publication"]
            or candidate.get("status") != "candidate"
            or not isinstance(evidence, dict)
            or row["valid_from"] != candidate.get("valid_from")
            or row["effective_date_evidence_url"] != evidence.get("official_url")
            or row["effective_date_evidence_file"] != evidence.get("file")
            or row["effective_date_quote"] != evidence.get("quote")
            or row["date_evidence_state"] != "pending"
            or row["reviewer"]
            or row["reviewed_at_utc"]
            or row["rationale"]
        ):
            raise PublicationEditionValidationError(
                f"candidate metadata mismatch at publication {item['publication']}"
            )
        confirmed = dict(row)
        confirmed.update(
            {
                "date_evidence_state": "confirmed",
                "reviewer": normalized_reviewer,
                "reviewed_at_utc": normalized_reviewed_at,
                "rationale": normalized_rationale,
            }
        )
        inspected, errors = _inspect_date_evidence(bundle, confirmed, now=now)
        if inspected is None or errors:
            raise PublicationEditionValidationError(
                f"publication {item['publication']} evidence failed: {'; '.join(errors)}"
            )
        current_date = date.fromisoformat(inspected["valid_from"])
        if previous_date is not None and current_date < previous_date:
            raise PublicationEditionValidationError(
                "approved effective dates go backwards across publications"
            )
        previous_date = current_date
        confirmed_rows.append(confirmed)
        approved_editions += 1

    confirmed_raw = _metadata_bytes(confirmed_rows)
    confirmed_sha = hashlib.sha256(confirmed_raw).hexdigest()
    unsigned_approval = {
        "contract": EFFECTIVE_DATE_APPROVAL_CONTRACT,
        "kind": "expert_effective_date_batch_approval",
        "plan_sha256": plan["plan_sha256"],
        "plan_file_sha256": plan_file_sha,
        "candidate_report_file_sha256": expected_report_file_sha256,
        "candidate_report_sha256": report["report_sha256"],
        "candidate_metadata_sha256": candidate_metadata_sha,
        "confirmed_metadata_sha256": confirmed_sha,
        "approved_editions": approved_editions,
        "pending_editions": pending_editions,
        "complete": pending_editions == 0,
        "reviewer": normalized_reviewer,
        "reviewed_at_utc": normalized_reviewed_at,
        "rationale": normalized_rationale,
        "database_writes_allowed": False,
        "public_answer_routing_changed": False,
    }
    approval = unsigned_approval | {
        "approval_sha256": sha256_json(unsigned_approval)
    }
    approval_raw = (
        json.dumps(approval, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    _write_new(output_metadata, confirmed_raw)
    _write_new(approval_output, approval_raw)
    approval["approval_file_sha256"] = hashlib.sha256(approval_raw).hexdigest()
    return approval
