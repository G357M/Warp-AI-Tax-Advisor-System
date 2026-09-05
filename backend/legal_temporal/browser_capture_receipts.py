"""Audit same-origin browser capture receipts for Matsne editions.

The browser collector is deliberately separate from legal interpretation.  It
records where and when exact response bodies were observed, while this module
recomputes every hash offline and rejects incomplete or inconsistent evidence.
It performs no network or database work.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
import hashlib
from pathlib import Path
import re
from typing import Any

from legal_temporal.publication_capture import read_capture_plan
from legal_temporal.publication_editions import (
    MAX_ARTICLES_PER_EDITION,
    MAX_SOURCE_BYTES,
    PublicationEditionValidationError,
    _bundle_file,
    _contains_block_page,
    _load_json_bytes,
    _read_bounded,
    _validate_tree,
    extract_article_sections,
    sha256_json,
)


BROWSER_RECEIPT_CONTRACT = "matsne-browser-capture-receipt-v1"
BROWSER_RECEIPT_AUDIT_CONTRACT = "matsne-browser-capture-receipt-audit-v1"
CAPTURE_METHOD = "same_origin_browser_fetch"
AUDITOR_IMPLEMENTATION = "indexed-dom-anchors-2026-09-06.4"
MAX_RECEIPT_BYTES = 64 * 1024
RECEIPT_FIELDS = frozenset(
    {
        "contract",
        "capture_method",
        "plan_sha256",
        "publication",
        "browser_origin",
        "completed_at_utc",
        "page",
        "tree",
        "database_writes_allowed",
        "public_answer_routing_changed",
    }
)
RESPONSE_FIELDS = frozenset(
    {
        "requested_url",
        "response_url",
        "file",
        "status",
        "content_type",
        "etag",
        "last_modified",
        "byte_length",
        "sha256",
        "fetched_at_utc",
    }
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$")
_DETAIL_FIELDS = frozenset(
    {
        "publication",
        "ready",
        "receipt_file",
        "receipt_sha256",
        "page_sha256",
        "tree_sha256",
        "article_count",
        "errors",
    }
)


def browser_receipt_file(publication: int) -> str:
    """Return the canonical sidecar path for one planned publication."""

    return f"editions/{publication:06d}/browser_capture_receipt.json"


def _utc_timestamp(value: Any, *, field: str, now: datetime) -> str:
    if not isinstance(value, str) or not _UTC_RE.fullmatch(value):
        raise PublicationEditionValidationError(
            f"{field} must use UTC ISO-8601 with seconds"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PublicationEditionValidationError(f"{field} is invalid") from exc
    if parsed > now + timedelta(minutes=5):
        raise PublicationEditionValidationError(f"{field} is in the future")
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _bounded_header(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or len(value) > 2_000:
        raise PublicationEditionValidationError(f"{field} must be bounded text")
    return value


def _validate_response_receipt(
    value: Any,
    *,
    kind: str,
    expected_url: str,
    expected_file: str,
    source_raw: bytes,
    now: datetime,
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != RESPONSE_FIELDS:
        raise PublicationEditionValidationError(f"{kind} receipt fields mismatch")
    if value["requested_url"] != expected_url or value["response_url"] != expected_url:
        raise PublicationEditionValidationError(f"{kind} receipt URL mismatch")
    if value["file"] != expected_file:
        raise PublicationEditionValidationError(f"{kind} receipt file mismatch")
    if isinstance(value["status"], bool) or value["status"] != 200:
        raise PublicationEditionValidationError(f"{kind} receipt status is not 200")
    content_type = _bounded_header(value["content_type"], field=f"{kind} content type")
    media_type = content_type.split(";", 1)[0].strip().casefold()
    expected_media = (
        {"text/html", "application/xhtml+xml"}
        if kind == "page"
        else {
            "application/json",
            "text/json",
            "text/plain",
            # Matsne can label its tree JSON as HTML. This declaration is
            # accepted only because _validate_tree independently parses the
            # exact stored body as strict JSON before an edition is ready.
            "text/html",
            "application/xhtml+xml",
        }
    )
    if media_type not in expected_media:
        raise PublicationEditionValidationError(
            f"{kind} receipt has unexpected content type"
        )
    _bounded_header(value["etag"], field=f"{kind} etag")
    _bounded_header(value["last_modified"], field=f"{kind} last-modified")
    if isinstance(value["byte_length"], bool) or value["byte_length"] != len(source_raw):
        raise PublicationEditionValidationError(f"{kind} receipt byte length mismatch")
    expected_sha = hashlib.sha256(source_raw).hexdigest()
    if not isinstance(value["sha256"], str) or not _SHA256_RE.fullmatch(value["sha256"]):
        raise PublicationEditionValidationError(f"{kind} receipt SHA-256 is invalid")
    if value["sha256"] != expected_sha:
        raise PublicationEditionValidationError(f"{kind} receipt SHA-256 mismatch")
    fetched_at = _utc_timestamp(
        value["fetched_at_utc"], field=f"{kind} fetched_at_utc", now=now
    )
    return {"sha256": expected_sha, "fetched_at_utc": fetched_at}


def _inspect_receipt(
    receipt_raw: bytes,
    *,
    item: dict[str, Any],
    page_raw: bytes,
    tree_raw: bytes,
    expected_plan_sha256: str,
    now: datetime,
) -> dict[str, Any]:
    receipt = _load_json_bytes(receipt_raw, label="browser capture receipt")
    if set(receipt) != RECEIPT_FIELDS:
        raise PublicationEditionValidationError("browser capture receipt fields mismatch")
    if receipt["contract"] != BROWSER_RECEIPT_CONTRACT:
        raise PublicationEditionValidationError("browser capture receipt contract mismatch")
    if receipt["capture_method"] != CAPTURE_METHOD:
        raise PublicationEditionValidationError("browser capture method mismatch")
    if receipt["plan_sha256"] != expected_plan_sha256:
        raise PublicationEditionValidationError("browser receipt plan pin mismatch")
    if receipt["publication"] != item["publication"]:
        raise PublicationEditionValidationError("browser receipt publication mismatch")
    if receipt["browser_origin"] != "https://matsne.gov.ge":
        raise PublicationEditionValidationError("browser receipt origin mismatch")
    if receipt["database_writes_allowed"] is not False:
        raise PublicationEditionValidationError("browser receipt database flag mismatch")
    if receipt["public_answer_routing_changed"] is not False:
        raise PublicationEditionValidationError("browser receipt routing flag mismatch")
    completed_at = _utc_timestamp(
        receipt["completed_at_utc"], field="completed_at_utc", now=now
    )
    page = _validate_response_receipt(
        receipt["page"],
        kind="page",
        expected_url=item["page_url"],
        expected_file=item["page_file"],
        source_raw=page_raw,
        now=now,
    )
    tree = _validate_response_receipt(
        receipt["tree"],
        kind="tree",
        expected_url=item["tree_url"],
        expected_file=item["tree_file"],
        source_raw=tree_raw,
        now=now,
    )
    completed = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
    for response in (page, tree):
        fetched = datetime.fromisoformat(
            response["fetched_at_utc"].replace("Z", "+00:00")
        )
        if fetched > completed + timedelta(seconds=1):
            raise PublicationEditionValidationError(
                "browser receipt completed before a response was fetched"
            )
    return receipt


def _reusable_ready_detail(
    value: Any,
    *,
    publication: int,
    receipt_file: str,
    page_sha256: str | None,
    tree_sha256: str | None,
    receipt_sha256: str | None,
) -> dict[str, Any] | None:
    """Accept one result only from an externally hash-pinned checkpoint.

    The caller remains responsible for authenticating the checkpoint envelope
    and binding it to ``AUDITOR_IMPLEMENTATION`` and the exact capture plan.
    This function additionally binds the reusable result to all three current
    files so changed evidence is always re-audited.
    """

    if not isinstance(value, Mapping) or set(value) != _DETAIL_FIELDS:
        return None
    article_count = value.get("article_count")
    if (
        value.get("publication") != publication
        or value.get("ready") is not True
        or value.get("receipt_file") != receipt_file
        or value.get("receipt_sha256") != receipt_sha256
        or value.get("page_sha256") != page_sha256
        or value.get("tree_sha256") != tree_sha256
        or isinstance(article_count, bool)
        or not isinstance(article_count, int)
        or not 1 <= article_count <= MAX_ARTICLES_PER_EDITION
        or value.get("errors") != []
    ):
        return None
    return dict(value)


def audit_browser_capture_receipts(
    plan_path: Path,
    bundle: Path,
    *,
    expected_plan_sha256: str,
    now: datetime | None = None,
    resume_details: Mapping[int, Mapping[str, Any]] | None = None,
    progress: Callable[[int, int, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Audit all planned browser receipts and exact response bodies read-only."""

    now = now or datetime.now(UTC)
    if bundle.is_symlink() or not bundle.is_dir():
        raise PublicationEditionValidationError("capture bundle must be a regular directory")
    plan, plan_file_sha = read_capture_plan(plan_path)
    if plan["plan_sha256"] != expected_plan_sha256:
        raise PublicationEditionValidationError("capture plan identity pin mismatch")

    counters = {
        "page_files_present": 0,
        "tree_files_present": 0,
        "receipts_present": 0,
        "source_pairs_valid": 0,
        "valid_receipts": 0,
    }
    total_bytes = 0
    details: list[dict[str, Any]] = []
    total_items = len(plan["items"])
    for completed_items, item in enumerate(plan["items"], start=1):
        errors: list[str] = []
        page_raw: bytes | None = None
        tree_raw: bytes | None = None
        receipt_raw: bytes | None = None
        page_path = _bundle_file(bundle, item["page_file"], field="page file")
        tree_path = _bundle_file(bundle, item["tree_file"], field="tree file")
        receipt_file = browser_receipt_file(item["publication"])
        receipt_path = _bundle_file(bundle, receipt_file, field="receipt file")

        for kind, path, limit in (
            ("page", page_path, MAX_SOURCE_BYTES),
            ("tree", tree_path, MAX_SOURCE_BYTES),
            ("receipt", receipt_path, MAX_RECEIPT_BYTES),
        ):
            if not path.exists() and not path.is_symlink():
                errors.append(f"missing_{kind}_file")
                continue
            try:
                raw = _read_bounded(path, limit, label=f"publication {item['publication']} {kind}")
                total_bytes += len(raw)
                if kind == "page":
                    page_raw = raw
                    counters["page_files_present"] += 1
                elif kind == "tree":
                    tree_raw = raw
                    counters["tree_files_present"] += 1
                else:
                    receipt_raw = raw
                    counters["receipts_present"] += 1
            except PublicationEditionValidationError as exc:
                errors.append(str(exc))

        page_sha = hashlib.sha256(page_raw).hexdigest() if page_raw else None
        tree_sha = hashlib.sha256(tree_raw).hexdigest() if tree_raw else None
        receipt_sha = hashlib.sha256(receipt_raw).hexdigest() if receipt_raw else None
        cached = _reusable_ready_detail(
            (resume_details or {}).get(item["publication"]),
            publication=item["publication"],
            receipt_file=receipt_file,
            page_sha256=page_sha,
            tree_sha256=tree_sha,
            receipt_sha256=receipt_sha,
        )

        article_count: int | None = None
        if cached is not None:
            article_count = cached["article_count"]
            counters["source_pairs_valid"] += 1
            counters["valid_receipts"] += 1
        elif page_raw is not None and tree_raw is not None:
            try:
                # Decode before applying the text-prefix limit inside
                # _contains_block_page. Slicing raw UTF-8 bytes at 200,000 can
                # split a Georgian code point and quarantine a valid edition.
                decoded = page_raw.decode("utf-8-sig")
                if _contains_block_page(decoded):
                    raise PublicationEditionValidationError(
                        "page is an access/challenge response"
                    )
                tree_value = _validate_tree(tree_raw)
                articles, _exclusions = extract_article_sections(page_raw, tree_value)
                article_count = len(articles)
                if not 1 <= article_count <= MAX_ARTICLES_PER_EDITION:
                    raise PublicationEditionValidationError(
                        "article count is outside bounds"
                    )
                counters["source_pairs_valid"] += 1
            except (UnicodeError, PublicationEditionValidationError) as exc:
                errors.append(str(exc))

        if cached is None and receipt_raw is not None:
            if page_raw is None or tree_raw is None:
                errors.append("receipt has no complete source pair")
            else:
                try:
                    _inspect_receipt(
                        receipt_raw,
                        item=item,
                        page_raw=page_raw,
                        tree_raw=tree_raw,
                        expected_plan_sha256=expected_plan_sha256,
                        now=now,
                    )
                    counters["valid_receipts"] += 1
                except PublicationEditionValidationError as exc:
                    errors.append(str(exc))

        detail = cached or {
            "publication": item["publication"],
            "ready": not errors and article_count is not None and receipt_sha is not None,
            "receipt_file": receipt_file,
            "receipt_sha256": receipt_sha,
            "page_sha256": page_sha,
            "tree_sha256": tree_sha,
            "article_count": article_count,
            "errors": errors,
        }
        details.append(detail)
        if progress is not None:
            progress(completed_items, total_items, dict(detail))

    pending = [detail for detail in details if not detail["ready"]]
    next_action = None
    if pending:
        detail = pending[0]
        item = plan["items"][
            detail["publication"] - plan["range"]["first_publication"]
        ]
        next_action = {
            "publication": item["publication"],
            "page_url": item["page_url"],
            "tree_url": item["tree_url"],
            "receipt_file": detail["receipt_file"],
            "errors": detail["errors"],
        }

    report = {
        "contract": BROWSER_RECEIPT_AUDIT_CONTRACT,
        "auditor_implementation": AUDITOR_IMPLEMENTATION,
        "kind": "read_only_same_origin_browser_capture_audit",
        "plan_sha256": plan["plan_sha256"],
        "plan_file_sha256": plan_file_sha,
        "act": plan["act"],
        "summary": {
            "planned_editions": len(plan["items"]),
            **counters,
            "pending_editions": len(pending),
            "total_evidence_bytes_observed": total_bytes,
        },
        "complete": not pending,
        "next_action": next_action,
        "details": details,
        "database_writes_allowed": False,
        "public_answer_routing_changed": False,
    }
    report["audit_sha256"] = sha256_json(report)
    return report


def compact_browser_receipt_audit(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "contract": report["contract"],
        "auditor_implementation": report["auditor_implementation"],
        "plan_sha256": report["plan_sha256"],
        "audit_sha256": report["audit_sha256"],
        **report["summary"],
        "complete": report["complete"],
        "next_action": report["next_action"],
        "database_writes_allowed": report["database_writes_allowed"],
        "public_answer_routing_changed": report["public_answer_routing_changed"],
    }
