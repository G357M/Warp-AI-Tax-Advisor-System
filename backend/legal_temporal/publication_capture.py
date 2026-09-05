"""Plan, audit and finalize browser-captured Matsne publication evidence.

This module performs no network or database work.  It turns a publication
range into a deterministic capture packet, audits exact files saved through a
normal browser session, and builds the manifest consumed by
``publication_editions`` only when every publication and effective-date record
is complete.
"""

from __future__ import annotations

import csv
from datetime import UTC, date, datetime, timedelta
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any

from legal_temporal.publication_editions import (
    BUNDLE_CONTRACT,
    MAX_ARTICLES_PER_EDITION,
    MAX_EDITIONS,
    MAX_MANIFEST_BYTES,
    MAX_SOURCE_BYTES,
    PublicationEditionValidationError,
    _bundle_file,
    _contains_block_page,
    _iso_date,
    _load_json_bytes,
    _official_matsne_url,
    _read_bounded,
    _text,
    _tree_url,
    _validate_act,
    _validate_tree,
    extract_article_sections,
    sha256_json,
)


CAPTURE_PLAN_CONTRACT = "matsne-publication-capture-plan-v1"
CAPTURE_AUDIT_CONTRACT = "matsne-publication-capture-audit-v1"
CAPTURE_ADMISSION_CONTRACT = "matsne-publication-capture-admission-v1"
MAX_METADATA_BYTES = 16 * 1024 * 1024
PLAN_FIELDS = frozenset({"contract", "act", "range", "items", "plan_sha256"})
PLAN_RANGE_FIELDS = frozenset(
    {"first_publication", "last_publication", "publication_count"}
)
PLAN_ITEM_FIELDS = frozenset(
    {"publication", "page_url", "page_file", "tree_url", "tree_file"}
)
METADATA_FIELDS = (
    "publication",
    "page_url",
    "page_file",
    "tree_url",
    "tree_file",
    "valid_from",
    "effective_date_evidence_url",
    "effective_date_evidence_file",
    "effective_date_quote",
    "date_evidence_state",
    "reviewer",
    "reviewed_at_utc",
    "rationale",
    "notes",
)
DATE_STATES = frozenset({"pending", "confirmed", "defer"})
_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|\+00:00)$")
_GEORGIAN_MONTH_STEMS = (
    "იანვარ",
    "თებერვალ",
    "მარტ",
    "აპრილ",
    "მაის",
    "ივნის",
    "ივლის",
    "აგვისტ",
    "სექტემბერ",
    "ოქტომბერ",
    "ნოემბერ",
    "დეკემბერ",
)


