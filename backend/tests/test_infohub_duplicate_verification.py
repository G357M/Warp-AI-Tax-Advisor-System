"""Contracts for official-API duplicate technical verification."""

import csv
import io
import json
import os
import stat
from datetime import datetime, timezone

import pytest

from scripts import verify_infohub_duplicate_candidates as verifier


def _member(document_id, source_key, *, content="same"):
    return {
        "facts_id": f"facts-{document_id}",
        "document_id": document_id,
        "title": "Decision",
        "source_url": f"https://infohub.rs.ge/ka/workspace/document/{source_key}",
        "document_number": "11623",
        "date_published": "2026-05-27",
        "file_hash": content,
        "content_length": 100,
        "content_md5": content,
        "normalized_content_md5": content,
        "authority_body": "revenue_service_council",
        "dispute_type": "tax",
        "outcome": "rejected",
        "in_favor": "authority",
        "decision_number": "11623",
        "decision_date": "2026-05-27",
        "case_number": None,
        "normalized_number": "11623",
    }


def _group(*, candidate_class="likely"):
    return {
        "group_id": "DFG-EXAMPLE",
        "candidate_class": candidate_class,
        "authority_body": "revenue_service_council",
        "normalized_number": "11623",
        "signals": {},
        "member_count": 2,
        "members": [
            _member("doc-b", "9604352c-9678-4fa0-85cf-3f882c60eef5"),
            _member("doc-a", "846760da-bd66-4525-acee-3ee8918e6e49"),
        ],
        "review": {"review_state": "pending"},
    }


def _bundle():
    group = _group()
    return {
        "schema_version": 1,
        "bundle_type": "decision_facts_full_expert_review",
        "source": {
            "source_snapshot_sha256": "a" * 64,
            "deployed_commit": "abc123",
        },
        "review_contract": {"database_writes_allowed": False},
        "counts": {
            "review_items": 0,
            "duplicate_groups": 1,
            "duplicate_members": 2,
        },
        "review_items": [],
        "duplicate_groups": [group],
    }


def _live(
    source_url,
    body,
    *,
    receipt_date="2026-05-27T00:00:00",
    decision_content="same structured decision",
):
    key = source_url.rsplit("/", 1)[-1]
    return {
        "ok": True,
        "source_url": source_url,
        "official_api_url": f"https://infohubapi.rs.ge/api/documents/{key}",
        "language": "ka",
        "unique_key": key,
        "metadata": {
            "name": "ბრძანება N 11623",
            "documentNumber": "11623",
            "type": "შემოსავლების სამსახურის დავების გადაწყვეტილება",
            "baseType": "საგადასახადო/საბაჟო დავა",
            "status": "მოქმედი",
            "receiptDate": receipt_date,
            "publishDate": None,
            "effectiveDate": None,
            "expirationDate": None,
            "createDate": None,
            "updateDate": None,
            "parentDocumentId": None,
        },
        "body_length": len(body),
        "normalized_body_length": len(body),
        "normalized_body_sha256": verifier._hash_text(body),
        "normalized_canonical_length": len(body),
        "normalized_canonical_sha256": verifier._hash_text(body),
        "decision_content_sha256": (
            verifier._hash_text(decision_content) if decision_content else None
        ),
        "_normalized_body": body,
    }


def test_contract_prohibits_legal_and_database_actions():
    contract = verifier.load_contract()
    profile = contract["execution_profile"]

    assert profile["llm_calls_allowed"] is False
    assert profile["postgresql_reads_allowed"] is False
    assert profile["postgresql_writes_allowed"] is False
    assert profile["legal_verdicts_allowed"] is False
    assert profile["automatic_exclusions_allowed"] is False


