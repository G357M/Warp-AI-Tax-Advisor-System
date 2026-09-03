"""Admission gates use fixture identities only; never real legal approvals."""

from copy import deepcopy
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from legal_temporal.backfill import sha256_json
from legal_temporal.expert_review import ReviewValidationError
from legal_temporal.review_admission import (
    ADMISSION_CONTRACT, load_proposals, require_pin, second_review_template,
    validate_admission, validate_restore_evidence, validate_rollback_proof,
)
from scripts.admit_legal_temporal_review import main
from test_legal_temporal_expert_review import NOW, _document, _validate, evidence  # noqa: F401


def _second(proposals):
    second = second_review_template(proposals)
    for row in second["rows"]:
        row.update({"state": "agree", "reviewer": "Independent Expert (fixture)",
                    "reviewed_at_utc": "2026-09-03T11:30:00Z",
                    "rationale": "Fixture-only independent assessment; not a real legal decision."})
    return second


def _admission(manifest, texts, state="confirm"):
    proposals = _validate(manifest, texts, _document(manifest, texts, state))
    second = _second(proposals)
    return validate_admission(proposals, second, "b" * 64, now=NOW)


def _recovery_files(tmp_path):
    backup = tmp_path / "fixture-not-a-real-database.dump"
    backup.write_bytes(b"fixture, not a real production dump")
    sha = hashlib.sha256(backup.read_bytes()).hexdigest()
    receipt = {
        "schema_version": 2, "result": "passed",
        "started_at_utc": "2026-09-03T10:00:00Z", "completed_at_utc": "2026-09-03T10:05:00Z",
        "backup": {"modified_at_utc": "2026-09-03T09:00:00Z", "sha256": sha, "bytes": backup.stat().st_size},
        "isolation": {"network": "none", "published_ports": False, "host_bind_mounts": False,
                      "production_volumes": False, "ephemeral_database_volume": True},
        "integrity": {"missing_critical_tables": 0, "orphan_chunks": 0, "orphan_decision_facts": 0,
                      "orphan_decision_links": 0, "unvalidated_foreign_keys": 0, "vector_extension": True},
    }
    return backup, sha, receipt


def _restore(tmp_path, backup, sha, receipt, now=NOW):
    path = tmp_path / "fixture-recovery.json"
    raw = json.dumps(receipt).encode()
    path.write_bytes(raw)
    return validate_restore_evidence(path, hashlib.sha256(raw).hexdigest(), backup, sha, now=now)


def test_admission_import_and_no_command_are_offline(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, "-c",
        "import sys; from scripts.admit_legal_temporal_review import main; main([]); "
        "assert not any(n == 'sqlalchemy' or n.startswith('core.') for n in sys.modules)"],
        cwd=tmp_path, env={**os.environ, "PYTHONPATH": str(backend)}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert '"database_writes_allowed": false' in result.stdout


@pytest.mark.parametrize("state", ["confirm", "reject"])
def test_reviewed_admission_is_only_an_event_plan(evidence, state):
    _, manifest, texts = evidence
    plan = _admission(manifest, texts, state)
    assert plan["kind"] == "review_events_only"
    assert plan["authoritative_versions_created"] == 0
    assert plan["public_answer_routing_changed"] is False
    assert plan["admission_sha256"] == sha256_json({k: v for k, v in plan.items() if k != "admission_sha256"})


@pytest.mark.parametrize("field,value", [
    ("state", "pending"), ("state", "disagree"), ("reviewer", "Test Expert (fixture)"),
    ("reviewer", "  TEST   EXPERT (fixture)  "), ("reviewer", "Ｔｅｓｔ Expert (fixture)"),
    ("reviewer", ""), ("rationale", "short"), ("reviewed_at_utc", "2026-09-03T10:59:59Z"),
    ("reviewed_at_utc", "2026-09-04T10:00:00Z"), ("reviewed_at_utc", None),
    ("row_sha256", "c" * 64), ("row_id", []),
])
def test_independent_review_fails_closed(evidence, field, value):
    _, manifest, texts = evidence
    proposals = _validate(manifest, texts, _document(manifest, texts))
    second = _second(proposals)
    second["rows"][0][field] = value
    with pytest.raises(ReviewValidationError):
        validate_admission(proposals, second, "b" * 64, now=NOW)


@pytest.mark.parametrize("change", ["missing", "duplicate", "extra", "wrong_proposal", "blocked", "defer", "correct", "empty", "too_many"])
def test_whole_packet_and_supported_scope_required(evidence, change):
    _, manifest, texts = evidence
    proposals = _validate(manifest, texts, _document(manifest, texts))
    second = _second(proposals)
    if change == "missing":
        second["rows"] = []
    elif change == "duplicate":
        second["rows"] *= 2
    elif change == "extra":
        second["approved"] = True
    elif change == "wrong_proposal":
        second["proposal_sha256"] = "c" * 64
    elif change in {"defer", "correct", "blocked"}:
        if change == "blocked":
            proposals["proposals"][0]["evidence"]["blockers"] = ["target_source_content_drift"]
        else:
            proposals["proposals"][0]["decision"]["state"] = change
        second = _second(proposals)
    elif change == "empty":
        proposals["proposals"] = []
    else:
        proposals["proposals"] *= 101
    with pytest.raises(ReviewValidationError):
        validate_admission(proposals, second, "b" * 64, now=NOW)


