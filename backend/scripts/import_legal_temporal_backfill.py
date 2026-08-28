#!/usr/bin/env python3
"""Validate or atomically import a reviewed temporal legal backfill bundle.

Validation performs no database call. Apply mode requires exact manifest and
write ceilings, PostgreSQL schema contract v1 and one transaction. It imports
immutable source evidence, stable act/publication identity and only fail-closed
operation candidates. It creates no authoritative provision versions and does
not change public answer routing.
"""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.orm import Session

from core.database import SessionLocal, engine
from legal_temporal.backfill import (
    BACKFILL_CONTRACT,
    BackfillValidationError,
    operation_key,
    parse_iso_date,
    parse_iso_datetime,
    safe_bundle_file,
    validate_bundle,
)
from legal_temporal.schema_contract import SCHEMA_CONTRACT_SHA256, SCHEMA_VERSION
from legal_temporal.snapshots import prepare_snapshot, store_prepared_snapshot
from models.legal_temporal import (
    LegalAct,
    LegalActPublication,
    LegalAmendmentOperation,
    LegalProvision,
    LegalReviewEvent,
)


def import_plan() -> dict[str, Any]:
    return {
        "backfill_contract": BACKFILL_CONTRACT,
        "database_calls_allowed": False,
        "database_writes_allowed": False,
        "network_calls_allowed": False,
        "authoritative_provision_versions_allowed": False,
        "public_answer_routing_changed": False,
        "transaction_scope": "single_transaction",
    }


def _assert_equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise BackfillValidationError(f"existing {label} conflicts with the bundle")


def _get_or_create_act(
    db: Session, source: dict[str, Any], counters: dict[str, int]
) -> LegalAct:
    canonical_key = f"ge:infohub:{source['unique_key']}"
    act = (
        db.query(LegalAct).filter(LegalAct.canonical_key == canonical_key).one_or_none()
    )
    legacy_document_id = UUID(source["legacy_document_id"])
    if act is not None:
        _assert_equal(act.legacy_document_id, legacy_document_id, "legal act document")
        _assert_equal(act.canonical_source_url, source["workspace_url"], "legal act URL")
        _assert_equal(act.official_title_ka, source["title"], "legal act title")
        counters["acts_reused"] += 1
        return act
    act = LegalAct(
        canonical_key=canonical_key,
        jurisdiction="GE",
        act_type=source["document_type"],
        official_title_ka=source["title"],
        document_number=source.get("document_number"),
        issuing_authority=source.get("authority"),
        canonical_source_url=source["workspace_url"],
        legacy_document_id=legacy_document_id,
    )
    db.add(act)
    db.flush()
    counters["acts_created"] += 1
    return act


def _get_or_create_publication(
    db: Session,
    *,
    source: dict[str, Any],
    act: LegalAct,
    snapshot_id: object,
    effective_from: date | None,
    counters: dict[str, int],
) -> LegalActPublication:
    publication_key = f"infohub:{source['unique_key']}"
    publication = (
        db.query(LegalActPublication)
        .filter(
            LegalActPublication.legal_act_id == act.id,
            LegalActPublication.publication_key == publication_key,
        )
        .one_or_none()
    )
    published = parse_iso_date(source.get("date_published"))
    if publication is not None:
        _assert_equal(publication.source_snapshot_id, snapshot_id, "publication snapshot")
        _assert_equal(publication.official_url, source["workspace_url"], "publication URL")
        _assert_equal(publication.effective_from, effective_from, "publication effective date")
        counters["publications_reused"] += 1
        return publication
    publication = LegalActPublication(
        legal_act_id=act.id,
        publication_key=publication_key,
        official_url=source["workspace_url"],
        source_snapshot_id=snapshot_id,
        publication_date=published,
        effective_from=effective_from,
        is_consolidated=False,
    )
    db.add(publication)
    db.flush()
    counters["publications_created"] += 1
    return publication


def _get_or_create_provision(
    db: Session,
    *,
    act: LegalAct,
    article_ref: str,
    counters: dict[str, int],
) -> LegalProvision:
    stable_key = f"article:{article_ref}"
    provision = (
        db.query(LegalProvision)
        .filter(
            LegalProvision.legal_act_id == act.id,
            LegalProvision.stable_key == stable_key,
        )
        .one_or_none()
    )
    if provision is not None:
        _assert_equal(provision.ordinal_path, article_ref, "provision ordinal")
        counters["provisions_reused"] += 1
        return provision
    provision = LegalProvision(
        legal_act_id=act.id,
        stable_key=stable_key,
        provision_type="article",
        ordinal_path=article_ref,
        display_label_ka=f"მუხლი {article_ref}",
    )
    db.add(provision)
    db.flush()
    counters["provisions_created"] += 1
    return provision


def _review_event_id(operation_id: object, event_type: str) -> UUID:
    return uuid5(
        NAMESPACE_URL,
        f"{BACKFILL_CONTRACT}:{operation_id}:{event_type}",
    )


