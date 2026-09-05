from __future__ import annotations

import csv
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from legal_temporal.publication_capture import (
    CAPTURE_PLAN_CONTRACT,
    METADATA_FIELDS,
    audit_capture_packet,
    build_capture_plan,
    compact_audit,
    create_capture_packet,
    finalize_capture_packet,
    read_capture_plan,
)
from legal_temporal.publication_editions import (
    PublicationEditionValidationError,
    build_bundle_proposals,
    validate_and_extract_bundle,
)


NOW = datetime(2026, 9, 5, 10, 0, tzinfo=UTC)
ACT = {
    "act_key": "ge-tax-code",
    "document_id": "1043717",
    "title_ka": "საქართველოს საგადასახადო კოდექსი",
    "language": "ka",
    "official_document_url": "https://matsne.gov.ge/ka/document/view/1043717",
}


def _tree(article_texts):
    return {
        "Title": "ROOT",
        "Anchor": "ROOT",
        "DocumentPart": [
            {
                "Title": f"მუხლი {ref}. სათაური",
                "Anchor": f"part_{index}",
            }
            for index, ref in enumerate(article_texts, 1)
        ],
    }


def _page(publication, valid_from, article_texts):
    articles = "".join(
        f'<a id="part_{index}"></a><section><h2>მუხლი {ref}. სათაური</h2>'
        f"<p>{text}</p></section>"
        for index, (ref, text) in enumerate(article_texts.items(), 1)
    )
    return (
        "<!doctype html><html><body>"
        f"<div>რედაქცია {publication}; ძალაშია {valid_from}</div>"
        f'<main><div id="document-content">{articles}</div></main>'
        "<footer>footer</footer></body></html>"
    ).encode()


def _read_metadata_rows(path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_metadata_rows(path, rows, *, headers=METADATA_FIELDS):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, lineterminator="\n")
        writer.writeheader()
        writer.writerows(
            {field: row.get(field, "") for field in headers} for row in rows
        )


def _fill_packet(packet, editions, *, state="confirmed"):
    plan_path = packet / "capture_plan.json"
    metadata_path = packet / "edition_metadata.csv"
    plan, _ = read_capture_plan(plan_path)
    rows = _read_metadata_rows(metadata_path)
    for item, row, (valid_from, articles) in zip(
        plan["items"], rows, editions, strict=True
    ):
        page = _page(item["publication"], valid_from, articles)
        tree = json.dumps(_tree(articles), ensure_ascii=False).encode()
        (packet / item["page_file"]).write_bytes(page)
        (packet / item["tree_file"]).write_bytes(tree)
        row.update(
            {
                "valid_from": valid_from,
                "effective_date_quote": f"ძალაშია {valid_from}",
                "date_evidence_state": state,
                "reviewer": "Fixture Legal Expert",
                "reviewed_at_utc": "2026-09-05T09:00:00Z",
                "rationale": "Fixture confirmation of the exact official effective-date passage.",
            }
        )
    _write_metadata_rows(metadata_path, rows)
    return plan, rows


@pytest.fixture
def packet(tmp_path):
    output = tmp_path / "tax-capture"
    result = create_capture_packet(
        output, ACT, first_publication=0, last_publication=1
    )
    return output, result


def test_mass_plan_is_deterministic_canonical_and_excel_compatible(tmp_path):
    plan_a = build_capture_plan(ACT, first_publication=0, last_publication=245)
    plan_b = build_capture_plan(ACT, first_publication=0, last_publication=245)
    assert plan_a == plan_b
    assert plan_a["contract"] == CAPTURE_PLAN_CONTRACT
    assert plan_a["range"] == {
        "first_publication": 0,
        "last_publication": 245,
        "publication_count": 246,
    }
    assert plan_a["items"][245] == {
        "publication": 245,
        "page_url": "https://matsne.gov.ge/ka/document/view/1043717?publication=245",
        "page_file": "editions/000245/page.html",
        "tree_url": "https://matsne.gov.ge/ka/document/tree/1043717/245",
        "tree_file": "editions/000245/tree.json",
    }
    output = tmp_path / "packet"
    result = create_capture_packet(
        output, ACT, first_publication=0, last_publication=245
    )
    assert result["publication_count"] == 246
    assert (output / "edition_metadata.csv").read_bytes().startswith(b"\xef\xbb\xbf")
    assert len(_read_metadata_rows(output / "edition_metadata.csv")) == 246
    assert (output / "editions/000245").is_dir()
    if os.name != "nt":
        assert output.stat().st_mode & 0o077 == 0
    with pytest.raises(PublicationEditionValidationError, match="already exists"):
        create_capture_packet(output, ACT, first_publication=0, last_publication=1)


