"""Offline admission contract for independently reviewed temporal candidates.

Hashes bind operator-reviewed files; they are not identity authentication or
digital signatures. Nothing in this module connects to a database.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
from pathlib import Path
import re
import unicodedata

from legal_temporal.backfill import sha256_json
from legal_temporal.expert_review import (
    ReviewValidationError, _text, _utc, read_review, validate_reviews,
)

ADMISSION_CONTRACT = "legal-temporal-review-admission-v1"
MAX_ADMISSIONS = 100


def require_pin(actual, expected, label):
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ReviewValidationError(f"{label}: exact lowercase SHA-256 is required")
    if actual != expected:
        raise ReviewValidationError(f"{label}: SHA-256 mismatch")


def load_proposals(manifest, texts, paths, expected_sha256, *, now=None):
    if not 1 <= len(paths) <= 500:
        raise ReviewValidationError("provide 1..500 original review batches")
    if sum(p.stat().st_size for p in paths) > 128 * 1024 * 1024:
        raise ReviewValidationError("combined review inputs exceed 128 MiB")
    result = validate_reviews(manifest, texts, [read_review(p) for p in paths], now=now)
    if result["errors"]:
        raise ReviewValidationError("original review validation failed; no admission allowed")
    require_pin(result["proposal_sha256"], expected_sha256, "proposal")
    return result


def second_review_template(proposals):
    # Empty/pending input is not turned into a fabricated approval.
    return {
        "contract": ADMISSION_CONTRACT,
        "proposal_sha256": proposals["proposal_sha256"],
        "rows": [{
            "row_id": row["row_id"], "row_sha256": sha256_json(row),
            "state": "pending", "reviewer": "", "reviewed_at_utc": "",
            "rationale": "",
        } for row in proposals["proposals"]],
    }


def _identity(name):
    return " ".join(unicodedata.normalize("NFKC", name).casefold().split())


def validate_admission(proposals, second, second_sha256, *, now=None):
    now = now or datetime.now(UTC)
    rows = proposals["proposals"]
    if not 1 <= len(rows) <= MAX_ADMISSIONS:
        raise ReviewValidationError("admission requires 1..100 non-pending proposals")
    if set(second) != {"contract", "proposal_sha256", "rows"}:
        raise ReviewValidationError("unexpected independent review fields")
    if second["contract"] != ADMISSION_CONTRACT:
        raise ReviewValidationError("independent review contract mismatch")
    require_pin(second["proposal_sha256"], proposals["proposal_sha256"], "independent review proposal")
    if not isinstance(second["rows"], list) or len(second["rows"]) != len(rows):
        raise ReviewValidationError("independent review must cover exactly every proposal")
    expected = {row["row_id"]: row for row in rows}
    approved = {}
    for review in second["rows"]:
        if not isinstance(review, dict) or set(review) != {
            "row_id", "row_sha256", "state", "reviewer", "reviewed_at_utc", "rationale",
        }:
            raise ReviewValidationError("unexpected independent review row fields")
        row_id = review["row_id"]
        if not isinstance(row_id, str) or row_id not in expected or row_id in approved:
            raise ReviewValidationError("unknown or duplicate independent review row")
        row = expected[row_id]
        require_pin(review["row_sha256"], sha256_json(row), "independent review row")
        if review["state"] != "agree":
            raise ReviewValidationError("every independent decision must explicitly agree")
        name = _text(review["reviewer"], "second reviewer", 3, 255)
        if _identity(name) == _identity(row["decision"]["reviewer"]):
            raise ReviewValidationError("a distinct independent reviewer is required")
        _text(review["rationale"], "second rationale", 20, 6000)
        reviewed = _utc(_text(review["reviewed_at_utc"], "second review time", 20, 25), now=now)
        if reviewed < _utc(row["decision"]["reviewed_at_utc"], now=now):
            raise ReviewValidationError("independent review precedes the first decision")
        if row["decision"]["state"] not in {"confirm", "reject"} or row["evidence"]["blockers"]:
            raise ReviewValidationError("only unblocked confirm/reject operation proposals are importable; corrections need reconstruction")
        approved[row_id] = row | {"independent_review": review}
    plan = {
        "contract": ADMISSION_CONTRACT, "kind": "review_events_only",
        "manifest_sha256": proposals["manifest_sha256"],
        "proposal_sha256": proposals["proposal_sha256"],
        "independent_review_sha256": second_sha256,
        "rows": [approved[key] for key in sorted(approved)],
        "authoritative_versions_created": 0, "public_answer_routing_changed": False,
    }
    plan["admission_sha256"] = sha256_json(plan)
    return plan


def validate_restore_evidence(path: Path, expected_sha256: str, backup: Path,
                              expected_backup_sha256: str, *, now=None):
    """Check the existing isolated restore-drill receipt and the actual dump.

    This is operator evidence, not cryptographic proof of restore execution.
    The rehearsal separately binds the restored temporal rows to production.
    """
    now = now or datetime.now(UTC)
    receipt, raw_sha = read_review(path)
    require_pin(raw_sha, expected_sha256, "restore evidence")
    if type(receipt.get("schema_version")) is not int or receipt["schema_version"] != 2 or receipt.get("result") != "passed":
        raise ReviewValidationError("successful restore-drill v2 evidence is required")
    if any(not isinstance(receipt.get(key), dict) for key in ("backup", "isolation", "integrity")):
        raise ReviewValidationError("invalid restore evidence sections")
    isolation = receipt.get("isolation", {})
    for key, value in {"network": "none", "published_ports": False,
                       "host_bind_mounts": False, "production_volumes": False,
                       "ephemeral_database_volume": True}.items():
        if type(isolation.get(key)) is not type(value) or isolation[key] != value:
            raise ReviewValidationError("restore evidence isolation mismatch")
    integrity = receipt.get("integrity", {})
    for key in ("missing_critical_tables", "orphan_chunks", "orphan_decision_facts",
                "orphan_decision_links", "unvalidated_foreign_keys"):
        if type(integrity.get(key)) is not int or integrity[key] != 0:
            raise ReviewValidationError("restore evidence integrity failure")
    if integrity.get("vector_extension") is not True:
        raise ReviewValidationError("restore evidence lacks vector extension")
    dates = []
    for value in (receipt.get("backup", {}).get("modified_at_utc"),
                  receipt.get("started_at_utc"), receipt.get("completed_at_utc")):
        checked = _utc(_text(value, "restore timestamp", 20, 25), now=now)
        if checked < now - timedelta(hours=24):
            raise ReviewValidationError("backup and restore evidence must be less than 24 hours old")
        dates.append(checked)
    if dates != sorted(dates):
        raise ReviewValidationError("restore evidence timestamps are out of order")
    if backup.is_symlink() or not backup.is_file():
        raise ReviewValidationError("backup must be a regular file")
    digest = hashlib.sha256()
    length = 0
    with backup.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            length += len(chunk)
    require_pin(digest.hexdigest(), expected_backup_sha256, "backup")
    require_pin(receipt["backup"].get("sha256"), expected_backup_sha256, "restored backup")
    if not length or type(receipt["backup"].get("bytes")) is not int or receipt["backup"]["bytes"] != length:
        raise ReviewValidationError("restored backup size mismatch")
    return {"restore_evidence_sha256": raw_sha, "backup_sha256": expected_backup_sha256}


def validate_rollback_proof(proof, plan, recovery, *, now=None):
    now = now or datetime.now(UTC)
    if not isinstance(proof, dict) or set(proof) != {"contract", "admission_sha256", "restore_evidence_sha256",
                      "backup_sha256", "scope_sha256", "events_rehearsed",
                      "rolled_back", "completed_at_utc"}:
        raise ReviewValidationError("unexpected rollback proof fields")
    for key, value in {"contract": ADMISSION_CONTRACT,
                       "admission_sha256": plan["admission_sha256"], **recovery}.items():
        if proof[key] != value:
            raise ReviewValidationError("rollback proof pin mismatch")
    require_pin(proof["scope_sha256"], proof["scope_sha256"], "rollback scope")
    if proof["rolled_back"] is not True or type(proof["events_rehearsed"]) is not int or proof["events_rehearsed"] != len(plan["rows"]):
        raise ReviewValidationError("rollback proof must cover every event")
    at = _utc(_text(proof["completed_at_utc"], "rollback timestamp", 20, 25), now=now)
    if at < now - timedelta(hours=24):
        raise ReviewValidationError("rollback proof is older than 24 hours")
