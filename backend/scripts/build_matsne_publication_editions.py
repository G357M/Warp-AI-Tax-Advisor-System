#!/usr/bin/env python3
"""Build non-executable historical provision proposals from captured Matsne editions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from legal_temporal.publication_editions import build_bundle_proposals, summarize


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify an offline Matsne publication-edition evidence bundle and build "
            "non-executable provision-version proposals."
        )
    )
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = build_bundle_proposals(
        args.bundle,
        args.output,
        expected_manifest_sha256=args.expected_manifest_sha256,
    )
    print(
        "MATSNE_PUBLICATION_EDITION_BUILD="
        + json.dumps(summarize(result), ensure_ascii=True, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
