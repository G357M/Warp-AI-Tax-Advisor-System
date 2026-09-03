"""Offline expert review: coverage, immutable lineage and fail-closed proposals."""

from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from legal_temporal.backfill import (
    BackfillValidationError, SOURCE_VERIFICATION_DRIFT,
    compact_whitespace, manifest_sha256, normalized_infohub_text,
)
from legal_temporal.expert_review import (
    REVIEW_CONTRACT, ReviewValidationError, build_rows, load_evidence,
    pending_decision, read_review, review_document, validate_reviews,
)
from scripts.review_legal_temporal import _md, _write_new, build_packet, main
from test_legal_temporal_backfill import _bundle

NOW = datetime(2026, 9, 3, 12, tzinfo=UTC)
OPERATIVE = "მე-5 მუხლს დაემატოს შემდეგი შინაარსის მე-2 ნაწილი."
COMMENCEMENT = "ეს კანონი ამოქმედდეს 2026 წლის 1 თებერვლიდან."


def _save_manifest(bundle, manifest):
    manifest["manifest_sha256"] = manifest_sha256(manifest)
    (bundle / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def evidence(tmp_path):
    bundle, manifest = _bundle(tmp_path)
    source = manifest["sources"][0]
    path = bundle / source["file"]
    payload = json.loads(path.read_bytes())
    payload["description"] += f"<p>{COMMENCEMENT}</p>"
    raw = json.dumps(payload, ensure_ascii=False).encode()
    path.write_bytes(raw)
    normalized = normalized_infohub_text(payload)
    source.update({
        "content_sha256": hashlib.sha256(raw).hexdigest(), "byte_length": len(raw),
        "legacy_md5": hashlib.md5(normalized.encode()).hexdigest(),
        "legacy_full_text_md5": hashlib.md5(normalized.encode()).hexdigest(),
        "legacy_compact_md5": hashlib.md5(compact_whitespace(normalized).encode()).hexdigest(),
    })
    _save_manifest(bundle, manifest)
    loaded, texts = load_evidence(bundle, manifest["manifest_sha256"])
    return bundle, loaded, texts


def _decision(state="confirm"):
    return pending_decision() | {
        "state": state, "reviewer": "Test Expert (fixture)",
        "reviewed_at_utc": "2026-09-03T11:00:00Z",
        "rationale": "Test fixture only; not a real expert legal approval.",
        "evidence_locator": "Amending act article 1; commencement article 2",
        "operative_quote": OPERATIVE, "effective_date_quote": COMMENCEMENT,
    }


def _document(manifest, texts, state="confirm"):
    rows = deepcopy(build_rows(manifest, texts))
    if state != "pending":
        rows[0]["decision"] = _decision(state)
    return review_document(manifest, rows)


def _validate(manifest, texts, document):
    return validate_reviews(manifest, texts, [(document, "a" * 64)], now=NOW)


def test_offline_import_has_no_database_settings_or_network_dependencies(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    code = (
        "import sys; from scripts.review_legal_temporal import safety_plan; "
        "assert not any(n == 'sqlalchemy' or n.startswith('core.') for n in sys.modules); "
        "assert safety_plan()['database_calls_allowed'] is False"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(backend)}, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


def test_schema_package_exports_still_work():
    import legal_temporal
    from legal_temporal.schema_contract import SCHEMA_CONTRACT_SHA256
    assert legal_temporal.SCHEMA_VERSION == 1
    assert legal_temporal.SCHEMA_CONTRACT_SHA256 == SCHEMA_CONTRACT_SHA256
    with pytest.raises(AttributeError):
        getattr(legal_temporal, "not_a_schema_export")


def test_full_packet_is_deterministic_protected_and_all_pending(evidence, tmp_path):
    bundle, manifest, texts = evidence
    outputs = [tmp_path / "review-a", tmp_path / "review-b"]
    for output in outputs:
        report = build_packet(bundle, manifest["manifest_sha256"], output, 1)
        assert report["review_rows"] == 1
        assert report["lanes"] == {"expert_confirmation": 1}
        index = json.loads((output / "index.json").read_text(encoding="utf-8"))
        batch = index["batches"][0]
        path = output / batch["review_file"]
        document, actual = read_review(path)
        assert actual == batch["review_sha256"]
        assert document["rows"][0]["decision"] == pending_decision()
        validated = _validate(manifest, texts, document)
        assert validated["states"] == {"pending": 1}
        assert validated["proposals"] == []
        assert validated["not_submitted_rows"] == 0
        for source in manifest["sources"]:
            doc_id = source["legacy_document_id"]
            assert (output / f"sources/{doc_id}.txt").read_text(encoding="utf-8") == texts[doc_id]
        if os.name != "nt":
            assert output.stat().st_mode & 0o077 == 0
            assert path.stat().st_mode & 0o077 == 0
    assert (outputs[0] / "index.json").read_bytes() == (outputs[1] / "index.json").read_bytes()
    with pytest.raises(ReviewValidationError, match="already exists"):
        build_packet(bundle, manifest["manifest_sha256"], outputs[0])
    with pytest.raises(ReviewValidationError, match="outside"):
        build_packet(bundle, manifest["manifest_sha256"], bundle / "reviews")


def test_valid_confirmation_remains_non_executable(evidence):
    _, manifest, texts = evidence
    report = _validate(manifest, texts, _document(manifest, texts))
    assert report["error_count"] == 0
    assert report["states"] == {"confirm": 1}
    assert len(report["proposals"]) == 1
    assert report["kind"] == "non_executable_expert_proposals"
    assert not report["database_writes_allowed"]
    assert not report["public_answer_routing_changed"]
    assert report["authoritative_versions_created"] == 0
    assert report["requires_independent_review_and_reconstruction"]


@pytest.mark.parametrize("state", ["reject", "defer"])
def test_non_confirming_decisions_are_proposals_not_approvals(evidence, state):
    _, manifest, texts = evidence
    document = _document(manifest, texts, state)
    document["rows"][0]["decision"]["operative_quote"] = ""
    document["rows"][0]["decision"]["effective_date_quote"] = ""
    result = _validate(manifest, texts, document)
    assert result["error_count"] == 0
    assert result["states"] == {state: 1}
    assert result["authoritative_versions_created"] == 0


@pytest.mark.parametrize("field,value", [
    ("state", "approved"), ("state", []), ("reviewer", ""),
    ("rationale", "short"), ("evidence_locator", ""),
    ("operative_quote", "Invented legal text not in the source"),
    ("effective_date_quote", "Invented commencement clause in the source"),
    ("operative_quote", ""), ("effective_date_quote", ""),
    ("reviewed_at_utc", "19:42"), ("reviewed_at_utc", "2026-09-03T11:00:00"),
    ("reviewed_at_utc", "2026-09-03T11:00:00+04:00"),
    ("reviewed_at_utc", "2027-01-01T00:00:00Z"),
    ("reviewed_at_utc", "2026-02-30T11:00:00Z"),
    ("reviewed_at_utc", "2025-01-01T00:00:00Z"),
    ("proposed_correction", {}), ("reviewer", None),
])
def test_invalid_decisions_fail_entire_proposal_export(evidence, field, value):
    _, manifest, texts = evidence
    document = _document(manifest, texts)
    document["rows"][0]["decision"][field] = value
    report = _validate(manifest, texts, document)
    assert report["error_count"] == 1
    assert report["proposals"] == []


def test_pending_filled_review_is_not_silently_ignored(evidence):
    _, manifest, texts = evidence
    document = _document(manifest, texts)
    document["rows"][0]["decision"]["state"] = "pending"
    report = _validate(manifest, texts, document)
    assert "explicitly set" in report["errors"][0]["error"]


@pytest.mark.parametrize("change", ["evidence", "pin", "contract", "unknown", "extra", "boolean_index"])
def test_immutable_columns_and_contract_pins_cannot_be_replaced(evidence, change):
    _, manifest, texts = evidence
    document = _document(manifest, texts)
    if change == "evidence":
        document["rows"][0]["evidence"]["effective_date"] = "2000-01-01"
    elif change == "pin":
        document["manifest_sha256"] = "0" * 64
    elif change == "contract":
        document["contract"] = "other"
    elif change == "unknown":
        document["rows"][0]["row_id"] = "unknown"
    elif change == "boolean_index":
        document["rows"][0]["evidence"]["item_index"] = False
    else:
        document["rows"][0]["approval"] = True
    with pytest.raises(ReviewValidationError):
        _validate(manifest, texts, document)


@pytest.mark.parametrize("role", ["amendment", "target"])
def test_source_drift_never_becomes_confirmed_by_reviewer(evidence, role):
    _, manifest, texts = evidence
    manifest["sources"][0 if role == "amendment" else 1]["verification_mode"] = SOURCE_VERIFICATION_DRIFT
    document = _document(manifest, texts)
    assert document["rows"][0]["evidence"]["lane"] == "source_reconciliation"
    result = _validate(manifest, texts, document)
    assert "blocked candidate" in result["errors"][0]["error"]
    assert result["proposals"] == []


@pytest.mark.parametrize("issue", ["missing_target", "missing_date", "ambiguous", "row_issue"])
def test_unresolved_candidates_cannot_be_confirmed(evidence, issue):
    _, manifest, texts = evidence
    amendment = manifest["amendments"][0]
    if issue == "missing_target":
        amendment["target_legacy_document_id"] = None
    elif issue == "missing_date":
        amendment["effective_date"] = None
    elif issue == "ambiguous":
        amendment["candidates"][0]["classification"] = {"state": "needs_review", "reason": "conflict"}
    else:
        amendment["row_issues"] = ["unresolved_link"]
    result = _validate(manifest, texts, _document(manifest, texts))
    assert result["error_count"] == 1


def test_partial_disjoint_batches_preserve_missing_and_reject_overlap(evidence):
    _, manifest, texts = evidence
    second = deepcopy(manifest["amendments"][0])
    second["legacy_law_amendment_id"] = "00000000-0000-4000-8000-000000000001"
    manifest["amendments"].append(second)
    manifest["summary"]["expert_review_rows"] = 2
    all_rows = build_rows(manifest, texts)
    first = review_document(manifest, [all_rows[0]])
    result = _validate(manifest, texts, first)
    assert result["submitted_rows"] == 1
    assert result["not_submitted_rows"] == 1
    assert result["states"] == {"pending": 1}
    second_doc = review_document(manifest, [all_rows[1]])
    result = validate_reviews(manifest, texts, [(first, "a" * 64), (second_doc, "b" * 64)], now=NOW)
    assert result["not_submitted_rows"] == 0
    with pytest.raises(ReviewValidationError, match="overlapping"):
        validate_reviews(manifest, texts, [(first, "a" * 64), (first, "b" * 64)], now=NOW)
    first["rows"][0]["decision"] = _decision()
    second_doc["rows"][0]["decision"] = _decision() | {"reviewer": ""}
    result = validate_reviews(manifest, texts, [(first, "a" * 64), (second_doc, "b" * 64)], now=NOW)
    assert result["error_count"] == 1
    assert result["proposals"] == []


def test_no_candidate_amendment_is_not_lost(evidence):
    _, manifest, texts = evidence
    manifest["amendments"][0]["candidates"] = []
    row = build_rows(manifest, texts)[0]
    assert row["evidence"]["classification"]["reason"] == "no_candidate_items"
    assert row["evidence"]["item_index"] is None
    row["decision"] = _decision("defer")
    result = _validate(manifest, texts, review_document(manifest, [row]))
    assert result["error_count"] == 0


def test_correction_is_explicit_and_never_modifies_original(evidence):
    _, manifest, texts = evidence
    document = _document(manifest, texts, "correct")
    before = deepcopy(document["rows"][0]["evidence"])
    correction = {
        "target_legacy_document_id": manifest["sources"][1]["legacy_document_id"],
        "article_ref": "5-1", "operation_type": "replace", "effective_date": "2026-02-01",
    }
    document["rows"][0]["decision"]["proposed_correction"] = correction
    result = _validate(manifest, texts, document)
    assert result["error_count"] == 0
    assert result["proposals"][0]["evidence"] == before
    for key, value in (
        ("target_legacy_document_id", "unknown"), ("article_ref", "05"),
        ("operation_type", "delete"), ("effective_date", "01.02.2026"),
        ("effective_date", "2026-02-30"),
    ):
        broken = deepcopy(document)
        broken["rows"][0]["decision"]["proposed_correction"][key] = value
        assert _validate(manifest, texts, broken)["error_count"] == 1


@pytest.mark.parametrize("raw", [b'{"rows":[],"rows":[]}', b'{"rows":NaN}', b'[]', b'broken', b'\xff'])
def test_strict_json_rejects_ambiguous_or_invalid_inputs(tmp_path, raw):
    path = tmp_path / "review.json"
    path.write_bytes(raw)
    with pytest.raises(ReviewValidationError):
        read_review(path)


def test_read_limits_utf8_bom_and_non_overwrite(tmp_path, monkeypatch):
    path = tmp_path / "review.json"
    path.write_bytes(b'\xef\xbb\xbf{"rows":[]}')
    assert read_review(path)[0] == {"rows": []}
    with pytest.raises(FileExistsError):
        _write_new(path, "overwrite")
    assert path.read_bytes().startswith(b'\xef\xbb\xbf')
    monkeypatch.setattr("legal_temporal.expert_review.MAX_REVIEW_BYTES", 4)
    with pytest.raises(ReviewValidationError, match="byte limit"):
        read_review(path)


@pytest.mark.skipif(os.name == "nt", reason="Windows symlinks require OS privileges")
def test_symlink_review_is_rejected(tmp_path):
    source = tmp_path / "original.json"
    source.write_text("{}")
    alias = tmp_path / "link.json"
    alias.symlink_to(source)
    with pytest.raises(ReviewValidationError, match="regular file"):
        read_review(alias)


def test_source_bytes_and_wrong_bundle_pin_fail_before_writing(evidence, tmp_path):
    bundle, manifest, _ = evidence
    output = tmp_path / "review"
    with pytest.raises(BackfillValidationError, match="reviewed manifest"):
        build_packet(bundle, "0" * 64, output)
    assert not output.exists()
    source = bundle / manifest["sources"][0]["file"]
    source.write_bytes(source.read_bytes() + b" ")
    with pytest.raises(BackfillValidationError, match="SHA-256 mismatch"):
        build_packet(bundle, manifest["manifest_sha256"], output)
    assert not output.exists()


def test_markdown_escapes_untrusted_source_markup():
    result = _md('<script>alert(1)</script> [click](javascript:alert(1))')
    assert "<script>" not in result
    assert "[click](" not in result


def test_cli_build_and_validate_all_pending_without_database(evidence, tmp_path, capsys):
    bundle, manifest, _ = evidence
    pin = manifest["manifest_sha256"]
    packet = tmp_path / "packet"
    assert main([]) == 0
    assert main(["build", "--bundle", str(bundle), "--expected-manifest-sha256", pin,
                 "--output", str(packet)]) == 0
    result_path = tmp_path / "proposals.json"
    args = ["validate", "--bundle", str(bundle), "--expected-manifest-sha256", pin,
            "--review-dir", str(packet / "batches"), "--output", str(result_path)]
    assert main(args) == 0
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["proposals"] == []
    assert result["states"] == {"pending": 1}
    with pytest.raises(ReviewValidationError, match="outside"):
        main(args[:-1] + [str(bundle / "forbidden-new-file.json")])
    batch_path = next((packet / "batches").glob("*.json"))
    batch = json.loads(batch_path.read_text(encoding="utf-8"))
    batch["rows"][0]["decision"]["reviewer"] = "Test fixture"
    batch_path.write_text(json.dumps(batch), encoding="utf-8")
    rejected_path = tmp_path / "rejected.json"
    assert main(args[:-1] + [str(rejected_path)]) == 1
    assert not rejected_path.exists()
    assert "proposal_count" in capsys.readouterr().out
