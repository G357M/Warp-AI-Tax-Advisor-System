"""Contracts for full expert queues, duplicate groups and proposal validation."""

import csv
import hashlib
import io
import json
import os
import stat
from datetime import datetime, timezone

import pytest

from scripts import build_decision_facts_full_review_bundle as bundle_builder
from scripts import export_decision_facts_expert_review as exporter
from scripts import validate_decision_facts_expert_review as validator


def _member(document_id, *, title="Decision", date="2026-01-01", content="hash-a"):
    return {
        "facts_id": f"facts-{document_id}",
        "document_id": document_id,
        "title": title,
        "source_url": f"https://example.test/{document_id}",
        "document_number": "N-1",
        "date_published": date,
        "file_hash": None,
        "content_length": 100,
        "content_md5": content,
        "normalized_content_md5": content,
        "authority_body": "mof_dispute_council",
        "dispute_type": "tax",
        "outcome": "satisfied",
        "in_favor": "taxpayer",
        "decision_number": "1/2026",
        "decision_date": date,
        "case_number": None,
        "normalized_number": "1/2026",
    }


def _review_item(document_id="doc-1"):
    return {
        **_member(document_id, title="=Formula title"),
        "contested_articles": ["98²"],
        "amount_gel": 100.0,
        "queue_reasons": ["non_simple_article_reference"],
    }


def _export_report():
    review_items = [_review_item()]
    duplicate_groups = exporter.build_duplicate_groups(
        [_member("dup-1", content="same"), _member("dup-2", content="same")]
    )
    snapshot = hashlib.sha256(
        json.dumps(
            {"review_items": review_items, "duplicate_groups": duplicate_groups},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": 1,
        "report_type": "decision_facts_full_expert_review",
        "contract_version": "2026-08-20.1",
        "contract_sha256": "a" * 64,
        "generated_at_utc": "2026-08-20T00:00:00+00:00",
        "deployed_commit": "abc123",
        "execution_profile": {
            "llm_calls_allowed": False,
            "postgresql_writes_allowed": False,
            "full_report_must_remain_operational": True,
        },
        "source_snapshot_sha256": snapshot,
        "review_items": review_items,
        "duplicate_groups": duplicate_groups,
    }


def _bundle():
    return bundle_builder.build_bundle(
        _export_report(),
        "b" * 64,
        generated_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
    )


def _csv_rows(payload):
    text = payload.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text, newline="")))


def _complete_review_rows(bundle):
    rows = _csv_rows(bundle_builder.render_review_items(bundle))
    for row in rows:
        row["review_state"] = "complete"
        for field in bundle_builder.FIELD_VERIFICATIONS:
            row[field] = "correct"
        row["evidence_locator"] = "operative part, paragraph 3"
        row["proposed_corrections_json"] = "{}"
        row["confidence"] = "high"
        row["reviewer"] = "expert-a"
        row["reviewed_at_utc"] = "2026-08-20T12:00:00Z"
    return rows


def _complete_duplicate_rows(bundle):
    rows = _csv_rows(bundle_builder.render_duplicate_groups(bundle))
    for row in rows:
        row["review_state"] = "complete"
        row["duplicate_verdict"] = "distinct_decisions"
        row["proposed_exclusions_json"] = "[]"
        row["evidence_locator"] = "both official documents"
        row["legal_rationale"] = "Different legal acts after source comparison."
        row["confidence"] = "high"
        row["reviewer"] = "expert-a"
        row["reviewed_at_utc"] = "2026-08-20T12:00:00Z"
    return rows


def test_export_contract_and_sql_are_read_only():
    contract = exporter.load_contract()

    assert contract["execution_profile"]["llm_calls_allowed"] is False
    assert contract["execution_profile"]["postgresql_writes_allowed"] is False
    sql = f"{exporter.REVIEW_QUEUE_SQL} {exporter.DUPLICATE_MEMBER_SQL}".lower()
    for forbidden in ("insert ", "update ", "delete ", "alter ", "drop ", "truncate "):
        assert forbidden not in sql