@pytest.mark.parametrize(
    "first,last,error",
    [
        (3, 2, "must not precede"),
        (0, 2000, "exceeds"),
        (-1, 2, "between"),
        (True, 2, "integer"),
    ],
)
def test_plan_range_is_bounded(first, last, error):
    with pytest.raises(PublicationEditionValidationError, match=error):
        build_capture_plan(ACT, first_publication=first, last_publication=last)


def test_empty_capture_audit_is_read_only_and_points_to_first_action(packet):
    output, created = packet
    report = audit_capture_packet(
        output / "capture_plan.json",
        output / "edition_metadata.csv",
        output,
        expected_plan_sha256=created["plan_sha256"],
        now=NOW,
    )
    assert report["summary"] == {
        "planned_editions": 2,
        "page_files_present": 0,
        "tree_files_present": 0,
        "source_pairs_valid": 0,
        "date_evidence_confirmed": 0,
        "ready_editions": 0,
        "pending_editions": 2,
        "total_source_bytes_observed": 0,
    }
    assert not report["complete"]
    assert report["next_action"]["publication"] == 0
    assert report["next_action"]["errors"] == [
        "missing_page_file",
        "missing_tree_file",
        "effective_date_pending",
    ]
    assert not report["database_writes_allowed"]
    assert not report["public_answer_routing_changed"]
    assert compact_audit(report)["pending_editions"] == 2
    assert not (output / "manifest.json").exists()


def test_complete_packet_finalizes_and_feeds_version_builder(packet):
    output, created = packet
    _fill_packet(
        output,
        [
            ("2020-01-01", {"1": "ძველი ტექსტი"}),
            ("2021-01-01", {"1": "ახალი ტექსტი", "2": "ახალი მუხლი"}),
        ],
    )
    report = audit_capture_packet(
        output / "capture_plan.json",
        output / "edition_metadata.csv",
        output,
        expected_plan_sha256=created["plan_sha256"],
        now=NOW,
    )
    assert report["complete"]
    assert report["summary"]["ready_editions"] == 2
    assert report["summary"]["source_pairs_valid"] == 2
    manifest, admission = finalize_capture_packet(
        output / "capture_plan.json",
        output / "edition_metadata.csv",
        output,
        expected_plan_sha256=created["plan_sha256"],
        manifest_output=output / "manifest.json",
        admission_output=output / "capture_admission.json",
        now=NOW,
    )
    manifest_raw = (output / "manifest.json").read_bytes()
    manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
    assert admission["manifest_sha256"] == manifest_sha
    assert admission["metadata_sha256"] == report["metadata_sha256"]
    assert admission["capture_audit_sha256"] == report["audit_sha256"]
    assert admission["authoritative_versions_created"] == 0
    assert len(admission["date_reviews"]) == 2
    assert manifest["editions"][0]["expected_article_count"] == 1
    assert manifest["editions"][1]["expected_article_count"] == 2

    identity, editions = validate_and_extract_bundle(
        output, expected_manifest_sha256=manifest_sha
    )
    proposals = build_bundle_proposals(
        output,
        output.parent / "proposals.json",
        expected_manifest_sha256=manifest_sha,
    )
    assert identity["manifest_sha256"] == manifest_sha
    assert len(editions) == 2
    assert proposals["summary"]["distinct_articles"] == 2
    assert proposals["summary"]["version_proposals"] == 3
    with pytest.raises(PublicationEditionValidationError, match="already exists"):
        finalize_capture_packet(
            output / "capture_plan.json",
            output / "edition_metadata.csv",
            output,
            expected_plan_sha256=created["plan_sha256"],
            manifest_output=output / "manifest.json",
            admission_output=output / "capture_admission.json",
            now=NOW,
        )


