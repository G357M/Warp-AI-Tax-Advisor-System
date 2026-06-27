#!/usr/bin/env python3
"""Discover InfoHub canonical document URLs through the native JSON API."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from export_pipeline.infohub_native_api import (  # noqa: E402
    InfohubNativeApiClient,
    build_source_url,
    extract_listing_items,
    save_listing_snapshot,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover InfoHub document URLs through native API")
    parser.add_argument("--species", required=True, choices=["NewDocument", "LegislativeNews", "Bill"])
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=10)
    parser.add_argument("--output-dir", default="backend/data/source_exports_native")
    parser.add_argument("--language-code", default="ka")
    return parser.parse_args()


def load_existing_queue(queue_path: Path) -> dict[str, dict]:
    existing: dict[str, dict] = {}
    if not queue_path.exists():
        return existing
    for line in queue_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        existing[row["source_url"]] = row
    return existing


def main() -> int:
    args = parse_args()
    output_root = Path(args.output_dir)
    state_dir = output_root / "state"
    state_dir.mkdir(parents=True, exist_ok=True)

    client = InfohubNativeApiClient(language_code=args.language_code)
    skip = (args.page - 1) * args.page_size
    payload = client.get_listing(species=args.species, skip=skip, take=args.page_size)
    listing_path = save_listing_snapshot(output_root, species=args.species, page=args.page, payload=payload)

    items = extract_listing_items(payload)
    discovered = []
    for position, item in enumerate(items, start=1):
        source_url = build_source_url(item)
        discovered.append(
            {
                "source_url": source_url,
                "species": args.species,
                "page": args.page,
                "position": position,
                "api_document_id": item.get("id"),
                "api_document_key": item.get("key"),
                "listing_raw": str(listing_path.relative_to(output_root)),
                "status": "pending",
            }
        )

    queue_path = state_dir / "queue.jsonl"
    existing = load_existing_queue(queue_path)
    for item in discovered:
        existing[item["source_url"]] = item
    ordered = [existing[key] for key in sorted(existing.keys())]
    queue_path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in ordered) + "\n", encoding="utf-8")

    print(json.dumps(
        {
            "species": args.species,
            "page": args.page,
            "page_size": args.page_size,
            "listing_raw": str(listing_path.relative_to(output_root)),
            "discovered_links": len(discovered),
            "queue_size": len(ordered),
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