def test_duplicate_classification_is_conservative_and_explainable():
    exact, exact_signals = exporter.classify_duplicate_group(
        [_member("a", content="same"), _member("b", content="same")]
    )
    likely, likely_signals = exporter.classify_duplicate_group(
        [_member("c", content="one"), _member("d", content="two")]
    )
    ambiguous, ambiguous_signals = exporter.classify_duplicate_group(
        [
            _member("e", title="First", date="2025-01-01", content="one"),
            _member("f", title="Second", date="2026-01-01", content="two"),
        ]
    )

    assert exact == "exact" and exact_signals["same_content"] is True
    assert likely == "likely" and likely_signals["same_decision_date"] is True
    assert ambiguous == "ambiguous"
    assert ambiguous_signals["same_decision_date"] is False


def test_connected_export_summary_is_pinned_and_aggregate(monkeypatch):
    review = _review_item()
    review["queue_reasons"] = ["outcome_alignment", "unclear_outcome"]
    duplicates = [_member("dup-1", content="same"), _member("dup-2", content="same")]
    monkeypatch.setattr(
        exporter,
        "db_status",
        lambda: {"mode": "db", "driver": "psycopg", "connectable": True},
    )
    monkeypatch.setattr(
        exporter,
        "run_query",
        lambda sql, params=None: (
            [review] if sql == exporter.REVIEW_QUEUE_SQL else duplicates
        ),
    )

    report, summary = exporter.build_export(
        exporter.load_contract(), deployed_commit="abc123"
    )

    assert summary["review_items"] == 1
    assert summary["duplicate_groups"] == 1
    assert summary["duplicate_members"] == 2
    assert summary["duplicate_class_counts"] == {"exact": 1}
    assert report["source_snapshot_sha256"] == summary["snapshot_sha256"]
    assert "title" not in summary and "source_url" not in summary


def test_full_bundle_contains_evidence_and_second_review_fields():
    bundle = _bundle()
    review_csv = bundle_builder.render_review_items(bundle).decode("utf-8-sig")
    duplicate_csv = bundle_builder.render_duplicate_groups(bundle).decode("utf-8-sig")

    assert bundle["counts"] == {
        "review_items": 1,
        "duplicate_groups": 1,
        "duplicate_members": 2,
    }
    assert "evidence_locator" in review_csv
    assert "proposed_corrections_json" in review_csv
    assert "second_reviewer" in review_csv
    assert "proposed_exclusions_json" in duplicate_csv
    assert "'=Formula title" in review_csv


def test_bundle_rejects_repeated_source_identities():
    report = _export_report()
    report["review_items"].append(dict(report["review_items"][0]))

    with pytest.raises(ValueError, match="duplicate review document_id"):
        bundle_builder.build_bundle(report, "b" * 64)

    report = _export_report()
    report["duplicate_groups"].append(dict(report["duplicate_groups"][0]))
    with pytest.raises(ValueError, match="duplicate duplicate-group ID"):
        bundle_builder.build_bundle(report, "b" * 64)


def test_bundle_materialization_is_restricted_and_exclusive(tmp_path):
    output = tmp_path / "full-review"
    hashes = bundle_builder.materialize(output, _bundle())

    assert set(hashes) == {
        "REVIEW_INSTRUCTIONS.md",
        "duplicate_groups.csv",
        "duplicate_members.csv",
        "review_bundle.json",
        "review_items.csv",
    }
    if os.name == "posix":
        assert stat.S_IMODE(output.stat().st_mode) == 0o700
        assert all(
            stat.S_IMODE(path.stat().st_mode) == 0o600 for path in output.iterdir()
        )
    with pytest.raises(FileExistsError):
        bundle_builder.materialize(output, _bundle())


