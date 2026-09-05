#!/usr/bin/env python3
"""Create a deterministic browser-capture packet for Matsne publications."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from legal_temporal.publication_capture import create_capture_packet


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--act-key", required=True)
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--title-ka", required=True)
    parser.add_argument("--first-publication", type=int, required=True)
    parser.add_argument("--last-publication", type=int, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    act = {
        "act_key": args.act_key,
        "document_id": args.document_id,
        "title_ka": args.title_ka,
        "language": "ka",
        "official_document_url": (
            f"https://matsne.gov.ge/ka/document/view/{args.document_id}"
        ),
    }
    result = create_capture_packet(
        args.output_dir,
        act,
        first_publication=args.first_publication,
        last_publication=args.last_publication,
    )
    print(
        "MATSNE_PUBLICATION_CAPTURE_PLAN="
        + json.dumps(result, ensure_ascii=False, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
