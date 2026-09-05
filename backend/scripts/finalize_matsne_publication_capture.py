#!/usr/bin/env python3
"""Finalize a complete capture packet into a pinned edition manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from legal_temporal.publication_capture import finalize_capture_packet


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--manifest-output", type=Path, required=True)
    parser.add_argument("--admission-output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest, admission = finalize_capture_packet(
        args.plan,
        args.metadata,
        args.bundle,
        expected_plan_sha256=args.expected_plan_sha256,
        manifest_output=args.manifest_output,
        admission_output=args.admission_output,
    )
    manifest_sha = hashlib.sha256(
        (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    ).hexdigest()
    print(
        "MATSNE_PUBLICATION_CAPTURE_FINALIZE="
        + json.dumps(
            {
                "manifest_sha256": manifest_sha,
                "admission_sha256": admission["admission_sha256"],
                "publication_count": len(manifest["editions"]),
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
