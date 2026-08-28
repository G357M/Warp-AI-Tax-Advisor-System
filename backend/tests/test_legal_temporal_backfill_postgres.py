"""Disposable PostgreSQL integration proof for the controlled backfill."""

from __future__ import annotations

from datetime import date
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from core.database import engine
from legal_temporal.backfill import (
    BACKFILL_CONTRACT,
    LEGACY_NORMALIZER_PLAIN,
    SOURCE_VERIFICATION_EXACT,
    candidate_fingerprint,
    classify_deterministic_operation,
    compact_whitespace,
    manifest_sha256,
    normalized_infohub_text,
    parse_workspace_source_url,
    validate_bundle,
)
from models.document import Document, LawAmendment
from models.legal_temporal import LegalAmendmentOperation
from scripts.audit_legal_temporal_backfill import execute_audit
from scripts.build_legal_temporal_backfill_bundle import collect_inventory
from scripts.import_legal_temporal_backfill import apply_bundle


pytestmark = pytest.mark.skipif(
    os.getenv("LEGAL_TEMPORAL_POSTGRES_TESTS") != "1",
    reason="requires the disposable CI PostgreSQL temporal-schema job",
)


def _source(
    bundle: Path,
    *,
    document_id,
    unique_key: str,
    title: str,
    body: str,
    role: str,
) -> tuple[dict, bytes]:
    payload = {
        "uniqueKey": unique_key,
        "name": title,
        "type": {"name": "კანონი"},
        "baseType": {"name": "ნორმატიული აქტი"},
        "description": f"<p>{body}</p>",
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    workspace_url = f"https://infohub.rs.ge/ka/workspace/document/{unique_key}"
    identity = parse_workspace_source_url(workspace_url)
    digest = hashlib.sha256(raw).hexdigest()
    relative_file = f"sources/{unique_key}-{digest[:16]}.json"
    (bundle / relative_file).write_bytes(raw)
    return (
        {
            "legacy_document_id": str(document_id),
            "roles": [role],
            "workspace_url": workspace_url,
            "api_url": identity.api_url,
            "language": "ka",
            "unique_key": unique_key,
            "legacy_md5": hashlib.md5(
                normalized_infohub_text(payload).encode()
            ).hexdigest(),
            "legacy_full_text_md5": hashlib.md5(
                normalized_infohub_text(payload).encode()
            ).hexdigest(),
            "legacy_compact_md5": hashlib.md5(
                compact_whitespace(normalized_infohub_text(payload)).encode()
            ).hexdigest(),
            "legacy_extraction_method": None,
            "legacy_normalizer": LEGACY_NORMALIZER_PLAIN,
            "verification_mode": SOURCE_VERIFICATION_EXACT,
            "title": title,
            "document_type": "law",
            "document_number": None,
            "authority": None,
            "date_published": "2026-01-01",
            "date_effective": None,
            "file": relative_file,
            "content_sha256": digest,
            "byte_length": len(raw),
            "media_type": "application/json",
            "http_status": 200,
            "etag": None,
            "last_modified": None,
            "captured_at_utc": "2026-08-28T12:00:00Z",
        },
        raw,
    )


def test_backfill_is_atomic_idempotent_and_never_promotes_authoritative_text(
    tmp_path: Path,
):
    assert engine.dialect.name == "postgresql"
    bundle = tmp_path / "bundle"
    (bundle / "sources").mkdir(parents=True)
    amendment_document_id = uuid4()
    target_document_id = uuid4()
    amendment_id = uuid4()
    amendment_key = str(uuid4())
    target_key = str(uuid4())
    amendment_source, amendment_raw = _source(
        bundle,
        document_id=amendment_document_id,
        unique_key=amendment_key,
        title="ცვლილების სატესტო კანონი",
        body="მე-5 მუხლს დაემატოს ახალი ნაწილი.",
        role="amendment",
    )
    target_source, target_raw = _source(
        bundle,
        document_id=target_document_id,
        unique_key=target_key,
        title="სატესტო კანონი",
        body="მუხლი 5. ძირითადი ნორმა.",
        role="target",
    )
    with Session(engine) as db:
        db.add_all(
            [
                Document(
                    id=amendment_document_id,
                    title=amendment_source["title"],
                    document_type="law",
                    language="ka",
                    status="active",
                    source_url=amendment_source["workspace_url"],
                    file_hash=amendment_source["legacy_md5"],
                    full_text=normalized_infohub_text(json.loads(amendment_raw)),
                    metadata_json={},
                ),
                Document(
                    id=target_document_id,
                    title=target_source["title"],
                    document_type="law",
                    language="ka",
                    status="active",
                    source_url=target_source["workspace_url"],
                    file_hash=target_source["legacy_md5"],
                    full_text=normalized_infohub_text(json.loads(target_raw)),
                    metadata_json={},
                ),
            ]
        )
        db.add(
            LawAmendment(
                id=amendment_id,
                amendment_doc_id=amendment_document_id,
                target_law_doc_id=target_document_id,
                target_law_title=target_source["title"],
                adoption_date=date(2026, 1, 1),
                effective_date=date(2026, 2, 1),
                status="in_force",
                affected_articles=[
                    {
                        "article": "5",
                        "action": "added",
                        "summary_ru": "candidate only",
                    }
                ],
                extraction_version=1,
            )
        )
        db.commit()

    inventory_amendments, inventory_sources = collect_inventory(
        target_law_doc_id=target_document_id,
        limit=0,
    )
    assert len(inventory_amendments) == 1
    assert len(inventory_sources) == 2
    assert {
        source["legacy_compact_md5"] for source in inventory_sources.values()
    } == {
        amendment_source["legacy_compact_md5"],
        target_source["legacy_compact_md5"],
    }

    candidate = {
        "legacy_law_amendment_id": str(amendment_id),
        "item_index": 0,
        "target_legacy_document_id": str(target_document_id),
        "article_ref": "5",
        "legacy_action": "added",
        "effective_date": "2026-02-01",
        "legacy_extraction_version": 1,
        "classification": classify_deterministic_operation(
            "მე-5 მუხლს დაემატოს ახალი ნაწილი.",
            article_ref="5",
            legacy_action="added",
        ),
    }
    candidate["candidate_fingerprint"] = candidate_fingerprint(candidate)
    manifest = {
        "schema_version": 1,
        "backfill_contract": BACKFILL_CONTRACT,
        "generated_at_utc": "2026-08-28T12:00:00Z",
        "filters": {"target_law_doc_id": str(target_document_id), "limit": 0},
        "sources": [amendment_source, target_source],
        "amendments": [
            {
                "legacy_law_amendment_id": str(amendment_id),
                "amendment_legacy_document_id": str(amendment_document_id),
                "target_legacy_document_id": str(target_document_id),
                "adoption_date": "2026-01-01",
                "effective_date": "2026-02-01",
                "legacy_status": "in_force",
                "legacy_extraction_version": 1,
                "row_issues": [],
                "candidates": [candidate],
            }
        ],
        "summary": {
            "amendments": 1,
            "sources": 2,
            "candidate_items": 1,
            "operation_candidates": 1,
            "candidate_items_needing_review": 0,
            "amendment_rows_with_issues": 0,
            "expert_review_rows": 1,
            "legacy_normalizers": {LEGACY_NORMALIZER_PLAIN: 2},
            "source_verification_modes": {SOURCE_VERIFICATION_EXACT: 2},
            "postgresql_writes_allowed": False,
            "public_answer_routing_changed": False,
        },
    }
    manifest["manifest_sha256"] = manifest_sha256(manifest)
    (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    loaded = validate_bundle(
        bundle, expected_manifest_sha256=manifest["manifest_sha256"]
    )

    first = apply_bundle(
        bundle_dir=bundle,
        manifest=loaded,
        max_source_snapshots=2,
        max_acts=2,
        max_operations=1,
    )
    assert first["result"] == "pass"
    assert first["counters"]["acts_created"] == 2
    assert first["counters"]["operations_created"] == 1
    assert first["authoritative_provision_versions_created"] == 0
    with Session(engine) as db:
        stored_operation = db.query(LegalAmendmentOperation).one()
        assert (
            stored_operation.structured_payload["source_verification_mode"]
            == SOURCE_VERIFICATION_EXACT
        )

    second = apply_bundle(
        bundle_dir=bundle,
        manifest=loaded,
        max_source_snapshots=2,
        max_acts=2,
        max_operations=1,
    )
    assert second["counters"]["acts_reused"] == 2
    assert second["counters"]["operations_reused"] == 1
    audit = execute_audit(loaded)
    assert audit["result"] == "pass"
    assert audit["found"]["authoritative_provision_versions"] == 0
