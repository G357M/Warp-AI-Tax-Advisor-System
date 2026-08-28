#!/usr/bin/env python3
"""Read-only aggregate audit for one imported temporal backfill bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any
from uuid import UUID

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import func

from core.database import SessionLocal, engine
from legal_temporal.backfill import (
    BACKFILL_CONTRACT,
    BackfillValidationError,
    operation_key,
    validate_bundle,
)
from models.legal_temporal import (
    LegalAct,
    LegalActPublication,
    LegalAmendmentOperation,
    LegalProvisionVersion,
    LegalReviewEvent,
    LegalSourceSnapshot,
)


def audit_plan() -> dict[str, Any]:
    return {
        "backfill_contract": BACKFILL_CONTRACT,
        "database_calls_allowed": False,
        "database_writes_allowed": False,
        "full_legal_text_output_allowed": False,
        "checks": [
            "source snapshots",
            "legacy act identity",
            "publication lineage",
            "operation keys and pending review events",
            "no authoritative provision-version promotion",
        ],
    }


def _batches(values: list[Any], size: int = 500):
    for offset in range(0, len(values), size):
        yield values[offset : offset + size]


def execute_audit(manifest: dict[str, Any]) -> dict[str, Any]:
    if engine.dialect.name != "postgresql":
        raise BackfillValidationError("temporal backfill audit requires PostgreSQL")
    errors: list[str] = []
    source_by_document = {
        source["legacy_document_id"]: source for source in manifest["sources"]
    }
    expected_operations: list[tuple[str, str]] = []
    for amendment in manifest["amendments"]:
        source = source_by_document[amendment["amendment_legacy_document_id"]]
        for candidate in amendment["candidates"]:
            if candidate["classification"].get("state") == "operation_candidate":
                expected_operations.append(
                    (
                        operation_key(candidate, source["content_sha256"]),
                        candidate["candidate_fingerprint"],
                    )
                )
    expected_by_key = dict(expected_operations)
    expected_key_by_fingerprint = {
        fingerprint: key for key, fingerprint in expected_operations
    }
    if len(expected_key_by_fingerprint) != len(expected_operations):
        raise BackfillValidationError(
            "bundle operation candidate fingerprints are not unique"
        )

    document_ids = list(source_by_document)
    document_uuids = [UUID(value) for value in document_ids]
    content_hashes = [source["content_sha256"] for source in manifest["sources"]]
    expected_snapshot_keys = {
        (source["api_url"], source["content_sha256"])
        for source in manifest["sources"]
    }
    found_acts: set[str] = set()
    found_snapshots: set[tuple[str, str]] = set()
    found_operations: dict[str, object] = {}
    pending_reviews: set[str] = set()
    machine_reviews: set[str] = set()
    source_snapshot_ids: list[object] = []
    db = SessionLocal()
    try:
        for batch in _batches(document_uuids):
            found_acts.update(
                str(value)
                for (value,) in db.query(LegalAct.legacy_document_id)
                .filter(LegalAct.legacy_document_id.in_(batch))
                .all()
            )
        for batch in _batches(content_hashes):
            rows = (
                db.query(
                    LegalSourceSnapshot.id,
                    LegalSourceSnapshot.source_url,
                    LegalSourceSnapshot.blob_sha256,
                )
                .filter(LegalSourceSnapshot.blob_sha256.in_(batch))
                .all()
            )
            found_snapshots.update((row.source_url, row.blob_sha256) for row in rows)
            source_snapshot_ids.extend(row.id for row in rows)
        for batch in _batches(list(expected_by_key)):
            rows = (
                db.query(LegalAmendmentOperation)
                .filter(LegalAmendmentOperation.operation_key.in_(batch))
                .all()
            )
            for row in rows:
                found_operations[row.operation_key] = row.id
                payload = row.structured_payload or {}
                if (
                    payload.get("legacy_candidate_fingerprint")
                    != expected_by_key[row.operation_key]
                    or payload.get("backfill_contract") != BACKFILL_CONTRACT
                    or payload.get("review_state") != "needs_expert_review"
                    or payload.get("authoritative_text_promoted") is not False
                ):
                    errors.append("operation payload escaped pending-review contract")
        missing_fingerprints = [
            fingerprint
            for key, fingerprint in expected_operations
            if key not in found_operations
        ]
        for batch in _batches(missing_fingerprints):
            rows = (
                db.query(LegalAmendmentOperation)
                .filter(
                    LegalAmendmentOperation.structured_payload[
                        "legacy_candidate_fingerprint"
                    ].as_string().in_(batch)
                )
                .all()
            )
            for row in rows:
                payload = row.structured_payload or {}
                fingerprint = payload.get("legacy_candidate_fingerprint")
                expected_key = expected_key_by_fingerprint.get(fingerprint)
                if expected_key is None:
                    continue
                if expected_key in found_operations:
                    errors.append("operation candidate fingerprint is duplicated")
                    continue
                if (
                    payload.get("backfill_contract") != BACKFILL_CONTRACT
                    or payload.get("review_state") != "needs_expert_review"
                    or payload.get("authoritative_text_promoted") is not False
                ):
                    errors.append("operation payload escaped pending-review contract")
                found_operations[expected_key] = row.id
        operation_ids = list(found_operations.values())
        for batch in _batches(operation_ids):
            rows = (
                db.query(LegalReviewEvent.entity_id, LegalReviewEvent.event_type)
                .filter(
                    LegalReviewEvent.entity_type == "amendment_operation",
                    LegalReviewEvent.entity_id.in_(batch),
                )
                .all()
            )
            for entity_id, event_type in rows:
                if event_type == "needs_review":
                    pending_reviews.add(str(entity_id))
                elif event_type == "machine_extracted":
                    machine_reviews.add(str(entity_id))
        promoted_versions = 0
        for batch in _batches(source_snapshot_ids):
            promoted_versions += int(
                db.query(func.count(LegalProvisionVersion.id))
                .filter(LegalProvisionVersion.source_snapshot_id.in_(batch))
                .scalar()
                or 0
            )
        publication_count = 0
        for batch in _batches(document_uuids):
            act_ids = [
                value
                for (value,) in db.query(LegalAct.id)
                .filter(LegalAct.legacy_document_id.in_(batch))
                .all()
            ]
            if act_ids:
                publication_count += int(
                    db.query(func.count(LegalActPublication.id))
                    .filter(LegalActPublication.legal_act_id.in_(act_ids))
                    .scalar()
                    or 0
                )
    finally:
        db.close()

    missing_acts = len(set(document_ids) - found_acts)
    missing_snapshots = len(expected_snapshot_keys - found_snapshots)
    missing_operations = len(set(expected_by_key) - set(found_operations))
    operation_id_strings = {str(value) for value in found_operations.values()}
    missing_pending_reviews = len(operation_id_strings - pending_reviews)
    missing_machine_reviews = len(operation_id_strings - machine_reviews)
    if missing_acts:
        errors.append("bundle legal acts are missing")
    if missing_snapshots:
        errors.append("bundle source snapshots are missing")
    if publication_count < len(found_acts):
        errors.append("bundle act publications are missing")
    if missing_operations:
        errors.append("deterministic operation candidates are missing")
    if missing_pending_reviews or missing_machine_reviews:
        errors.append("operation review-event contract is incomplete")
    if promoted_versions:
        errors.append("bundle source was promoted to authoritative provision versions")

    return {
        "backfill_contract": BACKFILL_CONTRACT,
        "manifest_sha256": manifest["manifest_sha256"],
        "database_writes_allowed": False,
        "full_legal_text_output_allowed": False,
        "expected": {
            "sources": len(document_ids),
            "operations": len(expected_operations),
        },
        "found": {
            "acts": len(found_acts),
            "source_snapshots": len(found_snapshots),
            "act_publications": publication_count,
            "operations": len(found_operations),
            "needs_review_events": len(pending_reviews),
            "machine_extracted_events": len(machine_reviews),
            "authoritative_provision_versions": promoted_versions,
        },
        "error_count": len(errors),
        "errors": errors,
        "result": "pass" if not errors else "fail",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--expected-manifest-sha256")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        print("LEGAL_TEMPORAL_BACKFILL_AUDIT_PLAN=" + json.dumps(audit_plan(), sort_keys=True))
        return 0
    if args.bundle is None or not args.expected_manifest_sha256:
        parser.error("--execute requires --bundle and --expected-manifest-sha256")
    manifest = validate_bundle(
        args.bundle,
        expected_manifest_sha256=args.expected_manifest_sha256,
    )
    report = execute_audit(manifest)
    print("LEGAL_TEMPORAL_BACKFILL_AUDIT=" + json.dumps(report, sort_keys=True))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BackfillValidationError as exc:
        print(f"LEGAL_TEMPORAL_BACKFILL_AUDIT_ERROR={exc}", file=sys.stderr)
        raise SystemExit(1)
