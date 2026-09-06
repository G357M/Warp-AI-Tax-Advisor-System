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

from legal_temporal.effective_date_candidates import (
    APPROVAL_PHRASE,
    approve_effective_date_candidates,
    draft_effective_date_candidates,
)
from legal_temporal.publication_capture import METADATA_FIELDS, create_capture_packet
from legal_temporal.publication_editions import PublicationEditionValidationError


NOW = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
ACT = {
    "act_key": "ge-tax-code",
    "document_id": "1043717",
    "title_ka": "საქართველოს საგადასახადო კოდექსი",
    "language": "ka",
    "official_document_url": "https://matsne.gov.ge/ka/document/view/1043717",
}


def _page(publication, hint, active_date=None):
    active = (
        f'<a href="/ka/document/view/1043717?publication={publication}" '
        f'class="active list-group-item">{active_date}</a>'
        if active_date
        else ""
    )
    return (
        "<!doctype html><html><body>"
        '<div class="sidebar-content-target"><div class="list-group">'
        f"{active}</div></div>"
        f'<div class="publicationHint"><p>{hint}</p></div>'
        "</body></html>"
    ).encode()


def _read_rows(path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_rows(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=METADATA_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def captured_packet(tmp_path):
    bundle = tmp_path / "capture"
    created = create_capture_packet(
        bundle, ACT, first_publication=0, last_publication=2
    )
    pages = [
        _page(0, "პირველადი სახე (01/01/2020 - 01/02/2020)"),
        _page(
            1,
            "კონსოლიდირებული ვერსია (01/02/2020 - 01/03/2020)",
            "01/02/2020",
        ),
        _page(2, "კონსოლიდირებული ვერსია (საბოლოო)", "01/03/2020"),
    ]
    for publication, raw in enumerate(pages):
        (bundle / f"editions/{publication:06d}/page.html").write_bytes(raw)
    review_dir = tmp_path / "review"
    review_dir.mkdir()
    return bundle, review_dir, created


def _draft(bundle, review_dir, created):
    metadata = review_dir / "edition_metadata.candidates.csv"
    report = review_dir / "effective_date_candidates.json"
    result = draft_effective_date_candidates(
        bundle / "capture_plan.json",
        bundle / "edition_metadata.csv",
        bundle,
        expected_plan_sha256=created["plan_sha256"],
        output_metadata=metadata,
        report_output=report,
    )
    return metadata, report, result


def test_drafts_complete_chain_without_claiming_expert_confirmation(captured_packet):
    bundle, review_dir, created = captured_packet
    metadata, report_path, report = _draft(bundle, review_dir, created)
    assert report["complete"]
    assert report["summary"] == {
        "planned_editions": 3,
        "candidate_editions": 3,
        "direct_interval_candidates": 2,
        "terminal_chain_candidates": 1,
        "blocked_editions": 0,
        "date_evidence_confirmed": 0,
    }
    assert metadata.read_bytes().startswith(b"\xef\xbb\xbf")
    rows = _read_rows(metadata)
    assert [row["valid_from"] for row in rows] == [
        "2020-01-01",
        "2020-02-01",
        "2020-03-01",
    ]
    assert all(row["date_evidence_state"] == "pending" for row in rows)
    assert all(not row["reviewer"] for row in rows)
    assert rows[2]["effective_date_evidence_file"] == "editions/000001/page.html"
    assert "01/03/2020" in rows[2]["effective_date_quote"]
    stored = json.loads(report_path.read_text(encoding="utf-8"))
    assert stored["expert_approval_required"]
    assert not stored["database_writes_allowed"]


def test_conflicting_chain_is_visible_and_not_filled(captured_packet):
    bundle, review_dir, created = captured_packet
    (bundle / "editions/000001/page.html").write_bytes(
        _page(
            1,
            "კონსოლიდირებული ვერსია (02/02/2020 - 01/03/2020)",
            "02/02/2020",
        )
    )
    metadata, _report_path, report = _draft(bundle, review_dir, created)
    assert not report["complete"]
    assert report["summary"]["blocked_editions"] == 1
    assert report["candidates"][1]["errors"] == [
        "preceding interval end does not match interval start"
    ]
    assert _read_rows(metadata)[1]["valid_from"] == ""


def test_reverse_official_interval_is_retained_as_bitemporal_blocker(
    captured_packet,
):
    bundle, review_dir, created = captured_packet
    (bundle / "editions/000001/page.html").write_bytes(
        _page(
            1,
            "კონსოლიდირებული ვერსია (01/02/2020 - 15/01/2020)",
            "01/02/2020",
        )
    )
    (bundle / "editions/000002/page.html").write_bytes(
        _page(2, "კონსოლიდირებული ვერსია (საბოლოო)", "15/01/2020")
    )
    metadata, _report_path, report = _draft(bundle, review_dir, created)
    blocker = report["candidates"][1]
    assert blocker["status"] == "blocked"
    assert blocker["candidate_class"] == "direct_publication_interval"
    assert blocker["evidence"]["quote"].endswith(
        "(01/02/2020 - 15/01/2020)"
    )
    assert "bitemporal legal review" in blocker["errors"][0]
    assert _read_rows(metadata)[1]["valid_from"] == ""


def test_existing_review_work_is_never_overwritten(captured_packet):
    bundle, review_dir, created = captured_packet
    rows = _read_rows(bundle / "edition_metadata.csv")
    rows[0]["notes"] = "expert note is allowed"
    rows[1]["valid_from"] = "2020-02-01"
    _write_rows(bundle / "edition_metadata.csv", rows)
    metadata, _report_path, report = _draft(bundle, review_dir, created)
    assert report["summary"]["blocked_editions"] == 1
    output_rows = _read_rows(metadata)
    assert output_rows[0]["notes"] == "expert note is allowed"
    assert output_rows[1]["valid_from"] == "2020-02-01"


def test_explicit_pinned_batch_approval_confirms_all_candidates(captured_packet):
    bundle, review_dir, created = captured_packet
    candidates, report_path, report = _draft(bundle, review_dir, created)
    output = review_dir / "edition_metadata.confirmed.csv"
    receipt = review_dir / "effective_date_approval.json"
    approval = approve_effective_date_candidates(
        bundle / "capture_plan.json",
        candidates,
        report_path,
        bundle,
        expected_plan_sha256=created["plan_sha256"],
        expected_report_file_sha256=report["report_file_sha256"],
        approval_phrase=APPROVAL_PHRASE,
        reviewer="Fixture Legal Expert",
        reviewed_at_utc="2026-09-06T11:00:00Z",
        rationale="Reviewed every exact Matsne interval and the terminal chain evidence.",
        output_metadata=output,
        approval_output=receipt,
        now=NOW,
    )
    rows = _read_rows(output)
    assert approval["approved_editions"] == 3
    assert approval["pending_editions"] == 0
    assert approval["complete"]
    assert all(row["date_evidence_state"] == "confirmed" for row in rows)
    assert all(row["reviewer"] == "Fixture Legal Expert" for row in rows)
    assert hashlib.sha256(output.read_bytes()).hexdigest() == approval[
        "confirmed_metadata_sha256"
    ]
    assert json.loads(receipt.read_text(encoding="utf-8"))[
        "approval_sha256"
    ] == approval["approval_sha256"]


def test_batch_approval_confirms_safe_subset_and_preserves_blockers(captured_packet):
    bundle, review_dir, created = captured_packet
    (bundle / "editions/000001/page.html").write_bytes(
        _page(
            1,
            "კონსოლიდირებული ვერსია (01/02/2020 - 15/01/2020)",
            "01/02/2020",
        )
    )
    (bundle / "editions/000002/page.html").write_bytes(
        _page(2, "კონსოლიდირებული ვერსია (საბოლოო)", "15/01/2020")
    )
    candidates, report_path, report = _draft(bundle, review_dir, created)
    output = review_dir / "edition_metadata.confirmed.csv"
    receipt = review_dir / "effective_date_approval.json"
    approval = approve_effective_date_candidates(
        bundle / "capture_plan.json",
        candidates,
        report_path,
        bundle,
        expected_plan_sha256=created["plan_sha256"],
        expected_report_file_sha256=report["report_file_sha256"],
        approval_phrase=APPROVAL_PHRASE,
        reviewer="Fixture Legal Expert",
        reviewed_at_utc="2026-09-06T11:00:00Z",
        rationale="Reviewed every non-blocked exact Matsne interval candidate.",
        output_metadata=output,
        approval_output=receipt,
        now=NOW,
    )
    rows = _read_rows(output)
    assert approval["approved_editions"] == 2
    assert approval["pending_editions"] == 1
    assert not approval["complete"]
    assert rows[0]["date_evidence_state"] == "confirmed"
    assert rows[1]["date_evidence_state"] == "pending"
    assert rows[1]["valid_from"] == ""
    assert rows[2]["date_evidence_state"] == "confirmed"


def test_approval_fails_closed_on_phrase_hash_and_candidate_tamper(captured_packet):
    bundle, review_dir, created = captured_packet
    candidates, report_path, report = _draft(bundle, review_dir, created)
    common = {
        "plan_path": bundle / "capture_plan.json",
        "candidate_metadata_path": candidates,
        "candidate_report_path": report_path,
        "bundle": bundle,
        "expected_plan_sha256": created["plan_sha256"],
        "expected_report_file_sha256": report["report_file_sha256"],
        "reviewer": "Fixture Legal Expert",
        "reviewed_at_utc": "2026-09-06T11:00:00Z",
        "rationale": "Reviewed every exact Matsne interval and the terminal chain evidence.",
        "output_metadata": review_dir / "confirmed.csv",
        "approval_output": review_dir / "approval.json",
        "now": NOW,
    }
    with pytest.raises(PublicationEditionValidationError, match="approval phrase"):
        approve_effective_date_candidates(approval_phrase="no", **common)
    common["expected_report_file_sha256"] = "0" * 64
    with pytest.raises(PublicationEditionValidationError, match="hash pin"):
        approve_effective_date_candidates(
            approval_phrase=APPROVAL_PHRASE, **common
        )
    common["expected_report_file_sha256"] = report["report_file_sha256"]
    rows = _read_rows(candidates)
    rows[0]["valid_from"] = "2020-01-02"
    _write_rows(candidates, rows)
    with pytest.raises(PublicationEditionValidationError, match="metadata hash"):
        approve_effective_date_candidates(
            approval_phrase=APPROVAL_PHRASE, **common
        )


def test_candidate_module_has_no_database_or_network_runtime(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    code = (
        "import sys; import legal_temporal.effective_date_candidates as c; "
        "assert 'sqlalchemy' not in sys.modules; "
        "assert 'requests' not in sys.modules; "
        "assert c.APPROVAL_PHRASE.startswith('I_REVIEWED')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(backend)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
