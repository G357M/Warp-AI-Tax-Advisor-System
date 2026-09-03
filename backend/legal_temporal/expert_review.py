"""Offline, evidence-pinned expert review. Output is proposals, never legal truth.

No database, network, LLM or executable apply path. Human decisions cannot
replace immutable evidence or clear quarantine in the original source bundle.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from legal_temporal.backfill import (
    SOURCE_VERIFICATION_DRIFT,
    _article_pattern,
    canonical_article_ref,
    sha256_json,
    validate_bundle,
)

REVIEW_CONTRACT = "legal-temporal-expert-review-v1"
MAX_REVIEW_BYTES = 32 * 1024 * 1024
MAX_DECISIONS = 10000
STATES = frozenset({"pending", "confirm", "correct", "reject", "defer"})
CORRECTION_FIELDS = frozenset(
    {"target_legacy_document_id", "article_ref", "operation_type", "effective_date"}
)
DECISION_FIELDS = frozenset(
    {"state", "reviewer", "reviewed_at_utc", "rationale", "evidence_locator",
     "operative_quote", "effective_date_quote", "proposed_correction"}
)


class ReviewValidationError(ValueError):
    """A review input cannot be trusted; no partial result may be emitted."""


def pending_decision() -> dict[str, Any]:
    return {
        "state": "pending", "reviewer": "", "reviewed_at_utc": "",
        "rationale": "", "evidence_locator": "", "operative_quote": "",
        "effective_date_quote": "", "proposed_correction": None,
    }


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReviewValidationError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_constant(_value):
    raise ReviewValidationError("non-finite JSON value")


def read_review(path: Path) -> tuple[dict[str, Any], str]:
    if path.is_symlink() or not path.is_file():
        raise ReviewValidationError("review input must be a regular file")
    with path.open("rb") as handle:
        raw = handle.read(MAX_REVIEW_BYTES + 1)
    if not raw or len(raw) > MAX_REVIEW_BYTES:
        raise ReviewValidationError("review input exceeds byte limit or is empty")
    try:
        value = json.loads(
            raw.decode("utf-8-sig"), object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ReviewValidationError("invalid UTF-8 JSON review input") from exc
    if not isinstance(value, dict):
        raise ReviewValidationError("review input must be an object")
    return value, hashlib.sha256(raw).hexdigest()


def load_evidence(bundle: Path, expected_manifest_sha256: str):
    """Validate every source before deriving review rows or normalized text."""
    if not re.fullmatch(r"[0-9a-f]{64}", expected_manifest_sha256):
        raise ReviewValidationError("a pinned manifest SHA-256 is required")
    texts: dict[str, str] = {}
    manifest = validate_bundle(
        bundle, expected_manifest_sha256=expected_manifest_sha256,
        normalized_texts=texts,
    )
    return manifest, texts


def _source_evidence(source, texts):
    doc_id = source["legacy_document_id"]
    return {
        key: source.get(key) for key in (
            "legacy_document_id", "title", "document_number", "workspace_url",
            "api_url", "content_sha256", "verification_mode", "captured_at_utc",
            "legacy_normalizer", "file",
        )
    } | {
        "normalized_text_file": f"sources/{doc_id}.txt",
        "normalized_text_sha256": hashlib.sha256(texts[doc_id].encode()).hexdigest(),
    }


def _contexts(text: str, article_ref: str) -> list[str]:
    canonical = canonical_article_ref(article_ref)
    if canonical is None:
        return []
    # Navigation hints only, NOT verified subdivision/replacement text.
    result = []
    for match in _article_pattern(canonical).finditer(text):
        result.append(text[max(0, match.start() - 250):match.end() + 650])
        if len(result) == 3:
            break
    return result


def build_rows(manifest: dict, texts: dict[str, str]) -> list[dict]:
    sources = {s["legacy_document_id"]: s for s in manifest["sources"]}
    evidence_sources = {key: _source_evidence(s, texts) for key, s in sources.items()}
    rows = []
    seen = set()
    for amendment in manifest["amendments"]:
        source_id = amendment["amendment_legacy_document_id"]
        target_id = amendment.get("target_legacy_document_id")
        for candidate in amendment["candidates"] or [None]:
            candidate = candidate or {}
            classification = candidate.get("classification") or {
                "state": "row_issue", "reason": "no_candidate_items",
            }
            blockers = set(amendment.get("row_issues") or [])
            if not target_id:
                blockers.add("missing_target")
            if not amendment.get("effective_date"):
                blockers.add("missing_effective_date")
            for role, doc_id in (("amendment", source_id), ("target", target_id)):
                if doc_id and sources[doc_id]["verification_mode"] == SOURCE_VERIFICATION_DRIFT:
                    blockers.add(f"{role}_source_content_drift")
            if classification["state"] != "operation_candidate":
                blockers.add("not_operation_candidate")
            row_id = "LTR-" + sha256_json({
                "contract": REVIEW_CONTRACT,
                "manifest_sha256": manifest["manifest_sha256"],
                "amendment_id": amendment["legacy_law_amendment_id"],
                "item_index": candidate.get("item_index"),
            })
            if row_id in seen:
                raise ReviewValidationError("duplicate review row identity")
            seen.add(row_id)
            lane = (
                "source_reconciliation" if any("drift" in b for b in blockers)
                else "candidate_resolution" if blockers else "expert_confirmation"
            )
            evidence = {
                "legacy_law_amendment_id": amendment["legacy_law_amendment_id"],
                "candidate_fingerprint": candidate.get("candidate_fingerprint"),
                "item_index": candidate.get("item_index"),
                "article_ref": candidate.get("article_ref"),
                "legacy_action": candidate.get("legacy_action"),
                "adoption_date": amendment.get("adoption_date"),
                "effective_date": amendment.get("effective_date"),
                "classification": classification,
                "blockers": sorted(blockers), "lane": lane,
                "amendment_source": evidence_sources[source_id],
                "target_source": evidence_sources.get(target_id),
                "navigation_excerpts": _contexts(texts[source_id], candidate.get("article_ref") or ""),
            }
            rows.append({"row_id": row_id, "evidence": evidence, "decision": pending_decision()})
    if len(rows) != manifest["summary"]["expert_review_rows"]:
        raise ReviewValidationError("review coverage does not match the source bundle")
    return sorted(rows, key=lambda r: (
        (r["evidence"]["target_source"] or {}).get("legacy_document_id", ""),
        r["evidence"]["lane"], r["evidence"]["effective_date"] or "",
        r["evidence"]["legacy_law_amendment_id"],
        r["evidence"]["item_index"] if r["evidence"]["item_index"] is not None else -1,
    ))


def review_document(manifest: dict, rows: list[dict]) -> dict:
    return {"contract": REVIEW_CONTRACT, "manifest_sha256": manifest["manifest_sha256"], "rows": rows}


def _text(value: Any, field: str, minimum: int, maximum: int) -> str:
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
        raise ReviewValidationError(f"{field}: expected {minimum}..{maximum} characters")
    return value.strip()


def _utc(value: str, *, now: datetime) -> datetime:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|\+00:00)", value):
        raise ReviewValidationError("reviewed_at_utc: use YYYY-MM-DDTHH:MM:SSZ")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReviewValidationError("invalid reviewed_at_utc") from exc
    if result > now + timedelta(minutes=5):
        raise ReviewValidationError("reviewed_at_utc is in the future")
    return result


def _validate_decision(decision: dict, evidence: dict, texts: dict, source_ids: set, now: datetime):
    if not isinstance(decision, dict) or set(decision) != DECISION_FIELDS:
        raise ReviewValidationError("unexpected or missing decision fields")
    state = decision.get("state")
    if not isinstance(state, str) or state not in STATES:
        raise ReviewValidationError("unknown review state")
    if state == "pending":
        if decision != pending_decision():
            raise ReviewValidationError("pending row contains a decision; explicitly set its state")
        return
    _text(decision["reviewer"], "reviewer", 3, 255)
    _text(decision["rationale"], "rationale", 20, 6000)
    reviewed_at = _utc(_text(decision["reviewed_at_utc"], "reviewed_at_utc", 20, 25), now=now)
    captures = [evidence["amendment_source"]["captured_at_utc"]]
    if evidence["target_source"]:
        captures.append(evidence["target_source"]["captured_at_utc"])
    if any(reviewed_at < datetime.fromisoformat(c.replace("Z", "+00:00")) for c in captures):
        raise ReviewValidationError("review precedes its source capture")
    for field in ("evidence_locator", "operative_quote", "effective_date_quote"):
        _text(decision[field], field, 0, 12000)
    if state == "confirm" and evidence["blockers"]:
        raise ReviewValidationError("blocked candidate cannot be confirmed; correct, reject or defer")
    correction = decision["proposed_correction"]
    if state == "correct":
        if not isinstance(correction, dict) or set(correction) != CORRECTION_FIELDS:
            raise ReviewValidationError("correction requires exact target, article, operation and date fields")
        target = correction["target_legacy_document_id"]
        if not isinstance(target, str) or target not in source_ids:
            raise ReviewValidationError("correction target is not in the pinned source bundle")
        ref = correction["article_ref"]
        if not isinstance(ref, str) or not ref or canonical_article_ref(ref) != ref:
            raise ReviewValidationError("correction article reference must be canonical")
        if not isinstance(correction["operation_type"], str) or correction["operation_type"] not in {"add", "replace", "repeal"}:
            raise ReviewValidationError("invalid correction operation type")
        value = correction["effective_date"]
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ReviewValidationError("correction effective date must be YYYY-MM-DD")
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ReviewValidationError("invalid correction effective date") from exc
    elif correction is not None:
        raise ReviewValidationError("only correct decisions may contain proposed_correction")
    source_text = texts[evidence["amendment_source"]["legacy_document_id"]]
    for field in ("operative_quote", "effective_date_quote"):
        quote = decision[field]
        if state in {"confirm", "correct"}:
            _text(quote, field, 20, 12000)
        if quote and quote not in source_text:
            raise ReviewValidationError(f"{field} does not occur verbatim in the archived amendment")
    if state in {"confirm", "correct", "reject"}:
        _text(decision["evidence_locator"], "evidence_locator", 8, 2000)


def validate_reviews(manifest: dict, texts: dict, inputs: list[tuple[dict, str]], *, now=None) -> dict:
    """Combine disjoint partial batches; never produce executable operations.

    Quote membership cannot prove legal interpretation or date applicability.
    A valid confirm is an expert assertion still requiring independent review.
    """
    now = now or datetime.now(UTC)
    expected = {row["row_id"]: row for row in build_rows(manifest, texts)}
    source_ids = set(texts)
    seen = set()
    decisions = []
    errors = []
    counts = Counter()
    if not inputs or len(inputs) > 500:
        raise ReviewValidationError("provide 1..500 review batches")
    for document, _input_sha in inputs:
        if set(document) != {"contract", "manifest_sha256", "rows"}:
            raise ReviewValidationError("unexpected or missing review document fields")
        if document["contract"] != REVIEW_CONTRACT or document["manifest_sha256"] != manifest["manifest_sha256"]:
            raise ReviewValidationError("review contract or source manifest pin mismatch")
        rows = document["rows"]
        if not isinstance(rows, list) or not rows or len(rows) > MAX_DECISIONS:
            raise ReviewValidationError("review batch must contain 1..10000 rows")
        for row in rows:
            if not isinstance(row, dict) or set(row) != {"row_id", "evidence", "decision"}:
                raise ReviewValidationError("unexpected or missing review row fields")
            row_id = row["row_id"]
            if not isinstance(row_id, str) or row_id not in expected:
                raise ReviewValidationError("unknown review row")
            if row_id in seen:
                raise ReviewValidationError("duplicate/overlapping review row; use disjoint batches")
            seen.add(row_id)
            if sha256_json(row["evidence"]) != sha256_json(expected[row_id]["evidence"]):
                raise ReviewValidationError("immutable evidence was changed")
            try:
                _validate_decision(row["decision"], row["evidence"], texts, source_ids, now)
            except ReviewValidationError as exc:
                errors.append({"row_id": row_id, "error": str(exc)})
                continue
            state = row["decision"]["state"]
            counts[state] += 1
            if state != "pending":
                decisions.append(row)
    result = {
        "contract": REVIEW_CONTRACT, "kind": "non_executable_expert_proposals",
        "manifest_sha256": manifest["manifest_sha256"],
        "input_sha256": sorted(input_sha for _, input_sha in inputs),
        "total_review_rows": len(expected), "submitted_rows": len(seen),
        "not_submitted_rows": len(expected) - len(seen),
        "states": dict(sorted(counts.items())),
        "errors": errors, "error_count": len(errors),
        "database_writes_allowed": False, "public_answer_routing_changed": False,
        "authoritative_versions_created": 0,
        "requires_independent_review_and_reconstruction": True,
        "proposals": sorted(decisions, key=lambda r: r["row_id"]) if not errors else [],
    }
    result["proposal_sha256"] = sha256_json(result)
    return result