def test_source_url_is_fixed_to_official_document_uuid():
    contract = verifier.load_contract()
    language, key, api_url = verifier.parse_source_url(
        "https://infohub.rs.ge/ka/workspace/document/9604352c-9678-4fa0-85cf-3f882c60eef5",
        contract,
    )

    assert language == "ka"
    assert key == "9604352c-9678-4fa0-85cf-3f882c60eef5"
    assert api_url.startswith("https://infohubapi.rs.ge/api/documents/")
    for unsafe in (
        "http://infohub.rs.ge/ka/workspace/document/9604352c-9678-4fa0-85cf-3f882c60eef5",
        "https://evil.test/ka/workspace/document/9604352c-9678-4fa0-85cf-3f882c60eef5",
        "https://infohub.rs.ge/ka/workspace/document/not-a-uuid",
        "https://infohub.rs.ge/ka/workspace/document/9604352c-9678-4fa0-85cf-3f882c60eef5?next=evil",
    ):
        with pytest.raises(ValueError):
            verifier.parse_source_url(unsafe, contract)


def test_html_normalization_ignores_markup_whitespace_and_scripts():
    left = verifier.normalize_text(
        verifier.html_to_text("<p>ერთი&nbsp;ორი</p><script>bad()</script><p>სამი</p>")
    )
    right = verifier.normalize_text("ერთი ორი სამი")

    assert left == right
    assert "bad" not in left
    assert verifier.normalize_text("98²") != verifier.normalize_text("982")


def test_identical_official_content_becomes_batch_confirmation_candidate():
    group = _group()
    first_url = group["members"][0]["source_url"]
    second_url = group["members"][1]["source_url"]
    fetched = {
        first_url: _live(first_url, "same normalized official body"),
        second_url: _live(
            second_url,
            "same normalized official body",
            receipt_date="2026-05-29T00:00:00",
        ),
    }

    result = verifier.compare_group(group, fetched, verifier.load_contract())

    assert result["technical_assessment"] == "official_content_identical"
    assert result["expert_action"] == "expert_batch_confirmation_candidate"
    assert result["technical_canonical_document_id"] == "doc-a"
    assert result["technical_exclusion_candidates"] == ["doc-b"]
    assert result["metadata_differences"] == ["receiptDate"]
    assert result["minimum_live_similarity"] == 1.0
    assert result["minimum_token_sequence_similarity"] == 1.0
    assert result["same_live_decision_content"] is True


def test_high_ordered_overlap_becomes_priority_confirmation_without_exclusions():
    group = _group()
    first_url = group["members"][0]["source_url"]
    second_url = group["members"][1]["source_url"]
    base_tokens = [f"legal-token-{index}" for index in range(140)]
    changed_tokens = list(base_tokens)
    changed_tokens[40:45] = [f"changed-token-{index}" for index in range(5)]
    fetched = {
        first_url: _live(first_url, " ".join(base_tokens)),
        second_url: _live(second_url, " ".join(changed_tokens)),
    }

    result = verifier.compare_group(group, fetched, verifier.load_contract())

    assert result["technical_assessment"] == "official_content_high_overlap"
    assert result["expert_action"] == "expert_priority_confirmation"
    assert result["minimum_token_sequence_similarity"] >= 0.95
    assert result["same_live_decision_content"] is True
    assert result["technical_canonical_document_id"] is None
    assert result["technical_exclusion_candidates"] == []


def test_different_content_remains_manual_review():
    group = _group()
    first_url = group["members"][0]["source_url"]
    second_url = group["members"][1]["source_url"]
    fetched = {
        first_url: _live(first_url, "first unrelated legal body"),
        second_url: _live(second_url, "second completely different text"),
    }

    result = verifier.compare_group(group, fetched, verifier.load_contract())

    assert result["technical_assessment"] == "official_content_differs"
    assert result["expert_action"] == "manual_review"
    assert result["technical_canonical_document_id"] is None
    assert result["technical_exclusion_candidates"] == []


def test_incomplete_fetch_never_creates_technical_exclusions():
    group = _group()
    first_url = group["members"][0]["source_url"]
    second_url = group["members"][1]["source_url"]
    fetched = {
        first_url: _live(first_url, "same"),
        second_url: {"ok": False, "source_url": second_url, "error": "HTTP 503"},
    }

    result = verifier.compare_group(group, fetched, verifier.load_contract())

    assert result["technical_assessment"] == "verification_incomplete"
    assert result["technical_exclusion_candidates"] == []
    assert result["fetch_success_count"] == 1


