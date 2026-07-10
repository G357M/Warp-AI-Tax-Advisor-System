#!/usr/bin/env python
"""One-off deep backfill of the LegislativeNews species from the infohub API.

The nightly scraper (scrape_infohub_api.py) is incremental: it stops a species
as soon as a full page yields no new documents, so news published before the
scraper's launch was never ingested. This script walks EVERY page of the
species and ingests all missing documents through the same storage pipeline
(dedup by source_url, document_type + news subtype inferred at ingest,
chunks + embeddings written as usual).

Resumable: already-ingested documents are skipped, so the script can be
re-run after an interruption and will continue where it left off.

Usage (inside infohub-backend):
    python scripts/backfill_legislative_news.py --limit 20    # sample run
    python scripts/backfill_legislative_news.py               # full backfill
    python scripts/backfill_legislative_news.py --species Bill  # other species
"""
import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import SessionLocal
from models.document import Document
from scraper.infohub_api_scraper import InfoHubAPIScraper

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logger = logging.getLogger("news_backfill")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--species", default="LegislativeNews", help="infohub species to backfill")
    parser.add_argument("--limit", type=int, default=0, help="stop after N newly ingested documents (0 = all)")
    args = parser.parse_args()

    scraper = InfoHubAPIScraper()
    new = skipped = failed = 0
    skip = 0
    total = None
    started = time.time()

    while True:
        items, total = scraper.fetch_page(args.species, skip)
        if not items:
            break
        for item in items:
            uid = item.get("uniqueKey")
            if not uid:
                continue
            source_url = f"https://infohub.rs.ge/{scraper.language}/workspace/document/{uid}"
            db = SessionLocal()
            try:
                if db.query(Document.id).filter_by(source_url=source_url).first():
                    skipped += 1
                    continue
                detail = scraper.fetch_details(uid)
                if not detail:
                    failed += 1
                    continue
                if scraper.store(detail, source_url, db):
                    new += 1
                if scraper.delay:
                    time.sleep(scraper.delay)
            except Exception as e:
                db.rollback()
                failed += 1
                logger.error(f"Error processing {uid}: {e}")
                if failed > 100 and failed > new:
                    logger.error("Too many failures — aborting.")
                    return
            finally:
                db.close()
            if args.limit and new >= args.limit:
                logger.info(f"Limit reached. new={new} skipped={skipped} failed={failed}")
                return
        elapsed = time.time() - started
        logger.info(f"[{args.species}] page skip={skip}/{total} | new={new} skipped={skipped} "
                    f"failed={failed} | {elapsed / 60:.1f} min")
        skip += scraper.page_size
        if total is not None and skip >= total:
            break

    logger.info(f"Backfill finished: +{new} new docs, {skipped} already present, {failed} failed, "
                f"of {total} total in species {args.species}")


if __name__ == "__main__":
    main()
