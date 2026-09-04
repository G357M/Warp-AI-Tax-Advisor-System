#!/usr/bin/env python3
"""Query a pinned, non-authoritative historical provision proposal by date."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from legal_temporal.publication_editions import query_provision, read_proposals


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--proposals", type=Path, required=True)
    parser.add_argument("--expected-proposal-sha256", required=True)
    parser.add_argument("--article", required=True)
    parser.add_argument("--as-of", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = read_proposals(
        args.proposals,
        expected_proposal_sha256=args.expected_proposal_sha256,
    )
    result = query_provision(report, article_ref=args.article, as_of=args.as_of)
    print(
        "MATSNE_PROVISION_HISTORY_QUERY="
        + json.dumps(result, ensure_ascii=False, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
