#!/usr/bin/env python3
"""Apply an explicit expert attestation to a pinned complete candidate set."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from legal_temporal.effective_date_candidates import approve_effective_date_candidates


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--candidate-metadata", type=Path, required=True)
    parser.add_argument("--candidate-report", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--expected-report-file-sha256", required=True)
    parser.add_argument("--approval-phrase", required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--reviewed-at-utc", required=True)
    parser.add_argument("--rationale", required=True)
    parser.add_argument("--output-metadata", type=Path, required=True)
    parser.add_argument("--approval-output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    approval = approve_effective_date_candidates(
        args.plan,
        args.candidate_metadata,
        args.candidate_report,
        args.bundle,
        expected_plan_sha256=args.expected_plan_sha256,
        expected_report_file_sha256=args.expected_report_file_sha256,
        approval_phrase=args.approval_phrase,
        reviewer=args.reviewer,
        reviewed_at_utc=args.reviewed_at_utc,
        rationale=args.rationale,
        output_metadata=args.output_metadata,
        approval_output=args.approval_output,
    )
    print(
        "MATSNE_EFFECTIVE_DATE_APPROVAL="
        + json.dumps(
            {
                "approved_editions": approval["approved_editions"],
                "pending_editions": approval["pending_editions"],
                "complete": approval["complete"],
                "confirmed_metadata_sha256": approval[
                    "confirmed_metadata_sha256"
                ],
                "approval_sha256": approval["approval_sha256"],
                "approval_file_sha256": approval["approval_file_sha256"],
                "database_writes_allowed": False,
                "public_answer_routing_changed": False,
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