def _integer(value: Any, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PublicationEditionValidationError(f"{field} must be an integer")
    if not minimum <= value <= maximum:
        raise PublicationEditionValidationError(
            f"{field} must be between {minimum} and {maximum}"
        )
    return value


def _relative_capture_file(value: str, *, field: str) -> str:
    raw = _text(value, field, 1, 512).replace("\\", "/")
    pure = PurePosixPath(raw)
    if (
        pure.is_absolute()
        or any(part in {"", ".", ".."} for part in pure.parts)
        or any(not re.fullmatch(r"[A-Za-z0-9._-]+", part) for part in pure.parts)
    ):
        raise PublicationEditionValidationError(f"{field} must be a safe relative path")
    return pure.as_posix()


def _edition_item(document_id: str, publication: int) -> dict[str, Any]:
    directory = f"editions/{publication:06d}"
    return {
        "publication": publication,
        "page_url": (
            f"https://matsne.gov.ge/ka/document/view/{document_id}"
            f"?publication={publication}"
        ),
        "page_file": f"{directory}/page.html",
        "tree_url": (
            f"https://matsne.gov.ge/ka/document/tree/{document_id}/{publication}"
        ),
        "tree_file": f"{directory}/tree.json",
    }


def build_capture_plan(
    act: dict[str, Any],
    *,
    first_publication: int,
    last_publication: int,
) -> dict[str, Any]:
    normalized_act = _validate_act(act)
    first = _integer(first_publication, "first_publication", 0, 1_000_000)
    last = _integer(last_publication, "last_publication", 0, 1_000_000)
    if last < first:
        raise PublicationEditionValidationError(
            "last_publication must not precede first_publication"
        )
    count = last - first + 1
    if count > MAX_EDITIONS:
        raise PublicationEditionValidationError(
            f"capture range exceeds the {MAX_EDITIONS}-edition limit"
        )
    unsigned = {
        "contract": CAPTURE_PLAN_CONTRACT,
        "act": normalized_act,
        "range": {
            "first_publication": first,
            "last_publication": last,
            "publication_count": count,
        },
        "items": [
            _edition_item(normalized_act["document_id"], publication)
            for publication in range(first, last + 1)
        ],
    }
    return unsigned | {"plan_sha256": sha256_json(unsigned)}


def _write_json_new(path: Path, value: dict[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        raise PublicationEditionValidationError(f"output already exists: {path.name}")
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _metadata_template(plan: dict[str, Any]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=METADATA_FIELDS, lineterminator="\n")
    writer.writeheader()
    for item in plan["items"]:
        writer.writerow(
            {
                **item,
                "valid_from": "",
                "effective_date_evidence_url": item["page_url"],
                "effective_date_evidence_file": item["page_file"],
                "effective_date_quote": "",
                "date_evidence_state": "pending",
                "reviewer": "",
                "reviewed_at_utc": "",
                "rationale": "",
                "notes": "",
            }
        )
    return buffer.getvalue()


def create_capture_packet(
    output_dir: Path,
    act: dict[str, Any],
    *,
    first_publication: int,
    last_publication: int,
) -> dict[str, Any]:
    if output_dir.exists() or output_dir.is_symlink():
        raise PublicationEditionValidationError("capture packet directory already exists")
    plan = build_capture_plan(
        act,
        first_publication=first_publication,
        last_publication=last_publication,
    )
    output_dir.mkdir(parents=True, mode=0o700)
    plan_path = output_dir / "capture_plan.json"
    metadata_path = output_dir / "edition_metadata.csv"
    try:
        _write_json_new(plan_path, plan)
        with metadata_path.open("x", encoding="utf-8-sig", newline="") as handle:
            handle.write(_metadata_template(plan))
        try:
            metadata_path.chmod(0o600)
        except OSError:
            pass
        for item in plan["items"]:
            (output_dir / PurePosixPath(item["page_file"]).parent).mkdir(
                parents=True, exist_ok=True, mode=0o700
            )
    except Exception:
        # Preserve any evidence that may already have appeared concurrently.
        # The caller gets an error and can inspect the new packet directory.
        raise
    return {
        "contract": CAPTURE_PLAN_CONTRACT,
        "plan_sha256": plan["plan_sha256"],
        "publication_count": plan["range"]["publication_count"],
        "capture_plan": str(plan_path),
        "edition_metadata": str(metadata_path),
        "first_page_url": plan["items"][0]["page_url"],
        "first_tree_url": plan["items"][0]["tree_url"],
        "database_writes_allowed": False,
        "public_answer_routing_changed": False,
    }


def read_capture_plan(path: Path) -> tuple[dict[str, Any], str]:
    raw = _read_bounded(path, MAX_MANIFEST_BYTES, label="capture plan")
    plan = _load_json_bytes(raw, label="capture plan")
    if set(plan) != PLAN_FIELDS or plan.get("contract") != CAPTURE_PLAN_CONTRACT:
        raise PublicationEditionValidationError("capture plan contract or fields mismatch")
    embedded = plan.get("plan_sha256")
    if not isinstance(embedded, str) or not re.fullmatch(r"[0-9a-f]{64}", embedded):
        raise PublicationEditionValidationError("capture plan has no valid identity")
    unsigned = dict(plan)
    unsigned.pop("plan_sha256")
    if sha256_json(unsigned) != embedded:
        raise PublicationEditionValidationError("capture plan content hash mismatch")
    act = _validate_act(plan["act"])
    range_value = plan["range"]
    if not isinstance(range_value, dict) or set(range_value) != PLAN_RANGE_FIELDS:
        raise PublicationEditionValidationError("capture plan range fields mismatch")
    first = _integer(range_value["first_publication"], "first publication", 0, 1_000_000)
    last = _integer(range_value["last_publication"], "last publication", 0, 1_000_000)
    count = _integer(range_value["publication_count"], "publication count", 1, MAX_EDITIONS)
    if last < first or count != last - first + 1:
        raise PublicationEditionValidationError("capture plan range is inconsistent")
    items = plan["items"]
    if not isinstance(items, list) or len(items) != count:
        raise PublicationEditionValidationError("capture plan item coverage mismatch")
    expected = [
        _edition_item(act["document_id"], publication)
        for publication in range(first, last + 1)
    ]
    if items != expected or any(
        not isinstance(item, dict) or set(item) != PLAN_ITEM_FIELDS for item in items
    ):
        raise PublicationEditionValidationError("capture plan items are not canonical")
    return plan, hashlib.sha256(raw).hexdigest()


def _read_metadata(path: Path, plan: dict[str, Any]) -> tuple[list[dict[str, str]], str]:
    raw = _read_bounded(path, MAX_METADATA_BYTES, label="edition metadata")
    try:
        decoded = raw.decode("utf-8-sig")
    except UnicodeError as exc:
        raise PublicationEditionValidationError("edition metadata is not UTF-8 CSV") from exc
    try:
        reader = csv.DictReader(io.StringIO(decoded, newline=""))
        if reader.fieldnames != list(METADATA_FIELDS):
            raise PublicationEditionValidationError("edition metadata columns mismatch")
        rows = list(reader)
    except csv.Error as exc:
        raise PublicationEditionValidationError("edition metadata is malformed CSV") from exc
    if len(rows) != len(plan["items"]):
        raise PublicationEditionValidationError("edition metadata row coverage mismatch")
    for index, (row, item) in enumerate(zip(rows, plan["items"], strict=True)):
        if None in row or any(value is None for value in row.values()):
            raise PublicationEditionValidationError("edition metadata has extra or missing cells")
        expected_immutable = {
            "publication": str(item["publication"]),
            "page_url": item["page_url"],
            "page_file": item["page_file"],
            "tree_url": item["tree_url"],
            "tree_file": item["tree_file"],
        }
        if any(row[key] != value for key, value in expected_immutable.items()):
            raise PublicationEditionValidationError(
                f"edition metadata immutable cells changed at row {index + 2}"
            )
        if row["date_evidence_state"] not in DATE_STATES:
            raise PublicationEditionValidationError(
                f"unknown date_evidence_state at row {index + 2}"
            )
        for field in METADATA_FIELDS[5:]:
            if len(row[field]) > 12_000:
                raise PublicationEditionValidationError(
                    f"edition metadata {field} exceeds its cell limit"
                )
    return rows, hashlib.sha256(raw).hexdigest()


def _reviewed_at(value: str, *, now: datetime) -> str:
    if not isinstance(value, str) or not _UTC_RE.fullmatch(value.strip()):
        raise PublicationEditionValidationError(
            "reviewed_at_utc must use YYYY-MM-DDTHH:MM:SSZ"
        )
    raw = value.strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PublicationEditionValidationError("reviewed_at_utc is invalid") from exc
    if parsed > now + timedelta(minutes=5):
        raise PublicationEditionValidationError("reviewed_at_utc is in the future")
    return parsed.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _quote_identifies_date(value: date, quote: str) -> bool:
    normalized = re.sub(r"\s+", " ", quote).casefold()
    numeric_candidates = {
        value.isoformat(),
        f"{value.day:02d}.{value.month:02d}.{value.year}",
        f"{value.day}.{value.month:02d}.{value.year}",
        f"{value.day}.{value.month}.{value.year}",
        f"{value.day:02d}/{value.month:02d}/{value.year}",
        f"{value.day}/{value.month}/{value.year}",
    }
    if any(candidate in normalized for candidate in numeric_candidates):
        return True
    month_stem = _GEORGIAN_MONTH_STEMS[value.month - 1]
    return bool(
        re.search(
            rf"\b{value.year}\s*წლის\s*0?{value.day}\s*{month_stem}",
            normalized,
        )
    )


def _inspect_date_evidence(
    bundle: Path,
    row: dict[str, str],
    *,
    now: datetime,
) -> tuple[dict[str, Any] | None, list[str]]:
    if row["date_evidence_state"] != "confirmed":
        return None, [f"effective_date_{row['date_evidence_state']}"]
    errors: list[str] = []
    result: dict[str, Any] | None = None
    try:
        valid_date = _iso_date(row["valid_from"], "valid_from")
        valid_from = valid_date.isoformat()
        official_url = _official_matsne_url(
            row["effective_date_evidence_url"], field="effective date evidence URL"
        )
        evidence_file = _relative_capture_file(
            row["effective_date_evidence_file"], field="effective date evidence file"
        )
        evidence_path = _bundle_file(
            bundle, evidence_file, field="effective date evidence file"
        )
        raw = _read_bounded(
            evidence_path, MAX_SOURCE_BYTES, label="effective-date evidence"
        )
        try:
            decoded = raw.decode("utf-8-sig")
        except UnicodeError as exc:
            raise PublicationEditionValidationError(
                "effective-date evidence is not UTF-8"
            ) from exc
        if _contains_block_page(decoded):
            raise PublicationEditionValidationError(
                "effective-date evidence is an access/challenge response"
            )
        quote = _text(row["effective_date_quote"], "effective date quote", 8, 4000)
        if quote not in decoded:
            raise PublicationEditionValidationError(
                "effective date quote is not verbatim in its captured source"
            )
        if not _quote_identifies_date(valid_date, quote):
            raise PublicationEditionValidationError(
                "effective date quote does not identify valid_from"
            )
        reviewer = _text(row["reviewer"], "reviewer", 3, 255)
        reviewed_at = _reviewed_at(row["reviewed_at_utc"], now=now)
        rationale = _text(row["rationale"], "rationale", 20, 6000)
        result = {
            "valid_from": valid_from,
            "effective_date_evidence": {
                "official_url": official_url,
                "file": evidence_file,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "quote": quote,
            },
            "review": {
                "state": "confirmed",
                "reviewer": reviewer,
                "reviewed_at_utc": reviewed_at,
                "rationale": rationale,
            },
        }
    except PublicationEditionValidationError as exc:
        errors.append(str(exc))
    return result, errors


def _inspect_capture(
    plan_path: Path,
    metadata_path: Path,
    bundle: Path,
    *,
    expected_plan_sha256: str,
    now: datetime | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    now = now or datetime.now(UTC)
    if bundle.is_symlink() or not bundle.is_dir():
        raise PublicationEditionValidationError("capture bundle must be a regular directory")
    plan, plan_file_sha = read_capture_plan(plan_path)
    if plan["plan_sha256"] != expected_plan_sha256:
        raise PublicationEditionValidationError("capture plan identity pin mismatch")
    rows, metadata_sha = _read_metadata(metadata_path, plan)
    details: list[dict[str, Any]] = []
    ready_editions: list[dict[str, Any]] = []
    counters = {
        "page_files_present": 0,
        "tree_files_present": 0,
        "source_pairs_valid": 0,
        "date_evidence_confirmed": 0,
        "ready_editions": 0,
    }
    total_source_bytes = 0
    previous_effective_date: date | None = None
    for item, row in zip(plan["items"], rows, strict=True):
        publication = item["publication"]
        errors: list[str] = []
        page_raw: bytes | None = None
        tree_raw: bytes | None = None
        page_path = _bundle_file(bundle, item["page_file"], field="page file")
        tree_path = _bundle_file(bundle, item["tree_file"], field="tree file")
        page_sha: str | None = None
        tree_sha: str | None = None
        article_count: int | None = None
        for kind, path in (("page", page_path), ("tree", tree_path)):
            if not path.exists():
                errors.append(f"missing_{kind}_file")
                continue
            try:
                raw = _read_bounded(
                    path, MAX_SOURCE_BYTES, label=f"publication {publication} {kind}"
                )
                if kind == "page":
                    page_raw = raw
                    counters["page_files_present"] += 1
                else:
                    tree_raw = raw
                    counters["tree_files_present"] += 1
                total_source_bytes += len(raw)
            except PublicationEditionValidationError as exc:
                errors.append(str(exc))
        if page_raw is not None:
            try:
                decoded_prefix = page_raw[:200_000].decode("utf-8-sig")
                if _contains_block_page(decoded_prefix):
                    errors.append("page_is_access_or_challenge_response")
                page_sha = hashlib.sha256(page_raw).hexdigest()
            except UnicodeError:
                errors.append("page_is_not_utf8")
        if tree_raw is not None:
            tree_sha = hashlib.sha256(tree_raw).hexdigest()
        if page_raw is not None and tree_raw is not None and not errors:
            try:
                tree = _validate_tree(tree_raw)
                articles, _exclusions = extract_article_sections(page_raw, tree)
                article_count = len(articles)
                if not 1 <= article_count <= MAX_ARTICLES_PER_EDITION:
                    raise PublicationEditionValidationError("article count is outside bounds")
                counters["source_pairs_valid"] += 1
            except PublicationEditionValidationError as exc:
                errors.append(str(exc))
        date_evidence, date_errors = _inspect_date_evidence(
            bundle, row, now=now
        )
        errors.extend(date_errors)
        if date_evidence is not None:
            counters["date_evidence_confirmed"] += 1
            current_effective_date = date.fromisoformat(date_evidence["valid_from"])
            if (
                previous_effective_date is not None
                and current_effective_date < previous_effective_date
            ):
                errors.append("effective dates go backwards across publications")
            previous_effective_date = current_effective_date
        ready = (
            not errors
            and page_sha is not None
            and tree_sha is not None
            and article_count is not None
            and date_evidence is not None
        )
        if ready:
            counters["ready_editions"] += 1
            ready_editions.append(
                {
                    **item,
                    "valid_from": date_evidence["valid_from"],
                    "page_sha256": page_sha,
                    "tree_sha256": tree_sha,
                    "expected_article_count": article_count,
                    "effective_date_evidence": date_evidence[
                        "effective_date_evidence"
                    ],
                    "review": date_evidence["review"],
                }
            )
        details.append(
            {
                "publication": publication,
                "ready": ready,
                "page_present": page_raw is not None,
                "tree_present": tree_raw is not None,
                "page_sha256": page_sha,
                "tree_sha256": tree_sha,
                "article_count": article_count,
                "date_evidence_state": row["date_evidence_state"],
                "errors": errors,
            }
        )
    pending = [detail for detail in details if not detail["ready"]]
    next_action = None
    if pending:
        first = pending[0]
        item = plan["items"][first["publication"] - plan["range"]["first_publication"]]
        next_action = {
            "publication": first["publication"],
            "page_url": item["page_url"],
            "page_file": item["page_file"],
            "tree_url": item["tree_url"],
            "tree_file": item["tree_file"],
            "errors": first["errors"],
        }
    report = {
        "contract": CAPTURE_AUDIT_CONTRACT,
        "kind": "read_only_offline_capture_audit",
        "plan_sha256": plan["plan_sha256"],
        "plan_file_sha256": plan_file_sha,
        "metadata_sha256": metadata_sha,
        "act": plan["act"],
        "summary": {
            "planned_editions": len(plan["items"]),
            **counters,
            "pending_editions": len(pending),
            "total_source_bytes_observed": total_source_bytes,
        },
        "complete": not pending,
        "next_action": next_action,
        "details": details,
        "database_writes_allowed": False,
        "public_answer_routing_changed": False,
    }
    report["audit_sha256"] = sha256_json(report)
    return report, ready_editions


def audit_capture_packet(
    plan_path: Path,
    metadata_path: Path,
    bundle: Path,
    *,
    expected_plan_sha256: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    report, _ready = _inspect_capture(
        plan_path,
        metadata_path,
        bundle,
        expected_plan_sha256=expected_plan_sha256,
        now=now,
    )
    return report


def finalize_capture_packet(
    plan_path: Path,
    metadata_path: Path,
    bundle: Path,
    *,
    expected_plan_sha256: str,
    manifest_output: Path,
    admission_output: Path,
    now: datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    for output in (manifest_output, admission_output):
        if output.exists() or output.is_symlink():
            raise PublicationEditionValidationError(
                f"output already exists: {output.name}"
            )
    report, editions = _inspect_capture(
        plan_path,
        metadata_path,
        bundle,
        expected_plan_sha256=expected_plan_sha256,
        now=now,
    )
    if not report["complete"]:
        raise PublicationEditionValidationError(
            "capture packet is incomplete; run the audit and resolve next_action"
        )
    manifest = {
        "contract": BUNDLE_CONTRACT,
        "act": report["act"],
        "editions": [
            {
                key: edition[key]
                for key in (
                    "publication",
                    "valid_from",
                    "page_url",
                    "page_file",
                    "page_sha256",
                    "tree_url",
                    "tree_file",
                    "tree_sha256",
                    "expected_article_count",
                    "effective_date_evidence",
                )
            }
            for edition in editions
        ],
    }
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    admission = {
        "contract": CAPTURE_ADMISSION_CONTRACT,
        "kind": "non_executable_capture_admission_evidence",
        "plan_sha256": report["plan_sha256"],
        "metadata_sha256": report["metadata_sha256"],
        "capture_audit_sha256": report["audit_sha256"],
        "manifest_sha256": manifest_sha,
        "act": report["act"],
        "summary": report["summary"],
        "date_reviews": [
            {
                "publication": edition["publication"],
                "valid_from": edition["valid_from"],
                **edition["review"],
            }
            for edition in editions
        ],
        "database_writes_allowed": False,
        "public_answer_routing_changed": False,
        "authoritative_versions_created": 0,
    }
    admission["admission_sha256"] = sha256_json(admission)
    if manifest_output.parent.resolve() != bundle.resolve():
        raise PublicationEditionValidationError(
            "manifest output must be the capture bundle directory"
        )
    if admission_output.parent.resolve() != bundle.resolve():
        raise PublicationEditionValidationError(
            "admission output must be the capture bundle directory"
        )
    manifest_output.parent.mkdir(parents=True, exist_ok=True)
    admission_output.parent.mkdir(parents=True, exist_ok=True)
    with manifest_output.open("xb") as handle:
        handle.write(manifest_bytes)
    try:
        _write_json_new(admission_output, admission)
    except Exception:
        # Manifest is a new derived file, never source evidence.  Leave it in
        # place so the failed partial finalization is visible and recoverable.
        raise
    for output in (manifest_output, admission_output):
        try:
            output.chmod(0o600)
        except OSError:
            pass
    return manifest, admission


def compact_audit(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "contract": report["contract"],
        "plan_sha256": report["plan_sha256"],
        "audit_sha256": report["audit_sha256"],
        **report["summary"],
        "complete": report["complete"],
        "next_action": report["next_action"],
        "database_writes_allowed": report["database_writes_allowed"],
        "public_answer_routing_changed": report["public_answer_routing_changed"],
    }