def _ensure_review_events(
    db: Session,
    *,
    operation: LegalAmendmentOperation,
    evidence_locator: str,
    counters: dict[str, int],
) -> None:
    rationales = {
        "machine_extracted": (
            "Official source bytes and an explicit Georgian operative formula "
            "were correlated deterministically; no legal conclusion was published."
        ),
        "needs_review": (
            "Article identity began as a legacy extraction hint and requires expert "
            "verification before authoritative temporal promotion."
        ),
    }
    for event_type, rationale in rationales.items():
        event_id = _review_event_id(operation.id, event_type)
        if db.get(LegalReviewEvent, event_id) is not None:
            counters["review_events_reused"] += 1
            continue
        db.add(
            LegalReviewEvent(
                id=event_id,
                entity_type="amendment_operation",
                entity_id=operation.id,
                event_type=event_type,
                rationale=rationale,
                evidence_locator=evidence_locator,
            )
        )
        counters["review_events_created"] += 1


def _effective_dates_by_document(manifest: dict[str, Any]) -> dict[str, date | None]:
    values: dict[str, date | None] = {}
    for amendment in manifest["amendments"]:
        document_id = amendment["amendment_legacy_document_id"]
        effective = parse_iso_date(amendment.get("effective_date"))
        if document_id in values and values[document_id] != effective:
            raise BackfillValidationError("one amendment document has conflicting dates")
        values[document_id] = effective
    return values