def test_pending_or_deferred_dates_block_finalization(packet):
    output, created = packet
    _fill_packet(
        output,
        [
            ("2020-01-01", {"1": "ა"}),
            ("2021-01-01", {"1": "ბ"}),
        ],
        state="pending",
    )
    rows = _read_metadata_rows(output / "edition_metadata.csv")
    rows[1]["date_evidence_state"] = "defer"
    _write_metadata_rows(output / "edition_metadata.csv", rows)
    report = audit_capture_packet(
        output / "capture_plan.json",
        output / "edition_metadata.csv",
        output,
        expected_plan_sha256=created["plan_sha256"],
        now=NOW,
    )
    assert report["summary"]["source_pairs_valid"] == 2
    assert report["summary"]["date_evidence_confirmed"] == 0
    assert report["details"][0]["errors"] == ["effective_date_pending"]
    assert report["details"][1]["errors"] == ["effective_date_defer"]
    with pytest.raises(PublicationEditionValidationError, match="incomplete"):
        finalize_capture_packet(
            output / "capture_plan.json",
            output / "edition_metadata.csv",
            output,
            expected_plan_sha256=created["plan_sha256"],
            manifest_output=output / "manifest.json",
            admission_output=output / "capture_admission.json",
            now=NOW,
        )
    assert not (output / "manifest.json").exists()


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("valid_from", "01.01.2020", "YYYY-MM-DD"),
        ("effective_date_quote", "invented passage", "not verbatim"),
        ("valid_from", "2019-01-01", "does not identify"),
        ("reviewer", "x", "3..255"),
        ("reviewed_at_utc", "19:42", "YYYY-MM-DD"),
        ("reviewed_at_utc", "2027-01-01T00:00:00Z", "future"),
        ("rationale", "short", "20..6000"),
        ("effective_date_evidence_file", "../escape.html", "safe relative"),
        ("effective_date_evidence_url", "https://example.com", "official Matsne"),
    ],
)
def test_invalid_date_evidence_stays_visible_and_not_ready(packet, field, value, error):
    output, created = packet
    _fill_packet(
        output,
        [
            ("2020-01-01", {"1": "ა"}),
            ("2021-01-01", {"1": "ბ"}),
        ],
    )
    rows = _read_metadata_rows(output / "edition_metadata.csv")
    rows[0][field] = value
    _write_metadata_rows(output / "edition_metadata.csv", rows)
    report = audit_capture_packet(
        output / "capture_plan.json",
        output / "edition_metadata.csv",
        output,
        expected_plan_sha256=created["plan_sha256"],
        now=NOW,
    )
    assert not report["complete"]
    assert any(error in item for item in report["details"][0]["errors"])
    assert report["details"][1]["ready"]


def test_challenge_page_and_missing_tree_are_quarantined(packet):
    output, created = packet
    plan, rows = _fill_packet(
        output,
        [
            ("2020-01-01", {"1": "ა"}),
            ("2021-01-01", {"1": "ბ"}),
        ],
    )
    (output / plan["items"][0]["page_file"]).write_text(
        "<html><title>Access Denied</title></html>", encoding="utf-8"
    )
    (output / plan["items"][1]["tree_file"]).unlink()
    report = audit_capture_packet(
        output / "capture_plan.json",
        output / "edition_metadata.csv",
        output,
        expected_plan_sha256=created["plan_sha256"],
        now=NOW,
    )
    assert "page_is_access_or_challenge_response" in report["details"][0]["errors"]
    assert "missing_tree_file" in report["details"][1]["errors"]
    assert report["summary"]["source_pairs_valid"] == 0


def test_effective_dates_must_not_go_backwards(packet):
    output, created = packet
    _fill_packet(
        output,
        [("2021-01-01", {"1": "ა"}), ("2020-01-01", {"1": "ბ"})],
    )
    report = audit_capture_packet(
        output / "capture_plan.json",
        output / "edition_metadata.csv",
        output,
        expected_plan_sha256=created["plan_sha256"],
        now=NOW,
    )
    assert not report["complete"]
    assert report["details"][0]["ready"]
    assert "effective dates go backwards" in report["details"][1]["errors"][0]