def test_validator_accepts_complete_no_change_review():
    bundle = _bundle()
    summary, manifest = validator.build_validation(
        bundle,
        _complete_review_rows(bundle),
        _complete_duplicate_rows(bundle),
        require_complete=True,
    )

    assert summary["errors"] == []
    assert summary["review_items"] == {"completed": 1, "pending": 0}
    assert summary["duplicate_groups"] == {"completed": 1, "pending": 0}
    assert manifest["execution_profile"] == {
        "postgresql_writes_allowed": False,
        "apply_supported": False,
        "proposal_only": True,
    }


def test_outcome_correction_requires_matching_value_and_second_reviewer():
    bundle = _bundle()
    review_rows = _complete_review_rows(bundle)
    review_rows[0]["outcome_correct"] = "incorrect"
    review_rows[0]["proposed_corrections_json"] = json.dumps({"outcome": "rejected"})
    review_rows[0]["legal_rationale"] = "The operative part rejects the complaint."
    duplicate_rows = _complete_duplicate_rows(bundle)

    summary, _ = validator.build_validation(
        bundle, review_rows, duplicate_rows, require_complete=True
    )
    assert any("second_reviewer" in error for error in summary["errors"])

    review_rows[0]["second_reviewer"] = "expert-b"
    review_rows[0]["second_reviewed_at_utc"] = "2026-08-20T13:00:00Z"
    summary, manifest = validator.build_validation(
        bundle, review_rows, duplicate_rows, require_complete=True
    )
    assert summary["errors"] == []
    assert manifest["fact_correction_proposals"][0]["changes"] == {
        "outcome": {"current": "satisfied", "proposed": "rejected"}
    }


def test_true_duplicate_proposal_accounts_for_members_and_second_review():
    bundle = _bundle()
    review_rows = _complete_review_rows(bundle)
    duplicate_rows = _complete_duplicate_rows(bundle)
    members = bundle["duplicate_groups"][0]["members"]
    duplicate_rows[0]["duplicate_verdict"] = "true_duplicate"
    duplicate_rows[0]["canonical_document_id"] = members[0]["document_id"]
    duplicate_rows[0]["proposed_exclusions_json"] = json.dumps(
        [members[1]["document_id"]]
    )
    duplicate_rows[0]["second_reviewer"] = "expert-b"
    duplicate_rows[0]["second_reviewed_at_utc"] = "2026-08-20T13:00:00Z"

    summary, manifest = validator.build_validation(
        bundle, review_rows, duplicate_rows, require_complete=True
    )

    assert summary["errors"] == []
    assert len(manifest["duplicate_resolution_proposals"]) == 1


def test_second_reviewer_identity_comparison_is_case_insensitive():
    bundle = _bundle()
    review_rows = _complete_review_rows(bundle)
    review_rows[0]["outcome_correct"] = "incorrect"
    review_rows[0]["proposed_corrections_json"] = json.dumps({"outcome": "rejected"})
    review_rows[0]["legal_rationale"] = "Verified in the operative part."
    review_rows[0]["second_reviewer"] = "EXPERT-A"
    review_rows[0]["second_reviewed_at_utc"] = "2026-08-20T13:00:00Z"

    summary, _ = validator.build_validation(
        bundle,
        review_rows,
        _complete_duplicate_rows(bundle),
        require_complete=True,
    )

    assert any("second_reviewer must differ" in error for error in summary["errors"])


def test_validator_rejects_immutable_source_edits_and_pending_rows():
    bundle = _bundle()
    review_rows = _csv_rows(bundle_builder.render_review_items(bundle))
    duplicate_rows = _csv_rows(bundle_builder.render_duplicate_groups(bundle))
    review_rows[0]["document_id"] = "tampered"

    summary, _ = validator.build_validation(
        bundle, review_rows, duplicate_rows, require_complete=True
    )

    assert any("immutable field changed" in error for error in summary["errors"])
    assert any("still pending" in error for error in summary["errors"])
