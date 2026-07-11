#!/usr/bin/env python
"""Mark bulk-imported LegislativeNews documents so the /news scope sees them.

The bulk corpus import stored documents without the ``species`` key in
``metadata``, so the /news endpoint scope
(``metadata->>'species' = 'LegislativeNews' OR document_type = 'news'``)
misses them even though they are in the DB (the deep backfill skips them as
already ingested by source_url).

This walks the LegislativeNews listing on the infohub API (uniqueKey + name +
type, no detail fetches), matches documents by source_url, and merges
``species``/``type`` into their metadata. The news subtype is set by the
same ingest rules (only when empty or rule-sourced — LLM verdicts are kept).
``document_type`` is NOT touched, so RAG lanes are unaffected.

Idempotent; dry-run by default.

Usage (inside infohub-backend):
    python scripts/repair_news_species.py            # dry-run report
    python scripts/repair_news_species.py --apply    # write
"""
import argparse
import json
import logging
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text as sa_text

from core.database import SessionLocal
from scraper.normalize import classify_news_subtype

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logger = logging.getLogger("news_species_repair")

API_BASE = "https://infohubapi.rs.ge/api"
SPECIES = "LegislativeNews"
PAGE_SIZE = 50  # the API 422s on larger take values


def fetch_page(skip: int) -> tuple:
    url = f"{API_BASE}/documents?skip={skip}&take={PAGE_SIZE}&species={SPECIES}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "InfoHubAI-Bot/1.0",
        "Accept": "application/json, text/plain, */*",
        "languagecode": "ka",
        "Referer": "https://infohub.rs.ge/",
        "Origin": "https://infohub.rs.ge",
    })
    with urllib.request.urlopen(req, timeout=45) as r:
        payload = json.loads(r.read().decode("utf-8", "replace"))
    return payload.get("data", []), (payload.get("meta") or {}).get("total", 0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry-run report)")
    args = parser.parse_args()

    # Walk the full listing: uniqueKey -> original type name.
    listing = {}
    skip = 0
    while True:
        items, total = fetch_page(skip)
        if not items:
            break
        for item in items:
            uid = item.get("uniqueKey")
            if not uid:
                continue
            t = item.get("type")
            listing[uid] = {
                "name": item.get("name") or "",
                "type": t.get("name") if isinstance(t, dict) else None,
            }
        skip += PAGE_SIZE
        if skip >= total:
            break
        time.sleep(0.3)
    logger.info(f"Listing walked: {len(listing)} of {total} {SPECIES} items")

    db = SessionLocal()
    try:
        stats = Counter()
        verdicts = Counter()
        for uid, info in listing.items():
            source_url = f"https://infohub.rs.ge/ka/workspace/document/{uid}"
            row = db.execute(sa_text("""
                SELECT id, title, metadata->>'species' AS species,
                       subtype, subtype_source
                FROM documents WHERE source_url = :u
            """), {"u": source_url}).one_or_none()
            if row is None:
                stats["not_in_db"] += 1
                continue
            needs_species = row.species != SPECIES
            meta = {"type": info["type"], "species": SPECIES}
            subtype = classify_news_subtype(row.title or info["name"], meta)
            needs_subtype = subtype and (row.subtype is None or row.subtype_source == "rule") and subtype != row.subtype
            if not needs_species and not needs_subtype:
                stats["already_ok"] += 1
                continue
            stats["updated" if args.apply else "would_update"] += 1
            if subtype:
                verdicts[subtype] += 1
            else:
                verdicts["(unmatched)"] += 1
            if not args.apply:
                continue
            db.execute(sa_text("""
                UPDATE documents
                SET metadata = (coalesce(metadata::jsonb, '{}'::jsonb)
                                || jsonb_build_object('species', :species, 'type', :type))::json
                WHERE id = :id
            """), {"id": row.id, "species": SPECIES, "type": info["type"]})
            if needs_subtype:
                db.execute(sa_text(
                    "UPDATE documents SET subtype = :s, subtype_source = 'rule' WHERE id = :id"
                ), {"id": row.id, "s": subtype})
            db.commit()

        print(f"\n{SPECIES} listing: {len(listing)} items")
        for key, n in stats.most_common():
            print(f"  {key:15s} {n}")
        print("\nSubtype verdicts among (would-be) updated:")
        for subtype, n in verdicts.most_common():
            print(f"  {subtype:20s} {n}")
        if not args.apply:
            print("\nDry-run only. Re-run with --apply to write.")
        else:
            counts = dict(db.execute(sa_text("""
                SELECT coalesce(subtype, 'general'), count(*) FROM documents
                WHERE ((metadata->>'species') = 'LegislativeNews' OR document_type = 'news')
                GROUP BY 1 ORDER BY 2 DESC
            """)).all())
            print(f"\n/news scope now: {sum(counts.values())} docs, by subtype: {counts}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
