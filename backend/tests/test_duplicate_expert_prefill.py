import hashlib
import json
from pathlib import Path

import pytest

from scripts import prepare_duplicate_expert_prefill as prefill


def _review():
    return {
        "review_state": "pending",
        "duplicate_verdict": "",
        "canonical_document_id": "",
        "proposed_exclusions_json": "",
        "evidence_locator": "",
        "legal_rationale": "",
        "confidence": "",
        "reviewer": "",
        "reviewed_at_utc": "",
        "second_reviewer": "",
        "second_reviewed_at_utc": "",
        "notes": "",
    }


def _bundle():
    members = [
        {"document_id": "doc-a", "source_url": "https://infohub.rs.ge/ka/workspace/document/a"},
        {"document_id": "doc-b", "source_url": "https://infohub.rs.ge/ka/workspace/document/b"},
    ]
    return {
        "schema_version": 1,
        "bundle_type": "decision_facts_full_expert_review",
        "source": {"source_snapshot_sha256": "a" * 64},
        "review_contract": {"database_writes_allowed": False},
        "counts": {"duplicate_groups": 1, "duplicate_members": 2, "review_items": 0},
        "review_items": [],
        "duplicate_groups": [
            {
                "group_id": "DFG-ONE",
                "candidate_class": "exact",
                "authority_body": "Revenue Service",
                "normalized_number": "11623",
                "member_count": 2,
                "signals": ["same_file_hash"],
                "members": members,
                "review": _review(),
            }
        ],
    }


def _report():
    return {
        "schema_version": 1,
        "report_type": "infohub_duplicate_technical_verification",
        "execution_profile": {
            "llm_calls_allowed": False,
            "postgresql_writes_allowed": False,
            "legal_verdicts_allowed": False,
            "automatic_exclusions_allowed": False,
        },
        "legal_effect": {
            "legal_verdicts_created": False,
            "database_changes_created": False,
            "automatic_exclusions_created": False,
            "expert_confirmation_required": True,
        },
        "groups": [
            {
                "group_id": "DFG-ONE",
                "candidate_class": "exact",
                "technical_assessment": "official_content_identical",
                "technical_confidence": "high",
                "member_count": 2,
                "technical_canonical_document_id": "doc-a",
                "technical_exclusion_candidates": ["doc-b"],
                "source_urls": [
                    "https://infohub.rs.ge/ka/workspace/document/a",
                    "https://infohub.rs.ge/ka/workspace/document/b",
                ],
                "evidence_summary": "Official content matched. No legal verdict was applied.",
            }
        ],
    }


def test_prefill_adds_only_technical_evidence_and_notes():
    rows, changed = prefill.build_prefilled_rows(
        bundle=_bundle(),
        report=_report(),
        report_sha256="b" * 64,
    )
    row = rows[0]

    assert changed == 1
    assert "Official InfoHub records" in row["evidence_locator"]
    assert "expert verification required" in row["notes"]
    assert "technical canonical candidate=doc-a" in row["notes"]
    assert row["review_state"] == "pending"
    for field in prefill.PROTECTED_LEGAL_FIELDS:
        assert row[field] == ""


def test_existing_expert_fields_and_completed_rows_are_never_rewritten():
    expected = prefill._expected_rows(_bundle())
    pending = [dict(expected[0])]
    pending[0]["duplicate_verdict"] = "true_duplicate"
    pending[0]["canonical_document_id"] = "doc-a"
    pending[0]["notes"] = "Expert note"

    rows, changed = prefill.build_prefilled_rows(
        bundle=_bundle(), report=_report(), report_sha256="b" * 64, review_rows=pending
    )
    assert changed == 1
    assert rows[0]["duplicate_verdict"] == "true_duplicate"
    assert rows[0]["canonical_document_id"] == "doc-a"
    assert rows[0]["notes"] == "Expert note"
    assert "Official InfoHub records" in rows[0]["evidence_locator"]

    completed = [dict(expected[0])]
    completed[0]["review_state"] = "complete"
    completed[0]["evidence_locator"] = "Expert evidence"
    completed_rows, completed_changed = prefill.build_prefilled_rows(
        bundle=_bundle(), report=_report(), report_sha256="b" * 64, review_rows=completed
    )
    assert completed_changed == 0
    assert completed_rows == completed


def test_report_must_match_bundle_and_prohibit_legal_effects():
    report = _report()
    report["source"] = {"bundle_sha256": "wrong"}
    with pytest.raises(ValueError, match="was not created from this"):
        prefill._validate_report(report, bundle_sha256="a" * 64)

    report["source"]["bundle_sha256"] = "a" * 64
    report["execution_profile"]["legal_verdicts_allowed"] = True
    with pytest.raises(ValueError, match="unsafe execution profile"):
        prefill._validate_report(report, bundle_sha256="a" * 64)


def test_technical_suggestions_must_reference_group_members():
    report = _report()
    report["groups"][0]["technical_exclusion_candidates"] = ["not-a-member"]

    with pytest.raises(ValueError, match="reference nonmembers"):
        prefill.build_prefilled_rows(
            bundle=_bundle(), report=report, report_sha256="b" * 64
        )


def test_csv_is_formula_safe_and_output_refuses_overwrite():
    row = prefill._expected_rows(_bundle())[0]
    row["notes"] = "=HYPERLINK(\"https://example.com\")"
    payload = prefill.render_rows([row])
    parsed = prefill._parse_csv(payload)
    assert parsed[0]["notes"].startswith("'=HYPERLINK")

    output = Path(__file__).with_name(".duplicate-prefill-output.test.csv")
    try:
        prefill._write_exclusive(output, payload)
        assert hashlib.sha256(output.read_bytes()).hexdigest() == hashlib.sha256(payload).hexdigest()
        with pytest.raises(FileExistsError, match="refusing overwrite"):
            prefill._write_exclusive(output, payload)
    finally:
        if output.exists():
            output.chmod(0o666)
            output.unlink()


def test_report_sha_can_be_pinned_to_exact_bytes():
    raw = json.dumps(_report(), ensure_ascii=False, sort_keys=True).encode("utf-8")
    assert prefill._sha256(raw) == hashlib.sha256(raw).hexdigest()