def apply_bundle(
    *,
    bundle_dir: Path,
    manifest: dict[str, Any],
    max_source_snapshots: int,
    max_acts: int,
    max_operations: int,
) -> dict[str, Any]:
    if engine.dialect.name != "postgresql":
        raise BackfillValidationError("temporal backfill apply requires PostgreSQL")
    expected_sources = len(manifest["sources"])
    expected_acts = expected_sources
    expected_operations = int(manifest["summary"]["operation_candidates"])
    ceilings = {
        "max_source_snapshots": (max_source_snapshots, expected_sources),
        "max_acts": (max_acts, expected_acts),
        "max_operations": (max_operations, expected_operations),
    }
    for label, (actual, expected) in ceilings.items():
        if actual != expected:
            raise BackfillValidationError(f"--{label.replace('_', '-')} must equal {expected}")

    counters = {
        "source_snapshots_processed": 0,
        "acts_created": 0,
        "acts_reused": 0,
        "publications_created": 0,
        "publications_reused": 0,
        "provisions_created": 0,
        "provisions_reused": 0,
        "operations_created": 0,
        "operations_reused": 0,
        "review_events_created": 0,
        "review_events_reused": 0,
    }
    source_by_document = {
        source["legacy_document_id"]: source for source in manifest["sources"]
    }
    effective_by_document = _effective_dates_by_document(manifest)
    db = SessionLocal()
    try:
        with db.begin():
            db.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": BACKFILL_CONTRACT},
            )
            installed_contract = db.execute(
                text(
                    "SELECT contract_sha256 FROM legal_temporal_schema_migrations "
                    "WHERE schema_version = :version"
                ),
                {"version": SCHEMA_VERSION},
            ).scalar_one_or_none()
            if installed_contract != SCHEMA_CONTRACT_SHA256:
                raise BackfillValidationError("installed temporal schema contract mismatch")

            snapshot_by_document: dict[str, object] = {}
            act_by_document: dict[str, LegalAct] = {}
            publication_by_document: dict[str, LegalActPublication] = {}
            for source in manifest["sources"]:
                raw = safe_bundle_file(bundle_dir, source["file"]).read_bytes()
                prepared = prepare_snapshot(
                    source_url=source["api_url"],
                    content=raw,
                    media_type=source["media_type"],
                    captured_at=parse_iso_datetime(source["captured_at_utc"]),
                    capture_method="legacy_backfill",
                    http_status=int(source["http_status"]),
                    etag=source.get("etag"),
                    last_modified=source.get("last_modified"),
                    metadata={
                        "backfill_contract": BACKFILL_CONTRACT,
                        "legacy_document_id": source["legacy_document_id"],
                        "workspace_url": source["workspace_url"],
                    },
                )
                stored = store_prepared_snapshot(db, prepared)
                counters["source_snapshots_processed"] += 1
                document_id = source["legacy_document_id"]
                snapshot_by_document[document_id] = stored.snapshot_id
                act = _get_or_create_act(db, source, counters)
                act_by_document[document_id] = act
                publication_by_document[document_id] = _get_or_create_publication(
                    db,
                    source=source,
                    act=act,
                    snapshot_id=stored.snapshot_id,
                    effective_from=effective_by_document.get(
                        document_id, parse_iso_date(source.get("date_effective"))
                    ),
                    counters=counters,
                )

            processed_operations = 0
            for amendment in manifest["amendments"]:
                amendment_doc = amendment["amendment_legacy_document_id"]
                target_doc = amendment.get("target_legacy_document_id")
                if not target_doc:
                    continue
                target_act = act_by_document[target_doc]
                amendment_publication = publication_by_document[amendment_doc]
                source = source_by_document[amendment_doc]
                for candidate in amendment["candidates"]:
                    classification = candidate["classification"]
                    if classification.get("state") != "operation_candidate":
                        continue
                    article_ref = classification["article_ref"]
                    provision = _get_or_create_provision(
                        db,
                        act=target_act,
                        article_ref=article_ref,
                        counters=counters,
                    )
                    key = operation_key(candidate, source["content_sha256"])
                    operation = (
                        db.query(LegalAmendmentOperation)
                        .filter(LegalAmendmentOperation.operation_key == key)
                        .one_or_none()
                    )
                    payload = {
                        "backfill_contract": BACKFILL_CONTRACT,
                        "review_state": "needs_expert_review",
                        "authoritative_text_promoted": False,
                        "legacy_law_amendment_id": amendment[
                            "legacy_law_amendment_id"
                        ],
                        "legacy_candidate_fingerprint": candidate[
                            "candidate_fingerprint"
                        ],
                        "legacy_extraction_version": candidate[
                            "legacy_extraction_version"
                        ],
                        "legacy_action": candidate["legacy_action"],
                        "article_mention_count": classification[
                            "article_mention_count"
                        ],
                        "operative_marker_codes": classification["marker_codes"],
                        "source_blob_sha256": source["content_sha256"],
                    }
                    if operation is None:
                        operation = LegalAmendmentOperation(
                            operation_key=key,
                            amendment_publication_id=amendment_publication.id,
                            target_provision_id=provision.id,
                            source_snapshot_id=snapshot_by_document[amendment_doc],
                            operation_type=classification["operation_type"],
                            effective_from=parse_iso_date(amendment["effective_date"]),
                            source_locator=source["workspace_url"],
                            structured_payload=payload,
                            extraction_method="llm_assisted",
                        )
                        db.add(operation)
                        db.flush()
                        counters["operations_created"] += 1
                    else:
                        _assert_equal(
                            operation.structured_payload,
                            payload,
                            "amendment operation payload",
                        )
                        _assert_equal(
                            operation.source_snapshot_id,
                            snapshot_by_document[amendment_doc],
                            "amendment operation snapshot",
                        )
                        counters["operations_reused"] += 1
                    _ensure_review_events(
                        db,
                        operation=operation,
                        evidence_locator=source["workspace_url"],
                        counters=counters,
                    )
                    processed_operations += 1
            if processed_operations != expected_operations:
                raise BackfillValidationError("processed operation count changed in apply")
    finally:
        db.close()

    return {
        "backfill_contract": BACKFILL_CONTRACT,
        "manifest_sha256": manifest["manifest_sha256"],
        "schema_contract_sha256": SCHEMA_CONTRACT_SHA256,
        "database_writes_allowed": True,
        "network_calls_allowed": False,
        "authoritative_provision_versions_created": 0,
        "public_answer_routing_changed": False,
        "transaction_result": "committed",
        "counters": counters,
        "result": "pass",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--expected-manifest-sha256")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--max-source-snapshots", type=int, default=0)
    parser.add_argument("--max-acts", type=int, default=0)
    parser.add_argument("--max-operations", type=int, default=0)
    args = parser.parse_args()

    if args.bundle is None:
        if args.apply:
            parser.error("--apply requires --bundle")
        print("LEGAL_TEMPORAL_BACKFILL_IMPORT_PLAN=" + json.dumps(import_plan(), sort_keys=True))
        return 0
    manifest = validate_bundle(
        args.bundle,
        expected_manifest_sha256=args.expected_manifest_sha256,
    )
    validation = {
        "backfill_contract": BACKFILL_CONTRACT,
        "manifest_sha256": manifest["manifest_sha256"],
        "sources": len(manifest["sources"]),
        "amendments": len(manifest["amendments"]),
        "operation_candidates": manifest["summary"]["operation_candidates"],
        "database_calls_allowed": False,
        "database_writes_allowed": False,
        "network_calls_allowed": False,
        "result": "pass",
    }
    if not args.apply:
        print(
            "LEGAL_TEMPORAL_BACKFILL_BUNDLE_VALIDATION="
            + json.dumps(validation, sort_keys=True)
        )
        return 0
    if not args.expected_manifest_sha256:
        parser.error("--apply requires --expected-manifest-sha256")
    report = apply_bundle(
        bundle_dir=args.bundle.resolve(),
        manifest=manifest,
        max_source_snapshots=args.max_source_snapshots,
        max_acts=args.max_acts,
        max_operations=args.max_operations,
    )
    print("LEGAL_TEMPORAL_BACKFILL_IMPORT=" + json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BackfillValidationError as exc:
        print(f"LEGAL_TEMPORAL_BACKFILL_IMPORT_ERROR={exc}", file=sys.stderr)
        raise SystemExit(1)
