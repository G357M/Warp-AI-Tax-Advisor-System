#!/usr/bin/env python3
"""Audit Matsne same-origin browser capture receipts without writes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from legal_temporal.browser_capture_receipts import (
    audit_browser_capture_receipts,
    compact_browser_receipt_audit,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--report", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = audit_browser_capture_receipts(
        args.plan,
        args.bundle,
        expected_plan_sha256=args.expected_plan_sha256,
    )
    if args.report:
        if args.report.exists() or args.report.is_symlink():
            raise ValueError("audit report output already exists")
        with args.report.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        try:
            args.report.chmod(0o600)
        except OSError:
            pass
    print(
        "MATSNE_BROWSER_CAPTURE_RECEIPT_AUDIT="
        + json.dumps(compact_browser_receipt_audit(report), sort_keys=True)
    )
    return 0 if report["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
