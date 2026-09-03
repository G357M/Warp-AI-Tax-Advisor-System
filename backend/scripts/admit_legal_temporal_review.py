#!/usr/bin/env python3
"""Admit independently reviewed operation decisions, never historical legal text.

Default: offline safety plan. Database commands are explicit. Rehearsal must
target an isolated restored copy using its normally configured DATABASE_URL.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from legal_temporal.backfill import BackfillValidationError
from legal_temporal.expert_review import ReviewValidationError, load_evidence, read_review
from legal_temporal.review_admission import (
    ADMISSION_CONTRACT, load_proposals, require_pin, second_review_template,
    validate_admission, validate_restore_evidence, validate_rollback_proof,
)
from scripts.review_legal_temporal import _check_new_output, _json, _write_new


def safety_plan():
    return {
        "contract": ADMISSION_CONTRACT, "database_calls_allowed": False,
        "database_writes_allowed": False, "public_answer_routing_changed": False,
        "authoritative_versions_created": 0,
        "commands": ["template", "validate", "preflight", "rehearse", "apply"],
        "human_identity_authenticated": False,
        "apply_requires": ["original_sources_and_reviews", "independent_review",
                           "exact_admission_pin_and_event_count", "fresh_restored_backup",
                           "hash_pinned_rollback_rehearsal", "unchanged_database_scope"],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=safety_plan()["commands"])
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--expected-manifest-sha256")
    parser.add_argument("--reviews", nargs="+", type=Path)
    parser.add_argument("--expected-proposal-sha256")
    parser.add_argument("--independent-review", type=Path)
    parser.add_argument("--expected-independent-review-sha256")
    parser.add_argument("--expected-admission-sha256")
    parser.add_argument("--max-events", type=int, default=0)
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--expected-backup-sha256")
    parser.add_argument("--restore-evidence", type=Path)
    parser.add_argument("--expected-restore-evidence-sha256")
    parser.add_argument("--rollback-proof", type=Path)
    parser.add_argument("--expected-rollback-proof-sha256")
    parser.add_argument("--isolated-restore", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.command is None:
        print("LEGAL_TEMPORAL_ADMISSION_PLAN=" + json.dumps(safety_plan(), sort_keys=True))
        return 0
    if not args.bundle or not args.expected_manifest_sha256 or not args.reviews or not args.expected_proposal_sha256:
        parser.error("all commands require pinned source bundle, original reviews and proposal SHA-256")
    if args.command in {"template", "rehearse"} and not args.output:
        parser.error("template/rehearse requires a new --output file")
    if args.command == "apply" and args.output:
        parser.error("apply reports to stdout; use the database receipt to recover uncertain outcomes")
    if args.output:
        _check_new_output(args.bundle, args.output)
    if args.command != "template" and (not args.independent_review or not args.expected_independent_review_sha256):
        parser.error("independent review and its exact SHA-256 are required")
    if args.command in {"rehearse", "apply"}:
        if not all((args.expected_admission_sha256, args.backup, args.expected_backup_sha256,
                    args.restore_evidence, args.expected_restore_evidence_sha256)):
            parser.error("rehearse/apply requires admission pin and pinned backup/restore evidence")
    if args.command == "rehearse" and not args.isolated_restore:
        parser.error("rehearse requires --isolated-restore; configure the restored database, never production")
    if args.command == "apply" and (not args.rollback_proof or not args.expected_rollback_proof_sha256):
        parser.error("apply requires hash-pinned --rollback-proof")
    manifest, texts = load_evidence(args.bundle, args.expected_manifest_sha256)
    proposals = load_proposals(manifest, texts, args.reviews, args.expected_proposal_sha256)
    if args.command == "template":
        output = second_review_template(proposals)
        digest = _write_new(args.output, _json(output))
        report = {"rows": len(output["rows"]), "state": "pending", "output_sha256": digest}
    else:
        second, digest = read_review(args.independent_review)
        require_pin(digest, args.expected_independent_review_sha256, "independent review")
        plan = validate_admission(proposals, second, digest)
        if args.command == "validate":
            report = {k: v for k, v in plan.items() if k != "rows"}
            report.update({"events": len(plan["rows"]), "database_calls_allowed": False,
                           "database_writes_allowed": False})
        else:
            recovery, proof = None, None
            if args.command in {"rehearse", "apply"}:
                require_pin(plan["admission_sha256"], args.expected_admission_sha256, "admission")
                recovery = validate_restore_evidence(
                    args.restore_evidence, args.expected_restore_evidence_sha256,
                    args.backup, args.expected_backup_sha256,
                )
            if args.command == "apply":
                proof, digest = read_review(args.rollback_proof)
                require_pin(digest, args.expected_rollback_proof_sha256, "rollback proof")
                validate_rollback_proof(proof, plan, recovery)
            # Offline validation finishes before importing settings or opening a DB.
            from core.database import SessionLocal
            from legal_temporal.review_importer import execute_admission
            from sqlalchemy.exc import SQLAlchemyError
            try:
                report = execute_admission(
                    SessionLocal, manifest, texts, plan, mode=args.command,
                    max_events=args.max_events, recovery=recovery, rollback_proof=proof,
                )
            except SQLAlchemyError:
                # Do not print SQL parameters containing quotes/reviewer identity,
                # connection details, or claim rollback after an uncertain commit.
                raise ReviewValidationError(
                    "database command failed or commit outcome is uncertain; run read-only preflight before retrying"
                ) from None
        if args.output:
            _write_new(args.output, _json(report))
    print("LEGAL_TEMPORAL_ADMISSION=" + json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BackfillValidationError, ReviewValidationError, OSError) as exc:
        print(f"LEGAL_TEMPORAL_ADMISSION_ERROR={exc}", file=sys.stderr)
        raise SystemExit(1)