def test_original_review_files_are_revalidated_not_just_self_hashes(evidence, tmp_path):
    _, manifest, texts = evidence
    path = tmp_path / "review.json"
    document = _document(manifest, texts)
    path.write_text(json.dumps(document), encoding="utf-8")
    raw_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    from legal_temporal.expert_review import validate_reviews
    pin = validate_reviews(manifest, texts, [(document, raw_sha)], now=NOW)["proposal_sha256"]
    assert load_proposals(manifest, texts, [path], pin, now=NOW)["proposals"]
    document["rows"][0]["evidence"]["effective_date"] = "2000-01-01"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ReviewValidationError, match="immutable"):
        load_proposals(manifest, texts, [path], pin, now=NOW)


def test_cli_pending_template_is_empty_and_cannot_be_overwritten(evidence, tmp_path, capsys):
    bundle, manifest, texts = evidence
    document = _document(manifest, texts, "pending")
    path = tmp_path / "pending.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    raw_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    from legal_temporal.expert_review import validate_reviews
    proposals = validate_reviews(manifest, texts, [(document, raw_sha)])
    output = tmp_path / "second.json"
    args = ["template", "--bundle", str(bundle), "--expected-manifest-sha256", manifest["manifest_sha256"],
            "--reviews", str(path), "--expected-proposal-sha256", proposals["proposal_sha256"],
            "--output", str(output)]
    assert main(args) == 0
    assert json.loads(output.read_bytes())["rows"] == []
    assert '"state": "pending"' in capsys.readouterr().out
    if os.name != "nt":
        assert output.stat().st_mode & 0o077 == 0
    with pytest.raises(ReviewValidationError, match="already exists"):
        main(args)


@pytest.mark.parametrize("pin", [None, "", "a", "A" * 64, "c" * 64])
def test_exact_pins_required(pin):
    with pytest.raises(ReviewValidationError):
        require_pin("b" * 64, pin, "fixture")


def test_restore_receipt_is_bound_to_actual_dump_and_freshness(tmp_path):
    backup, sha, receipt = _recovery_files(tmp_path)
    assert _restore(tmp_path, backup, sha, receipt)["backup_sha256"] == sha
    with pytest.raises(ReviewValidationError, match="24 hours"):
        _restore(tmp_path, backup, sha, receipt, now=NOW + timedelta(days=2))
    backup.write_bytes(b"changed")
    with pytest.raises(ReviewValidationError, match="SHA-256"):
        _restore(tmp_path, backup, sha, receipt)


@pytest.mark.parametrize("section,key,value", [
    (None, "result", "failed"), (None, "schema_version", True),
    ("isolation", "network", "infohub_default"), ("isolation", "published_ports", 0),
    ("integrity", "orphan_chunks", 1), ("integrity", "unvalidated_foreign_keys", False),
    ("integrity", "vector_extension", False), ("backup", "bytes", 1),
    ("backup", "sha256", "c" * 64), (None, "completed_at_utc", "2026-09-03T09:59:59Z"),
])
def test_bad_restore_evidence_cannot_enable_writes(tmp_path, section, key, value):
    backup, sha, receipt = _recovery_files(tmp_path)
    (receipt[section] if section else receipt)[key] = value
    with pytest.raises(ReviewValidationError):
        _restore(tmp_path, backup, sha, receipt)


def test_rollback_proof_binds_all_inputs_and_exact_count(evidence):
    _, manifest, texts = evidence
    plan = _admission(manifest, texts)
    recovery = {"backup_sha256": "c" * 64, "restore_evidence_sha256": "d" * 64}
    proof = {"contract": ADMISSION_CONTRACT, "admission_sha256": plan["admission_sha256"],
             **recovery, "scope_sha256": "e" * 64, "events_rehearsed": 1,
             "rolled_back": True, "completed_at_utc": "2026-09-03T11:45:00Z"}
    validate_rollback_proof(proof, plan, recovery, now=NOW)
    for key, value in [("backup_sha256", "f" * 64), ("rolled_back", 1),
                       ("events_rehearsed", True), ("events_rehearsed", 2),
                       ("scope_sha256", ""), ("completed_at_utc", "2026-09-01T11:45:00Z")]:
        with pytest.raises(ReviewValidationError):
            validate_rollback_proof(proof | {key: value}, plan, recovery, now=NOW)


@pytest.mark.parametrize("command", ["template", "validate", "preflight", "rehearse", "apply"])
def test_cli_requires_inputs_before_database_access(command):
    with pytest.raises(SystemExit) as exc:
        main([command])
    assert exc.value.code == 2
