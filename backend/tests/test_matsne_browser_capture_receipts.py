from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from legal_temporal.browser_capture_receipts import (
    BROWSER_RECEIPT_AUDIT_CONTRACT,
    BROWSER_RECEIPT_CONTRACT,
    CAPTURE_METHOD,
    audit_browser_capture_receipts,
    browser_receipt_file,
    compact_browser_receipt_audit,
)
from legal_temporal.publication_capture import create_capture_packet, read_capture_plan
from legal_temporal.publication_editions import PublicationEditionValidationError


NOW = datetime(2026, 9, 5, 10, 0, tzinfo=UTC)
ACT = {
    "act_key": "ge-tax-code",
    "document_id": "1043717",
    "title_ka": "საქართველოს საგადასახადო კოდექსი",
    "language": "ka",
    "official_document_url": "https://matsne.gov.ge/ka/document/view/1043717",
}


def _page(publication: int) -> bytes:
    return (
        "<!doctype html><html><body><main><div id=\"document-content\">"
        f"<a id=\"part_{publication}\"></a><section><h2>მუხლი 1. სათაური</h2>"
        f"<p>ოფიციალური ტექსტი {publication}</p></section>"
        "</div></main></body></html>"
    ).encode()


def _tree(publication: int) -> bytes:
    return json.dumps(
        {
            "Title": "ROOT",
            "Anchor": "ROOT",
            "DocumentPart": [
                {"Title": "მუხლი 1. სათაური", "Anchor": f"part_{publication}"}
            ],
        },
        ensure_ascii=False,
    ).encode()


def _response(item, kind: str, raw: bytes, fetched_at="2026-09-05T09:00:00.000Z"):
    return {
        "requested_url": item[f"{kind}_url"],
        "response_url": item[f"{kind}_url"],
        "file": item[f"{kind}_file"],
        "status": 200,
        "content_type": "text/html; charset=utf-8"
        if kind == "page"
        else "application/json; charset=utf-8",
        "etag": "",
        "last_modified": "",
        "byte_length": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "fetched_at_utc": fetched_at,
    }


def _write_receipt(packet: Path, item, plan_sha: str, *, mutate=None):
    page = _page(item["publication"])
    tree = _tree(item["publication"])
    (packet / item["page_file"]).write_bytes(page)
    (packet / item["tree_file"]).write_bytes(tree)
    receipt = {
        "contract": BROWSER_RECEIPT_CONTRACT,
        "capture_method": CAPTURE_METHOD,
        "plan_sha256": plan_sha,
        "publication": item["publication"],
        "browser_origin": "https://matsne.gov.ge",
        "completed_at_utc": "2026-09-05T09:00:01.000Z",
        "page": _response(item, "page", page),
        "tree": _response(item, "tree", tree),
        "database_writes_allowed": False,
        "public_answer_routing_changed": False,
    }
    if mutate:
        mutate(receipt)
    (packet / browser_receipt_file(item["publication"])).write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return receipt


@pytest.fixture
def packet(tmp_path):
    output = tmp_path / "capture"
    created = create_capture_packet(
        output, ACT, first_publication=0, last_publication=1
    )
    plan, _ = read_capture_plan(output / "capture_plan.json")
    return output, created, plan


def test_empty_receipt_audit_is_read_only_and_actionable(packet):
    output, created, _plan = packet
    before = sorted(path.relative_to(output) for path in output.rglob("*"))
    report = audit_browser_capture_receipts(
        output / "capture_plan.json",
        output,
        expected_plan_sha256=created["plan_sha256"],
        now=NOW,
    )
    after = sorted(path.relative_to(output) for path in output.rglob("*"))
    assert before == after
    assert report["contract"] == BROWSER_RECEIPT_AUDIT_CONTRACT
    assert report["summary"] == {
        "planned_editions": 2,
        "page_files_present": 0,
        "tree_files_present": 0,
        "receipts_present": 0,
        "source_pairs_valid": 0,
        "valid_receipts": 0,
        "pending_editions": 2,
        "total_evidence_bytes_observed": 0,
    }
    assert report["next_action"]["publication"] == 0
    assert report["next_action"]["errors"] == [
        "missing_page_file",
        "missing_tree_file",
        "missing_receipt_file",
    ]
    assert compact_browser_receipt_audit(report)["pending_editions"] == 2
    assert not report["database_writes_allowed"]
    assert not report["public_answer_routing_changed"]


def test_complete_browser_receipts_bind_exact_sources(packet):
    output, created, plan = packet
    for item in plan["items"]:
        _write_receipt(output, item, created["plan_sha256"])
    report = audit_browser_capture_receipts(
        output / "capture_plan.json",
        output,
        expected_plan_sha256=created["plan_sha256"],
        now=NOW,
    )
    assert report["complete"]
    assert report["summary"]["source_pairs_valid"] == 2
    assert report["summary"]["valid_receipts"] == 2
    assert report["summary"]["pending_editions"] == 0
    assert report["details"][0]["article_count"] == 1
    assert report["details"][0]["receipt_sha256"] == hashlib.sha256(
        (output / browser_receipt_file(0)).read_bytes()
    ).hexdigest()


