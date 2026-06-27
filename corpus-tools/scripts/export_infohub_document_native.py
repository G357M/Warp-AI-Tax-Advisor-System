#!/usr/bin/env python3
"""Export a single InfoHub document through the native JSON API."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from export_pipeline.infohub_exporter import InfohubNormalizer  # noqa: E402
from export_pipeline.infohub_native_api import (  # noqa: E402
    InfohubNativeApiClient,
    build_source_url,
    native_detail_to_raw_payload,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export one InfoHub document through native API")
    parser.add_argument("--document-id", type=int, required=True)
    parser.add_argument("--source-url", help="Canonical public source URL from listing item")
    parser.add_argument("--output-dir", default="backend/data/source_exports_native")
    parser.add_argument("--species")
    parser.add_argument("--listing-page", type=int)
    parser.add_argument("--listing-position", type=int)
    parser.add_argument("--language-code", default="ka")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    client = InfohubNativeApiClient(language_code=args.language_code)
    detail = client.get_document_details(args.document_id)
    source_url = args.source_url or build_source_url(detail)
    raw_payload = native_detail_to_raw_payload(detail, source_url=source_url)
    normalizer = InfohubNormalizer(Path(args.output_dir))
    result = normalizer.export_document(
        source_url,
        raw_payload,
        method="native-api",
        listing_species=args.species or detail.get("species"),
        listing_page=args.listing_page,
        listing_position=args.listing_position,
    )
    print(json.dumps(result.to_json_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
