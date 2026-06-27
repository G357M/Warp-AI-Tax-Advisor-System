#!/usr/bin/env python3
"""Index normalized export corpus into chunk manifests and optionally the DB/pgvector."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from export_pipeline.corpus_indexer import CorpusIndexer  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Index normalized export corpus")
    parser.add_argument("--corpus-dir", required=True, help="Path to export corpus root")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--chunk-size", type=int)
    parser.add_argument("--overlap", type=int)
    parser.add_argument("--selected-json", help="JSON file listing normalized_json relative paths to index")
    parser.add_argument("--write-db", action="store_true", help="Upsert documents and chunks into database")
    parser.add_argument("--embed", action="store_true", help="Generate embeddings while indexing into DB")
    parser.add_argument("--force", action="store_true", help="Reindex even when file_hash matches existing DB row")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    indexer = CorpusIndexer(Path(args.corpus_dir))
    stats = indexer.index_corpus(
        limit=args.limit,
        chunk_size=args.chunk_size,
        overlap=args.overlap,
        write_db=args.write_db,
        embed=args.embed,
        force=args.force,
        selected_json=Path(args.selected_json) if args.selected_json else None,
    )
    print(json.dumps(stats.__dict__, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