@pytest.mark.parametrize(
    "mutate,error",
    [
        (lambda value: value.__setitem__("plan_sha256", "0" * 64), "plan pin"),
        (lambda value: value.__setitem__("browser_origin", "https://example.com"), "origin"),
        (lambda value: value["page"].__setitem__("status", 403), "status"),
        (lambda value: value["page"].__setitem__("response_url", "https://example.com"), "URL"),
        (lambda value: value["tree"].__setitem__("sha256", "0" * 64), "SHA-256 mismatch"),
        (lambda value: value["page"].__setitem__("byte_length", 1), "byte length"),
        (
            lambda value: value.__setitem__(
                "completed_at_utc", "2027-01-01T00:00:00.000Z"
            ),
            "future",
        ),
        (lambda value: value.__setitem__("database_writes_allowed", True), "database"),
    ],
)
def test_receipt_identity_and_runtime_flags_fail_closed(packet, mutate, error):
    output, created, plan = packet
    _write_receipt(output, plan["items"][0], created["plan_sha256"], mutate=mutate)
    report = audit_browser_capture_receipts(
        output / "capture_plan.json",
        output,
        expected_plan_sha256=created["plan_sha256"],
        now=NOW,
    )
    assert not report["details"][0]["ready"]
    assert any(error in message for message in report["details"][0]["errors"])


def test_source_change_after_receipt_is_detected(packet):
    output, created, plan = packet
    item = plan["items"][0]
    _write_receipt(output, item, created["plan_sha256"])
    page_path = output / item["page_file"]
    changed = page_path.read_bytes().replace(
        "ოფიციალური ტექსტი 0".encode(), "ოფიციალური ტექსტი 9".encode()
    )
    page_path.write_bytes(changed)
    report = audit_browser_capture_receipts(
        output / "capture_plan.json",
        output,
        expected_plan_sha256=created["plan_sha256"],
        now=NOW,
    )
    assert any("SHA-256 mismatch" in error for error in report["details"][0]["errors"])


def test_challenge_page_and_receipt_without_source_are_quarantined(packet):
    output, created, plan = packet
    first, second = plan["items"]
    _write_receipt(output, first, created["plan_sha256"])
    blocked = b"<html><title>Access Denied</title></html>"
    (output / first["page_file"]).write_bytes(blocked)
    receipt_path = output / browser_receipt_file(first["publication"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["page"].update(
        {"byte_length": len(blocked), "sha256": hashlib.sha256(blocked).hexdigest()}
    )
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    _write_receipt(output, second, created["plan_sha256"])
    (output / second["tree_file"]).unlink()
    report = audit_browser_capture_receipts(
        output / "capture_plan.json",
        output,
        expected_plan_sha256=created["plan_sha256"],
        now=NOW,
    )
    assert any("challenge" in error for error in report["details"][0]["errors"])
    assert "missing_tree_file" in report["details"][1]["errors"]
    assert "receipt has no complete source pair" in report["details"][1]["errors"]


def test_source_pair_without_articles_is_not_ready(packet):
    output, created, plan = packet
    item = plan["items"][0]
    _write_receipt(output, item, created["plan_sha256"])
    empty_page = b'<!doctype html><html><body><main id="document-content"></main></body></html>'
    empty_tree = json.dumps({"Title": "ROOT", "Anchor": "ROOT"}).encode()
    (output / item["page_file"]).write_bytes(empty_page)
    (output / item["tree_file"]).write_bytes(empty_tree)
    receipt_path = output / browser_receipt_file(item["publication"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["page"] = _response(item, "page", empty_page)
    receipt["tree"] = _response(item, "tree", empty_tree)
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    report = audit_browser_capture_receipts(
        output / "capture_plan.json",
        output,
        expected_plan_sha256=created["plan_sha256"],
        now=NOW,
    )
    assert "tree contains no extractable articles" in report["details"][0]["errors"]
    assert not report["details"][0]["ready"]


def test_receipt_json_is_strict_and_plan_pin_is_required(packet):
    output, created, plan = packet
    item = plan["items"][0]
    _write_receipt(output, item, created["plan_sha256"])
    receipt_path = output / browser_receipt_file(item["publication"])
    receipt_path.write_text(
        '{"contract":"a","contract":"b"}', encoding="utf-8"
    )
    report = audit_browser_capture_receipts(
        output / "capture_plan.json",
        output,
        expected_plan_sha256=created["plan_sha256"],
        now=NOW,
    )
    assert "duplicate JSON object key" in report["details"][0]["errors"]
    with pytest.raises(PublicationEditionValidationError, match="identity pin"):
        audit_browser_capture_receipts(
            output / "capture_plan.json",
            output,
            expected_plan_sha256="0" * 64,
            now=NOW,
        )


def test_browser_collector_is_syntax_valid_and_has_safety_controls():
    script = Path(__file__).resolve().parents[1] / "scripts/matsne_same_origin_capture.js"
    source = script.read_text(encoding="utf-8")
    assert 'EXPECTED_ORIGIN = "https://matsne.gov.ge"' in source
    assert 'credentials: "include"' in source
    assert 'cache: "no-store"' in source
    assert "writeNewOrMatch" in source
    assert "__MATSNE_CAPTURE_ABORT__" in source
    assert "database_writes_allowed: false" in source
    node = "node.exe" if os.name == "nt" else "node"
    result = subprocess.run(
        [node, "--check", str(script)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_receipt_auditor_imports_without_database_or_http_clients(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    code = (
        "import sys; import legal_temporal.browser_capture_receipts as r; "
        "assert 'sqlalchemy' not in sys.modules; "
        "assert 'requests' not in sys.modules; "
        "assert r.CAPTURE_METHOD == 'same_origin_browser_fetch'"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(backend)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