def test_plan_and_metadata_immutable_identity_fail_closed(packet):
    output, created = packet
    plan_path = output / "capture_plan.json"
    with pytest.raises(PublicationEditionValidationError, match="identity pin"):
        audit_capture_packet(
            plan_path,
            output / "edition_metadata.csv",
            output,
            expected_plan_sha256="0" * 64,
            now=NOW,
        )
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["items"][0]["page_url"] += "&changed=1"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(PublicationEditionValidationError, match="content hash"):
        read_capture_plan(plan_path)

    output2 = output.parent / "packet2"
    created2 = create_capture_packet(
        output2, ACT, first_publication=0, last_publication=1
    )
    rows = _read_metadata_rows(output2 / "edition_metadata.csv")
    rows[0]["page_url"] += "&changed=1"
    _write_metadata_rows(output2 / "edition_metadata.csv", rows)
    with pytest.raises(PublicationEditionValidationError, match="immutable cells"):
        audit_capture_packet(
            output2 / "capture_plan.json",
            output2 / "edition_metadata.csv",
            output2,
            expected_plan_sha256=created2["plan_sha256"],
            now=NOW,
        )


def test_metadata_schema_row_count_and_state_are_strict(packet):
    output, created = packet
    metadata = output / "edition_metadata.csv"
    rows = _read_metadata_rows(metadata)
    _write_metadata_rows(metadata, rows[:-1])
    with pytest.raises(PublicationEditionValidationError, match="row coverage"):
        audit_capture_packet(
            output / "capture_plan.json",
            metadata,
            output,
            expected_plan_sha256=created["plan_sha256"],
            now=NOW,
        )
    _write_metadata_rows(metadata, rows, headers=METADATA_FIELDS[:-1])
    with pytest.raises(PublicationEditionValidationError, match="columns"):
        audit_capture_packet(
            output / "capture_plan.json",
            metadata,
            output,
            expected_plan_sha256=created["plan_sha256"],
            now=NOW,
        )
    rows[0]["date_evidence_state"] = "approved"
    _write_metadata_rows(metadata, rows)
    with pytest.raises(PublicationEditionValidationError, match="unknown"):
        audit_capture_packet(
            output / "capture_plan.json",
            metadata,
            output,
            expected_plan_sha256=created["plan_sha256"],
            now=NOW,
        )


def test_finalize_outputs_must_be_new_and_inside_bundle(packet, tmp_path):
    output, created = packet
    _fill_packet(
        output,
        [("2020-01-01", {"1": "ა"}), ("2021-01-01", {"1": "ბ"})],
    )
    with pytest.raises(PublicationEditionValidationError, match="bundle directory"):
        finalize_capture_packet(
            output / "capture_plan.json",
            output / "edition_metadata.csv",
            output,
            expected_plan_sha256=created["plan_sha256"],
            manifest_output=tmp_path / "manifest.json",
            admission_output=output / "capture_admission.json",
            now=NOW,
        )
    assert not (tmp_path / "manifest.json").exists()


def test_offline_capture_import_has_no_database_or_network_runtime(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    code = (
        "import sys; import legal_temporal.publication_capture as c; "
        "assert 'sqlalchemy' not in sys.modules; "
        "assert 'requests' not in sys.modules; "
        "assert c.CAPTURE_PLAN_CONTRACT == 'matsne-publication-capture-plan-v1'"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(backend)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(os.name == "nt", reason="Windows symlinks require OS privileges")
def test_symlink_capture_source_is_rejected(packet):
    output, created = packet
    plan, _ = _fill_packet(
        output,
        [("2020-01-01", {"1": "ა"}), ("2021-01-01", {"1": "ბ"})],
    )
    page = output / plan["items"][0]["page_file"]
    original = page.with_suffix(".original")
    page.rename(original)
    page.symlink_to(original)
    report = audit_capture_packet(
        output / "capture_plan.json",
        output / "edition_metadata.csv",
        output,
        expected_plan_sha256=created["plan_sha256"],
        now=NOW,
    )
    assert any("regular file" in error for error in report["details"][0]["errors"])
