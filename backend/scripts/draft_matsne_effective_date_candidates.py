#!/usr/bin/env python3
"""Draft reviewable effective-date metadata from exact Matsne page hints."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from legal_temporal.effective_date_candidates import draft_effective_date_candidates


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--output-metadata", type=Path, required=True)
    parser.add_argument("--report-output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = draft_effective_date_candidates(
        args.plan,
        args.metadata,
        args.bundle,
        expected_plan_sha256=args.expected_plan_sha256,
        output_metadata=args.output_metadata,
        report_output=args.report_output,
    )
    print(
        "MATSNE_EFFECTIVE_DATE_CANDIDATES="
        + json.dumps(
            {
                **report["summary"],
                "complete": report["complete"],
                "report_sha256": report["report_sha256"],
                "report_file_sha256": report["report_file_sha256"],
                "output_metadata_sha256": report["output_metadata_sha256"],
                "database_writes_allowed": False,
                "public_answer_routing_changed": False,
                "expert_approval_required": True,
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0 if report["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
