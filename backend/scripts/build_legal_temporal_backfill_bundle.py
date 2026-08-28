#!/usr/bin/env python3
"""Build a protected, exact-source bundle for temporal legal backfill.

Default mode is a no-database/no-network plan. ``--inventory`` reads only
aggregate legacy metadata. ``--execute`` performs a bounded fetch from the
official InfoHub API, verifies every normalized body against the legacy MD5 and
writes a non-overwriting bundle. It never writes PostgreSQL.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib import error, request
from uuid import UUID

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import aliased

from core.database import SessionLocal
from legal_temporal.backfill import (
    BACKFILL_CONTRACT,
    BUNDLE_SCHEMA_VERSION,
    LEGACY_NORMALIZER_NATIVE,
    LEGACY_NORMALIZER_PLAIN,
    LEGACY_NORMALIZER_SCRAPLING,
    MAX_OFFICIAL_RESPONSE_BYTES,
    BackfillValidationError,
    candidate_fingerprint,
    canonical_article_ref,
    classify_deterministic_operation,
    manifest_sha256,
    parse_workspace_source_url,
    validate_official_api_bytes,
)
from models.document import Document, LawAmendment


class RateLimiter:
    def __init__(self, interval_seconds: float):
        self.interval_seconds = interval_seconds
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delay = max(0.0, self._next_allowed - now)
            self._next_allowed = max(now, self._next_allowed) + self.interval_seconds
        if delay:
            time.sleep(delay)


def _iso_date(value) -> str | None:
    return value.isoformat() if value else None


def _source_record_from_row(row, prefix: str, role: str) -> dict[str, Any]:
    def value(field: str):
        return getattr(row, f"{prefix}_{field}")

    identity = parse_workspace_source_url(value("source_url"))
    extraction_method = str(value("extraction_method") or "").strip()
    normalizer_by_method = {
        "": LEGACY_NORMALIZER_PLAIN,
        LEGACY_NORMALIZER_NATIVE: LEGACY_NORMALIZER_NATIVE,
        LEGACY_NORMALIZER_SCRAPLING: LEGACY_NORMALIZER_SCRAPLING,
    }
    if extraction_method not in normalizer_by_method:
        raise BackfillValidationError(
            f"unsupported legacy extraction method: {extraction_method}"
        )
    return {
        "legacy_document_id": str(value("id")),
        "roles": [role],
        "workspace_url": identity.workspace_url,
        "api_url": identity.api_url,
        "language": identity.language,
        "unique_key": identity.unique_key,
        "legacy_md5": str(value("file_hash") or "").lower(),
        "legacy_extraction_method": extraction_method or None,
        "legacy_normalizer": normalizer_by_method[extraction_method],
        "title": str(value("title") or "").strip(),
        "document_type": str(value("document_type") or "").strip(),
        "document_number": (
            str(value("document_number")).strip()
            if value("document_number")
            else None
        ),
        "authority": str(value("authority") or "").strip() or None,
        "date_published": _iso_date(value("date_published")),
        "date_effective": _iso_date(value("date_effective")),
    }


def _add_source(
    sources: dict[str, dict[str, Any]], source: dict[str, Any]
) -> None:
    key = source["legacy_document_id"]
    candidate = source
    existing = sources.get(key)
    if existing is None:
        sources[key] = candidate
        return
    stable_fields = set(candidate) - {"roles"}
    if any(existing[field] != candidate[field] for field in stable_fields):
        raise BackfillValidationError("one legacy document has conflicting source data")
    existing["roles"] = sorted(set(existing["roles"]) | set(candidate["roles"]))


def _candidate(
    *,
    legacy_law_amendment_id: str,
    extraction_version: int,
    effective_date,
    item: Any,
    item_index: int,
    target_document_id: str | None,
) -> dict[str, Any]:
    value = item if isinstance(item, dict) else {}
    raw_ref = str(value.get("article") or "").strip()
    canonical_ref = canonical_article_ref(raw_ref)
    action = str(value.get("action") or "").strip().lower()
    candidate = {
        "legacy_law_amendment_id": legacy_law_amendment_id,
        "item_index": item_index,
        "target_legacy_document_id": target_document_id,
        "article_ref": canonical_ref or raw_ref,
        "legacy_action": action,
        "effective_date": _iso_date(effective_date),
        "legacy_extraction_version": extraction_version,
        "classification": {
            "state": "needs_review",
            "reason": "official_source_not_fetched",
        },
    }
    candidate["candidate_fingerprint"] = candidate_fingerprint(candidate)
    return candidate


def collect_inventory(
    *, target_law_doc_id: UUID | None, limit: int
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    amendment_doc = aliased(Document)
    target_doc = aliased(Document)
    db = SessionLocal()
    try:
        query = (
            db.query(
                LawAmendment.id.label("law_amendment_id"),
                LawAmendment.target_law_doc_id.label("target_law_doc_id"),
                LawAmendment.adoption_date.label("adoption_date"),
                LawAmendment.effective_date.label("effective_date"),
                LawAmendment.status.label("legacy_status"),
                LawAmendment.extraction_version.label("extraction_version"),
                LawAmendment.affected_articles.label("affected_articles"),
                amendment_doc.id.label("amendment_id"),
                amendment_doc.source_url.label("amendment_source_url"),
                amendment_doc.file_hash.label("amendment_file_hash"),
                amendment_doc.title.label("amendment_title"),
                amendment_doc.document_type.label("amendment_document_type"),
                amendment_doc.document_number.label("amendment_document_number"),
                amendment_doc.authority.label("amendment_authority"),
                amendment_doc.date_published.label("amendment_date_published"),
                amendment_doc.date_effective.label("amendment_date_effective"),
                amendment_doc.metadata_json["extraction"]["method"]
                .as_string()
                .label("amendment_extraction_method"),
                target_doc.id.label("target_id"),
                target_doc.source_url.label("target_source_url"),
                target_doc.file_hash.label("target_file_hash"),
                target_doc.title.label("target_title"),
                target_doc.document_type.label("target_document_type"),
                target_doc.document_number.label("target_document_number"),
                target_doc.authority.label("target_authority"),
                target_doc.date_published.label("target_date_published"),
                target_doc.date_effective.label("target_date_effective"),
                target_doc.metadata_json["extraction"]["method"]
                .as_string()
                .label("target_extraction_method"),
            )
            .join(amendment_doc, amendment_doc.id == LawAmendment.amendment_doc_id)
            .outerjoin(target_doc, target_doc.id == LawAmendment.target_law_doc_id)
        )
        if target_law_doc_id is not None:
            query = query.filter(LawAmendment.target_law_doc_id == target_law_doc_id)
        query = query.order_by(LawAmendment.id.asc())
        if limit:
            query = query.limit(limit)
        rows = query.all()

        sources: dict[str, dict[str, Any]] = {}
        amendments: list[dict[str, Any]] = []
        for row in rows:
            amendment_source = _source_record_from_row(row, "amendment", "amendment")
            _add_source(sources, amendment_source)
            target_id = str(row.target_id) if row.target_id is not None else None
            if row.target_id is not None:
                _add_source(sources, _source_record_from_row(row, "target", "target"))
            items = row.affected_articles
            items = items if isinstance(items, list) else []
            issues: list[str] = []
            if row.target_id is None:
                issues.append("unresolved_target")
            if row.effective_date is None:
                issues.append("missing_effective_date")
            if not items:
                issues.append("missing_affected_articles")
            candidates = [
                _candidate(
                    legacy_law_amendment_id=str(row.law_amendment_id),
                    extraction_version=int(row.extraction_version or 0),
                    effective_date=row.effective_date,
                    item=item,
                    item_index=index,
                    target_document_id=target_id,
                )
                for index, item in enumerate(items)
            ]
            amendments.append(
                {
                    "legacy_law_amendment_id": str(row.law_amendment_id),
                    "amendment_legacy_document_id": str(row.amendment_id),
                    "target_legacy_document_id": target_id,
                    "adoption_date": _iso_date(row.adoption_date),
                    "effective_date": _iso_date(row.effective_date),
                    "legacy_status": row.legacy_status,
                    "legacy_extraction_version": int(row.extraction_version or 0),
                    "row_issues": issues,
                    "candidates": candidates,
                }
            )
        return amendments, sources
    finally:
        db.close()


def _inventory_summary(
    amendments: list[dict[str, Any]], sources: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    candidates = [
        candidate
        for amendment in amendments
        for candidate in amendment["candidates"]
    ]
    return {
        "amendments": len(amendments),
        "sources": len(sources),
        "amendments_with_resolved_target": sum(
            bool(item["target_legacy_document_id"]) for item in amendments
        ),
        "candidate_items": len(candidates),
        "canonical_candidate_refs": sum(
            canonical_article_ref(item["article_ref"]) is not None for item in candidates
        ),
        "legacy_normalizers": dict(
            sorted(
                Counter(
                    source["legacy_normalizer"] for source in sources.values()
                ).items()
            )
        ),
        "database_writes_allowed": False,
        "network_calls_allowed": False,
    }


def _fetch_source(
    source: dict[str, Any],
    *,
    limiter: RateLimiter,
    timeout_seconds: float,
    retries: int,
) -> dict[str, Any]:
    headers = {
        "User-Agent": "InfoHubAI-TemporalBackfill/1.0",
        "Accept": "application/json, text/plain, */*",
        "languagecode": source["language"],
        "Referer": "https://infohub.rs.ge/",
        "Origin": "https://infohub.rs.ge",
    }
    last_error = "unknown fetch error"
    for attempt in range(retries + 1):
        limiter.wait()
        req = request.Request(source["api_url"], headers=headers)
        try:
            with request.urlopen(req, timeout=timeout_seconds) as response:
                raw = response.read(MAX_OFFICIAL_RESPONSE_BYTES + 1)
                status = int(getattr(response, "status", 200))
                etag = response.headers.get("ETag")
                last_modified = response.headers.get("Last-Modified")
            identity = parse_workspace_source_url(source["workspace_url"])
            _, normalized_text = validate_official_api_bytes(
                raw,
                source=identity,
                expected_legacy_md5=source["legacy_md5"],
                legacy_normalizer=source["legacy_normalizer"],
            )
            return {
                "ok": True,
                "raw": raw,
                "normalized_text": normalized_text,
                "http_status": status,
                "etag": etag,
                "last_modified": last_modified,
                "captured_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            }
        except error.HTTPError as exc:
            last_error = f"HTTP {exc.code}"
            if exc.code not in {429, 500, 502, 503, 504}:
                break
        except (error.URLError, TimeoutError, OSError, BackfillValidationError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if isinstance(exc, BackfillValidationError):
                break
        if attempt < retries:
            time.sleep(min(2**attempt, 4))
    return {"ok": False, "error": last_error}


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.chmod(path, 0o600)


def _csv_safe(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    if value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


def _write_review_queue(path: Path, amendments: list[dict[str, Any]]) -> int:
    fields = (
        "legacy_law_amendment_id",
        "amendment_legacy_document_id",
        "target_legacy_document_id",
        "effective_date",
        "item_index",
        "article_ref",
        "legacy_action",
        "classification_state",
        "classification_reason",
        "review_state",
        "expert_verdict",
        "corrected_article_ref",
        "corrected_operation_type",
        "reviewer",
        "reviewed_at_utc",
        "legal_rationale",
    )
    count = 0
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for amendment in amendments:
            candidates = amendment["candidates"] or [None]
            for candidate in candidates:
                classification = (candidate or {}).get("classification") or {}
                writer.writerow(
                    {
                        key: _csv_safe(value)
                        for key, value in {
                            "legacy_law_amendment_id": amendment[
                                "legacy_law_amendment_id"
                            ],
                            "amendment_legacy_document_id": amendment[
                                "amendment_legacy_document_id"
                            ],
                            "target_legacy_document_id": amendment.get(
                                "target_legacy_document_id"
                            )
                            or "",
                            "effective_date": amendment.get("effective_date") or "",
                            "item_index": (candidate or {}).get("item_index", ""),
                            "article_ref": (candidate or {}).get("article_ref", ""),
                            "legacy_action": (candidate or {}).get(
                                "legacy_action", ""
                            ),
                            "classification_state": classification.get(
                                "state", "row_issue"
                            ),
                            "classification_reason": classification.get(
                                "reason", ";".join(amendment["row_issues"])
                            ),
                            "review_state": "pending",
                        }.items()
                    }
                )
                count += 1
    os.chmod(path, 0o600)
    return count


def build_bundle(args: argparse.Namespace) -> dict[str, Any]:
    amendments, source_map = collect_inventory(
        target_law_doc_id=args.target_law_doc_id,
        limit=args.limit,
    )
    required_fetches = len(source_map)
    if args.max_source_fetches != required_fetches:
        raise BackfillValidationError(
            f"--max-source-fetches must equal the exact inventory count {required_fetches}"
        )
    output = args.output.resolve()
    if output.exists():
        raise BackfillValidationError("output bundle directory already exists")
    output.mkdir(parents=True, mode=0o700)
    os.chmod(output, 0o700)
    source_dir = output / "sources"
    source_dir.mkdir(mode=0o700)
    os.chmod(source_dir, 0o700)

    limiter = RateLimiter(args.request_interval_seconds)
    failures: list[dict[str, str]] = []
    fetched: dict[str, dict[str, Any]] = {}
    amendments_by_document: dict[str, list[dict[str, Any]]] = {}
    for amendment in amendments:
        amendments_by_document.setdefault(
            amendment["amendment_legacy_document_id"], []
        ).append(amendment)
    ordered_sources = sorted(source_map.values(), key=lambda item: item["legacy_document_id"])
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(
                _fetch_source,
                source,
                limiter=limiter,
                timeout_seconds=args.timeout,
                retries=args.retries,
            ): source
            for source in ordered_sources
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            source = futures[future]
            result = future.result()
            if not result.get("ok"):
                failures.append(
                    {
                        "legacy_document_id": source["legacy_document_id"],
                        "error": str(result.get("error") or "unknown"),
                    }
                )
            else:
                raw = result.pop("raw")
                normalized_text = result.pop("normalized_text")
                content_sha = hashlib.sha256(raw).hexdigest()
                file_name = f"sources/{source['unique_key']}-{content_sha[:16]}.json"
                file_path = output / file_name
                file_path.write_bytes(raw)
                os.chmod(file_path, 0o600)
                fetched[source["legacy_document_id"]] = {
                    **source,
                    "file": file_name,
                    "content_sha256": content_sha,
                    "byte_length": len(raw),
                    "media_type": "application/json",
                    **result,
                }
                for amendment in amendments_by_document.get(
                    source["legacy_document_id"], []
                ):
                    row_blocked = bool(amendment["row_issues"])
                    for candidate in amendment["candidates"]:
                        if row_blocked:
                            classification = {
                                "state": "needs_review",
                                "reason": amendment["row_issues"][0],
                            }
                        else:
                            classification = classify_deterministic_operation(
                                normalized_text,
                                article_ref=candidate["article_ref"],
                                legacy_action=candidate["legacy_action"],
                            )
                        candidate["classification"] = classification
                        candidate["candidate_fingerprint"] = candidate_fingerprint(
                            candidate
                        )
            if completed % 100 == 0 or completed == required_fetches:
                print(
                    "LEGAL_TEMPORAL_BACKFILL_FETCH_PROGRESS="
                    + json.dumps(
                        {
                            "completed": completed,
                            "required": required_fetches,
                            "failures": len(failures),
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )

    if failures:
        failure_report = {
            "schema_version": BUNDLE_SCHEMA_VERSION,
            "backfill_contract": BACKFILL_CONTRACT,
            "required_fetches": required_fetches,
            "failure_count": len(failures),
            "failures": failures,
            "postgresql_writes_allowed": False,
        }
        _write_json(output / "failure_report.json", failure_report)
        raise BackfillValidationError(
            f"official source verification failed for {len(failures)} documents"
        )

    manifest_sources = [
        fetched[source["legacy_document_id"]] for source in ordered_sources
    ]

    promoted = 0
    review_candidates = 0
    for amendment in amendments:
        for candidate in amendment["candidates"]:
            classification = candidate["classification"]
            if classification["state"] == "operation_candidate":
                promoted += 1
            else:
                review_candidates += 1

    generated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    summary = {
        "amendments": len(amendments),
        "sources": len(manifest_sources),
        "candidate_items": promoted + review_candidates,
        "operation_candidates": promoted,
        "candidate_items_needing_review": review_candidates,
        "amendment_rows_with_issues": sum(bool(row["row_issues"]) for row in amendments),
        "legacy_normalizers": dict(
            sorted(
                Counter(
                    source["legacy_normalizer"] for source in manifest_sources
                ).items()
            )
        ),
        "postgresql_writes_allowed": False,
        "public_answer_routing_changed": False,
    }
    summary["expert_review_rows"] = _write_review_queue(
        output / "expert_review_queue.csv", amendments
    )
    manifest: dict[str, Any] = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "backfill_contract": BACKFILL_CONTRACT,
        "generated_at_utc": generated_at,
        "filters": {
            "target_law_doc_id": str(args.target_law_doc_id) if args.target_law_doc_id else None,
            "limit": args.limit,
        },
        "sources": manifest_sources,
        "amendments": amendments,
        "summary": summary,
    }
    manifest["manifest_sha256"] = manifest_sha256(manifest)
    _write_json(output / "manifest.json", manifest)
    _write_json(
        output / "summary.json",
        {
            **summary,
            "manifest_sha256": manifest["manifest_sha256"],
            "database_writes_allowed": False,
        },
    )
    return {
        **summary,
        "manifest_sha256": manifest["manifest_sha256"],
        "output": str(output),
        "result": "pass",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--inventory", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--target-law-doc-id", type=UUID)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-source-fetches", type=int, default=0)
    parser.add_argument("--request-interval-seconds", type=float, default=0.2)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--retries", type=int, default=2)
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("--limit must be non-negative")
    if not 0.15 <= args.request_interval_seconds <= 10:
        parser.error("--request-interval-seconds must be between 0.15 and 10")
    if not 1 <= args.workers <= 8:
        parser.error("--workers must be between 1 and 8")
    if not 1 <= args.timeout <= 120:
        parser.error("--timeout must be between 1 and 120")
    if not 0 <= args.retries <= 5:
        parser.error("--retries must be between 0 and 5")

    if not args.inventory and not args.execute:
        print(
            "LEGAL_TEMPORAL_BACKFILL_PLAN="
            + json.dumps(
                {
                    "backfill_contract": BACKFILL_CONTRACT,
                    "database_calls_allowed": False,
                    "database_writes_allowed": False,
                    "network_calls_allowed": False,
                    "public_answer_routing_changed": False,
                    "stages": ["inventory", "bounded_official_fetch", "separate_import"],
                },
                sort_keys=True,
            )
        )
        return 0

    if args.inventory:
        amendments, sources = collect_inventory(
            target_law_doc_id=args.target_law_doc_id,
            limit=args.limit,
        )
        report = _inventory_summary(amendments, sources)
        print("LEGAL_TEMPORAL_BACKFILL_INVENTORY=" + json.dumps(report, sort_keys=True))
        return 0
    if args.output is None:
        parser.error("--execute requires --output")

    # Re-read inside build_bundle so inventory and fetch never share a stale ORM session.
    report = build_bundle(args)
    print("LEGAL_TEMPORAL_BACKFILL_BUNDLE=" + json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BackfillValidationError as exc:
        print(f"LEGAL_TEMPORAL_BACKFILL_ERROR={exc}", file=sys.stderr)
        raise SystemExit(1)