def test_verify_groups_deduplicates_requests_and_reports_aggregates():
    group = _group()

    def fake_fetcher(source_url, contract, **kwargs):
        return _live(source_url, "same official body")

    comparisons, summary = verifier.verify_groups(
        [group],
        verifier.load_contract(),
        timeout_seconds=1,
        retries=0,
        max_workers=2,
        request_interval_seconds=0,
        fetcher=fake_fetcher,
    )

    assert len(comparisons) == 1
    assert summary == {
        "groups": 1,
        "members": 2,
        "official_api_requests": 2,
        "fetch_successes": 2,
        "fetch_failures": 0,
        "assessment_counts": {"official_content_identical": 1},
        "confirmation_queue_groups": 1,
    }


def test_report_and_csv_contain_hashes_but_not_legal_text():
    group = _group()
    first_url = group["members"][0]["source_url"]
    second_url = group["members"][1]["source_url"]
    fetched = {
        first_url: _live(first_url, "secret body that must not be exported"),
        second_url: _live(second_url, "secret body that must not be exported"),
    }
    comparison = verifier.compare_group(group, fetched, verifier.load_contract())
    report = verifier.build_report(
        bundle=_bundle(),
        bundle_sha256="b" * 64,
        contract=verifier.load_contract(),
        selected_groups=[group],
        comparisons=[comparison],
        verification_summary={
            "groups": 1,
            "members": 2,
            "official_api_requests": 2,
            "fetch_successes": 2,
            "fetch_failures": 0,
            "assessment_counts": {"official_content_identical": 1},
            "confirmation_queue_groups": 1,
        },
    )
    serialized = json.dumps(report, ensure_ascii=False)
    csv_text = verifier.render_triage_csv(report).decode("utf-8-sig")
    queue_text = verifier.render_triage_csv(
        report, confirmation_queue=True
    ).decode("utf-8-sig")

    assert "secret body" not in serialized
    assert "secret body" not in csv_text
    assert "secret body" not in queue_text
    assert "normalized_body_sha256" in serialized
    assert (
        list(csv.DictReader(io.StringIO(csv_text, newline="")))[0][
            "technical_assessment"
        ]
        == "official_content_identical"
    )
    assert report["legal_effect"] == {
        "legal_verdicts_created": False,
        "database_changes_created": False,
        "automatic_exclusions_created": False,
        "expert_confirmation_required": True,
    }


def test_materialization_is_restricted_and_exclusive(tmp_path):
    group = _group()
    first_url = group["members"][0]["source_url"]
    second_url = group["members"][1]["source_url"]
    fetched = {
        first_url: _live(first_url, "same"),
        second_url: _live(second_url, "same"),
    }
    comparison = verifier.compare_group(group, fetched, verifier.load_contract())
    report = verifier.build_report(
        bundle=_bundle(),
        bundle_sha256="b" * 64,
        contract=verifier.load_contract(),
        selected_groups=[group],
        comparisons=[comparison],
        verification_summary={
            "groups": 1,
            "members": 2,
            "official_api_requests": 2,
            "fetch_successes": 2,
            "fetch_failures": 0,
            "assessment_counts": {"official_content_identical": 1},
            "confirmation_queue_groups": 1,
        },
    )
    output = tmp_path / "technical-verification"

    hashes = verifier.materialize(output, report)

    assert set(hashes) == {
        "README.md",
        "duplicate_confirmation_queue.csv",
        "duplicate_technical_triage.csv",
        "technical_verification.json",
    }
    if os.name == "posix":
        assert stat.S_IMODE(output.stat().st_mode) == 0o700
        assert all(
            stat.S_IMODE(path.stat().st_mode) == 0o600 for path in output.iterdir()
        )
    with pytest.raises(FileExistsError):
        verifier.materialize(output, report)


def test_plan_selection_is_bounded_and_unknown_ids_fail():
    bundle = _bundle()

    selected = verifier.select_groups(bundle, candidate_classes={"likely"})
    assert [group["group_id"] for group in selected] == ["DFG-EXAMPLE"]
    assert verifier.select_groups(bundle, candidate_classes={"exact"}) == []
    with pytest.raises(ValueError, match="unknown requested group IDs"):
        verifier.select_groups(bundle, group_ids={"DFG-UNKNOWN"})
