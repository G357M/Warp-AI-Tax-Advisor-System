"""Quick probe script for Scrapling-based extraction on a single URL."""
from __future__ import annotations

import argparse
import json
import sys

from scraper.scrapling_scraper import probe_url_sync


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe a URL with the Scrapling pilot extractor")
    parser.add_argument("url", help="Target URL to fetch and extract")
    parser.add_argument("--no-adaptive", action="store_true", help="Disable Scrapling adaptive parsing")
    parser.add_argument("--preview-chars", type=int, default=1000, help="Preview text length")
    args = parser.parse_args()

    result = probe_url_sync(args.url, adaptive=not args.no_adaptive)
    preview = result.get("text", "")[: args.preview_chars]
    payload = {
        "url": result.get("url"),
        "title": result.get("title"),
        "extraction_mode": result.get("extraction_mode"),
        "content_length": result.get("content_length"),
        "preview": preview,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise
