#!/usr/bin/env python3
"""Run a small export-first pilot against the native InfoHub API."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from export_pipeline.infohub_exporter import InfohubNormalizer  # noqa: E402
from export_pipeline.infohub_native_api import (  # noqa: E402
    InfohubNativeApiClient,
    build_source_url,
    extract_listing_items,
    native_detail_to_raw_payload,
    save_listing_snapshot,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pilot export through native InfoHub API")
    parser.add_argument("--species", required=True, choices=["NewDocument", "LegislativeNews", "Bill"])
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=10)
    parser.add_argument("--count", type=int, default=5, help="How many documents from the listing to export")
    parser.add_argument("--output-dir", default="backend/data/source_exports_native")
    parser.add_argument("--language-code", default="ka")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    client = InfohubNativeApiClient(language_code=args.language_code)
    output_root = Path(args.output_dir)
    normalizer = InfohubNormalizer(output_root)

    skip = (args.page - 1) * args.page_size
    listing_payload = client.get_listing(species=args.species, skip=skip, take=args.page_size)
    listing_path = save_listing_snapshot(output_root, species=args.species, page=args.page, payload=listing_payload)
    items = extract_listing_items(listing_payload)

    exported = []
    for position, item in enumerate(items[: args.count], start=1):
        detail = client.get_document_details(item["id"])
        source_url = build_source_url(item)
        raw_payload = native_detail_to_raw_payload(detail, source_url=source_url)
        result = normalizer.export_document(
            source_url,
            raw_payload,
            method="native-api",
            listing_species=args.species,
            listing_page=args.page,
            listing_position=position,
        )
        exported.append(
            {
                "id": result.id,
                "title": result.title,
                "source_url": result.source_url,
                "normalized_json": result.storage.normalized_json,
                "normalized_md": result.storage.normalized_md,
            }
        )

    print(json.dumps(
        {
            "species": args.species,
            "page": args.page,
            "page_size": args.page_size,
            "count_requested": args.count,
            "count_exported": len(exported),
            "listing_raw": str(listing_path.relative_to(output_root)),
            "documents": exported,
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
