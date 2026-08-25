#!/usr/bin/env python
"""
Nightly scraper runner: populate the vector DB from the infohub.rs.ge JSON API.

Usage:
    python scripts/scrape_infohub_api.py --max-docs 200
    python scripts/scrape_infohub_api.py --species NewDocument --language ka --max-docs 50
"""
import sys
import logging
import argparse
import json
import os
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import SessionLocal
from scraper.infohub_api_scraper import InfoHubAPIScraper, SPECIES

LOG_FILE = Path(__file__).parent.parent / "logs" / "scraper.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(str(LOG_FILE)), logging.StreamHandler()],
)
# the API scraper logs are what we care about; quiet SQLAlchemy chatter
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def _active_embedding_column() -> str:
    """Return the fixed pgvector column selected by the runtime."""
    use_v2 = (os.getenv("INFOHUB_EMBEDDING_V2") or "").strip() == "1"
    return "embedding_v2" if use_v2 else "embedding"


def _get_vector_count() -> int:
    """Count populated vectors without importing the eager ``rag`` package."""
    column = _active_embedding_column()
    assert column in ("embedding", "embedding_v2")
    db = SessionLocal()
    try:
        result = db.execute(
            text(f"SELECT COUNT(*) FROM document_chunks WHERE {column} IS NOT NULL")
        )
        return int(result.scalar() or 0)
    except Exception as error:
        logger.warning("Could not read vector count: %s", error)
        return 0
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Scrape infohub.rs.ge via its JSON API")
    parser.add_argument("--max-docs", type=int, default=200, help="Max NEW documents to ingest this run")
    parser.add_argument("--species", choices=SPECIES, help="Limit to one species (default: all)")
    parser.add_argument("--language", default="ka", choices=["ka", "ru", "en"], help="languagecode")
    parser.add_argument("--page-size", type=int, default=50)
    args = parser.parse_args()

    before = _get_vector_count()
    logger.info("=" * 60)
    logger.info(f"InfoHub API scrape start | lang={args.language} | max_docs={args.max_docs}")
    logger.info(f"Vector store count before: {before}")

    scraper = InfoHubAPIScraper(language=args.language, page_size=args.page_size)
    result = scraper.scrape(
        species_list=[args.species] if args.species else None,
        max_docs=args.max_docs,
    )

    after = _get_vector_count()
    logger.info("=" * 60)
    logger.info(f"Done. New documents: {result['documents_scraped']} | pages: {result['pages_visited']}")
    logger.info(f"Vector store count after: {after} (was {before})")
    print(
        "INFOHUB_INGEST_SUMMARY="
        + json.dumps(
            {
                "documents_scraped": result["documents_scraped"],
                "pages_visited": result["pages_visited"],
                "species": result["species"],
            },
            sort_keys=True,
        )
    )
    print(f"\n✅ Scrape complete: +{result['documents_scraped']} new docs, vector count {before} -> {after}")


if __name__ == "__main__":
    main()
