"""Contracts for exact-source temporal legal backfill."""

from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest

from legal_temporal.backfill import (
    BACKFILL_CONTRACT,
    LEGACY_NORMALIZER_NATIVE,
    LEGACY_NORMALIZER_PLAIN,
    SOURCE_VERIFICATION_DRIFT,
    SOURCE_VERIFICATION_EXACT,
    SOURCE_VERIFICATION_WHITESPACE,
    BackfillValidationError,
    candidate_fingerprint,
    canonical_article_ref,
    classify_deterministic_operation,
    compact_whitespace,
    manifest_sha256,
    legacy_normalized_text,
    normalized_infohub_text,
    operation_key,
    parse_workspace_source_url,
    validate_bundle,
    validate_official_api_bytes,
)
from scripts.audit_legal_temporal_backfill import audit_plan
from scripts.build_legal_temporal_backfill_bundle import _csv_safe, _inventory_summary
from scripts.import_legal_temporal_backfill import import_plan


def _payload(unique_key: str, body: str) -> dict:
    return {
        "uniqueKey": unique_key,
        "name": "სატესტო კანონი",
        "type": {"name": "კანონი"},
        "baseType": {"name": "ნორმატიული აქტი"},
        "description": f"<p>{body}</p>",
    }


def _bundle(tmp_path: Path) -> tuple[Path, dict]:
    amendment_document_id = str(uuid4())
    target_document_id = str(uuid4())
    amendment_id = str(uuid4())
    unique_key = str(uuid4())
    payload = _payload(
        unique_key,
        "მე-5 მუხლს დაემატოს შემდეგი შინაარსის მე-2 ნაწილი.",
    )
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    legacy_md5 = hashlib.md5(normalized_infohub_text(payload).encode()).hexdigest()
    workspace_url = f"https://infohub.rs.ge/ka/workspace/document/{unique_key}"
    identity = parse_workspace_source_url(workspace_url)
    source = {
        "legacy_document_id": amendment_document_id,
        "roles": ["amendment"],
        "workspace_url": workspace_url,
        "api_url": identity.api_url,
        "language": "ka",
        "unique_key": unique_key,
        "legacy_md5": legacy_md5,
        "legacy_full_text_md5": legacy_md5,
        "legacy_compact_md5": hashlib.md5(
            compact_whitespace(normalized_infohub_text(payload)).encode()
        ).hexdigest(),
        "legacy_extraction_method": None,
        "legacy_normalizer": LEGACY_NORMALIZER_PLAIN,
        "verification_mode": SOURCE_VERIFICATION_EXACT,
        "title": payload["name"],
        "document_type": "law",
        "document_number": "1",
        "authority": None,
        "date_published": "2026-01-01",
        "date_effective": None,
        "file": f"sources/{unique_key}.json",
        "content_sha256": hashlib.sha256(raw).hexdigest(),
        "byte_length": len(raw),
        "media_type": "application/json",
        "http_status": 200,
        "etag": None,
        "last_modified": None,
        "captured_at_utc": "2026-08-28T10:00:00Z",
    }
    target_key = str(uuid4())
    target_payload = _payload(target_key, "მუხლი 5. ძირითადი ნორმა.")
    target_raw = json.dumps(
        target_payload, ensure_ascii=False, separators=(",", ":")
    ).encode()
    target_workspace = f"https://infohub.rs.ge/ka/workspace/document/{target_key}"
    target_identity = parse_workspace_source_url(target_workspace)
    target_source = {
        **source,
        "legacy_document_id": target_document_id,
        "roles": ["target"],
        "workspace_url": target_workspace,
        "api_url": target_identity.api_url,
        "unique_key": target_key,
        "legacy_md5": hashlib.md5(
            normalized_infohub_text(target_payload).encode()
        ).hexdigest(),
        "legacy_full_text_md5": hashlib.md5(
            normalized_infohub_text(target_payload).encode()
        ).hexdigest(),
        "legacy_compact_md5": hashlib.md5(
            compact_whitespace(normalized_infohub_text(target_payload)).encode()
        ).hexdigest(),
        "title": target_payload["name"],
        "file": f"sources/{target_key}.json",
        "content_sha256": hashlib.sha256(target_raw).hexdigest(),
        "byte_length": len(target_raw),
    }
    candidate = {
        "legacy_law_amendment_id": amendment_id,
        "item_index": 0,
        "target_legacy_document_id": target_document_id,
        "article_ref": "5",
        "legacy_action": "added",
        "effective_date": "2026-02-01",
        "legacy_extraction_version": 1,
        "classification": classify_deterministic_operation(
            normalized_infohub_text(payload),
            article_ref="5",
            legacy_action="added",
        ),
    }
    candidate["candidate_fingerprint"] = candidate_fingerprint(candidate)
    amendment = {
        "legacy_law_amendment_id": amendment_id,
        "amendment_legacy_document_id": amendment_document_id,
        "target_legacy_document_id": target_document_id,
        "adoption_date": "2026-01-01",
        "effective_date": "2026-02-01",
        "legacy_status": "in_force",
        "legacy_extraction_version": 1,
        "row_issues": [],
        "candidates": [candidate],
    }
    manifest = {
        "schema_version": 1,
        "backfill_contract": BACKFILL_CONTRACT,
        "generated_at_utc": "2026-08-28T10:00:00Z",
        "filters": {"target_law_doc_id": target_document_id, "limit": 0},
        "sources": [source, target_source],
        "amendments": [amendment],
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
    bundle = tmp_path / "bundle"
    (bundle / "sources").mkdir(parents=True)
    (bundle / source["file"]).write_bytes(raw)
    (bundle / target_source["file"]).write_bytes(target_raw)
    (bundle / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )
    return bundle, manifest


def test_workspace_url_and_official_bytes_are_fail_closed():
    unique_key = str(uuid4())
    workspace = f"https://infohub.rs.ge/ka/workspace/document/{unique_key}"
    source = parse_workspace_source_url(workspace)
    payload = _payload(unique_key, "მუხლი 5. ტექსტი.")
    raw = json.dumps(payload, ensure_ascii=False).encode()
    expected_md5 = hashlib.md5(normalized_infohub_text(payload).encode()).hexdigest()
    loaded, text, verification_mode = validate_official_api_bytes(
        raw, source=source, expected_legacy_md5=expected_md5
    )
    assert loaded["uniqueKey"] == unique_key
    assert "მუხლი 5" in text
    assert verification_mode == SOURCE_VERIFICATION_EXACT
    with pytest.raises(BackfillValidationError, match="drifted"):
        validate_official_api_bytes(
            raw,
            source=source,
            expected_legacy_md5="0" * 32,
            expected_legacy_compact_md5="0" * 32,
        )
    with pytest.raises(BackfillValidationError, match="invalid official"):
        parse_workspace_source_url(workspace + "?redirect=1")


def test_native_v2_legacy_normalizer_is_explicit_and_fail_closed():
    unique_key = str(uuid4())
    workspace = f"https://infohub.rs.ge/ka/workspace/document/{unique_key}"
    source = parse_workspace_source_url(workspace)
    payload = {
        **_payload(unique_key, "მუხლი 5. ტექსტი."),
        "documentNumber": "42",
        "receiptDate": "2026-01-02T00:00:00",
    }
    normalized = legacy_normalized_text(
        payload,
        source=source,
        normalizer=LEGACY_NORMALIZER_NATIVE,
    )
    assert normalized.startswith("დოკუმენტის ნომერი: 42")
    assert "მუხლი 5. ტექსტი." in normalized
    assert normalized.count(workspace) == 1
    digest = hashlib.md5(normalized.encode()).hexdigest()
    loaded, verified, verification_mode = validate_official_api_bytes(
        json.dumps(payload, ensure_ascii=False).encode(),
        source=source,
        expected_legacy_md5=digest,
        legacy_normalizer=LEGACY_NORMALIZER_NATIVE,
    )
    assert loaded == payload
    assert verified == normalized
    assert verification_mode == SOURCE_VERIFICATION_EXACT
    with pytest.raises(BackfillValidationError, match="unsupported"):
        legacy_normalized_text(payload, source=source, normalizer="unknown-v9")


def test_whitespace_equivalence_and_content_drift_are_distinct():
    unique_key = str(uuid4())
    source = parse_workspace_source_url(
        f"https://infohub.rs.ge/ka/workspace/document/{unique_key}"
    )
    payload = _payload(unique_key, "მუხლი 5.  ტექსტი.")
    raw = json.dumps(payload, ensure_ascii=False).encode()
    live = normalized_infohub_text(payload)
    stored_equivalent = live.replace("  ", " ")
    _, _, equivalent_mode = validate_official_api_bytes(
        raw,
        source=source,
        expected_legacy_md5=hashlib.md5(stored_equivalent.encode()).hexdigest(),
        expected_legacy_full_text_md5=hashlib.md5(
            stored_equivalent.encode()
        ).hexdigest(),
        expected_legacy_compact_md5=hashlib.md5(
            compact_whitespace(stored_equivalent).encode()
        ).hexdigest(),
    )
    assert equivalent_mode == SOURCE_VERIFICATION_WHITESPACE
    _, _, drift_mode = validate_official_api_bytes(
        raw,
        source=source,
        expected_legacy_md5="0" * 32,
        expected_legacy_compact_md5="0" * 32,
        allow_content_drift=True,
    )
    assert drift_mode == SOURCE_VERIFICATION_DRIFT


@pytest.mark.parametrize(
    ("text", "action", "expected"),
    [
        ("მე-5 მუხლს დაემატოს ახალი ნაწილი.", "added", "add"),
        ("5-ე მუხლი ჩამოყალიბდეს შემდეგი რედაქციით.", "amended", "replace"),
        ("მე-5 მუხლი ამოღებულ იქნეს.", "repealed", "repeal"),
    ],
)
def test_explicit_georgian_formula_promotes_only_matching_operation(
    text: str, action: str, expected: str
):
    result = classify_deterministic_operation(
        text, article_ref="5", legacy_action=action
    )
    assert result["state"] == "operation_candidate"
    assert result["operation_type"] == expected
    assert result["marker_codes"]


def test_ambiguous_or_unverified_operation_stays_in_review():
    missing = classify_deterministic_operation(
        "მე-5 მუხლი შეიცვალოს.", article_ref="5", legacy_action="amended"
    )
    conflict = classify_deterministic_operation(
        "მე-5 მუხლი ამოღებულ იქნეს და დაემატოს ახალი ნაწილი.",
        article_ref="5",
        legacy_action="added",
    )
    assert missing == {"state": "needs_review", "reason": "operative_formula_not_found"}
    assert conflict["reason"] == "operative_formula_conflict"
    assert canonical_article_ref("13.243") is None
    assert canonical_article_ref("168-1") == "168-1"


def test_bundle_hash_source_bytes_and_candidate_fingerprints(tmp_path: Path):
    bundle, manifest = _bundle(tmp_path)
    loaded = validate_bundle(
        bundle, expected_manifest_sha256=manifest["manifest_sha256"]
    )
    candidate = loaded["amendments"][0]["candidates"][0]
    source = loaded["sources"][0]
    assert operation_key(candidate, source["content_sha256"])

    (bundle / source["file"]).write_bytes(b"tampered")
    with pytest.raises(BackfillValidationError, match="SHA-256"):
        validate_bundle(bundle)


def test_drifted_amendment_source_cannot_promote_operation(tmp_path: Path):
    bundle, manifest = _bundle(tmp_path)
    amendment_source = manifest["sources"][0]
    amendment_source["legacy_md5"] = "0" * 32
    amendment_source["legacy_full_text_md5"] = "0" * 32
    amendment_source["legacy_compact_md5"] = "0" * 32
    amendment_source["verification_mode"] = SOURCE_VERIFICATION_DRIFT
    manifest["summary"]["source_verification_modes"] = {
        SOURCE_VERIFICATION_DRIFT: 1,
        SOURCE_VERIFICATION_EXACT: 1,
    }
    manifest["manifest_sha256"] = manifest_sha256(manifest)
    (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(BackfillValidationError, match="drifted amendment"):
        validate_bundle(
            bundle, expected_manifest_sha256=manifest["manifest_sha256"]
        )


def test_plans_are_no_database_no_network_and_no_public_routing():
    assert import_plan()["database_calls_allowed"] is False
    assert import_plan()["authoritative_provision_versions_allowed"] is False
    assert import_plan()["public_answer_routing_changed"] is False
    assert audit_plan()["database_writes_allowed"] is False
    summary = _inventory_summary([], {})
    assert summary["database_writes_allowed"] is False
    assert summary["network_calls_allowed"] is False
    assert _csv_safe("=HYPERLINK(\"https://example.com\")").startswith("'")


def test_temporal_backfill_is_not_imported_by_public_runtime():
    models_init = (Path(__file__).parents[1] / "models" / "__init__.py").read_text(
        encoding="utf-8"
    )
    public_routes = (Path(__file__).parents[1] / "api" / "routes" / "query.py").read_text(
        encoding="utf-8"
    )
    assert "legal_temporal" not in models_init
    assert "legal_temporal" not in public_routes
