"""Contracts for the restricted decision-facts expert-review bundle."""

import hashlib
import json
import os
import stat
import sys
from datetime import datetime, timezone

import pytest

from scripts import build_decision_facts_review_bundle as review_bundle


def _report():
    return {
        "schema_version": 1,
        "contract_version": "2026-08-20.2",
        "contract_sha256": "a" * 64,
        "generated_at_utc": "2026-08-20T00:00:00+00:00",
        "deployed_commit": "abc123",
        "execution_profile": {
            "llm_calls_allowed": False,
            "postgresql_writes_allowed": False,
        },
        "review_manifest": {
            "stratified": [
                {
                    "document_id": "doc-1",
                    "title": "=unsafe title",
                    "source_url": "https://example.test/1",
                    "authority_body": "mof_dispute_council",
                    "dispute_type": "tax",
                    "outcome": "satisfied",
                    "in_favor": "taxpayer",
                    "decision_number": "1",
                    "decision_date": "2026-01-01",
                    "contested_articles": ["166"],
                    "has_amount": True,
                }
            ],
            "anomalies": [
                {
                    "document_id": "doc-1",
                    "title": "=unsafe title",
                    "source_url": "https://example.test/1",
                    "authority_body": "mof_dispute_council",
                    "outcome": "satisfied",
                    "anomaly_flags": ["outcome_alignment"],
                },
                {
                    "document_id": "doc-2",
                    "title": "Second",
                    "source_url": "https://example.test/2",
                    "authority_body": "city_court",
                    "outcome": "unclear",
                    "anomaly_flags": ["missing_decision_date", "unclear_outcome"],
                },
            ],
        },
    }


def _restricted_report(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps(_report()), encoding="utf-8")
    path.chmod(0o600)
    return path


def test_bundle_deduplicates_documents_and_preserves_all_reasons():
    bundle = review_bundle.build_bundle(
        _report(),
        "b" * 64,
        generated_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
    )

    assert bundle["counts"]["unique_items"] == 2
    first = next(item for item in bundle["items"] if item["document_id"] == "doc-1")
    assert first["sample_reasons"] == [
        "anomaly:outcome_alignment",
        "stratum:mof_dispute_council:satisfied",
    ]
    assert first["review"]["review_state"] == "pending"
    assert first["review"]["outcome_correct"] is None


def test_csv_is_utf8_and_neutralizes_spreadsheet_formulas():
    bundle = review_bundle.build_bundle(_report(), "b" * 64)
    rendered = review_bundle.render_csv(bundle)

    assert rendered.startswith(b"\xef\xbb\xbf")
    assert "'=unsafe title" in rendered.decode("utf-8-sig")


def test_materialization_is_exclusive_restricted_and_checksummed(tmp_path):
    bundle = review_bundle.build_bundle(_report(), "b" * 64)
    output = tmp_path / "expert-review"

    hashes = review_bundle.materialize_bundle(output, bundle)

    assert set(hashes) == {
        "REVIEW_INSTRUCTIONS.md",
        "review_bundle.json",
        "review_sheet.csv",
    }
    assert (output / "SHA256SUMS").is_file()
    if os.name == "posix":
        assert stat.S_IMODE(output.stat().st_mode) == 0o700
        for path in output.iterdir():
            assert stat.S_IMODE(path.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        review_bundle.materialize_bundle(output, bundle)


def test_execute_requires_exact_fresh_item_count(tmp_path, monkeypatch):
    source = _restricted_report(tmp_path)
    output = tmp_path / "must-not-exist"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_decision_facts_review_bundle.py",
            "--input",
            str(source),
            "--output-dir",
            str(output),
            "--execute",
            "--expected-items",
            "3",
            "--expected-report-sha256",
            hashlib.sha256(source.read_bytes()).hexdigest(),
        ],
    )

    with pytest.raises(ValueError, match="expected 3, got 2"):
        review_bundle.main()
    assert not output.exists()
