#!/usr/bin/env python
"""Reclassify guidance content stuck in ``news`` as ``guideline``.

Methodical instructions (მეთოდური მითითება) and the situational-guides
registry (სიტუაციური სახელმძღვანელოების რეესტრი) were ingested through
LegislativeNews and typed ``news``, hiding them from the guideline RAG lane
and the /guides registry endpoint. ``scraper/normalize.py`` now routes such
titles to ``guideline`` for future ingest; this script fixes existing rows.

Usage (inside infohub-backend):
    python scripts/reclassify_guidance_docs.py           # dry-run: list affected rows
    python scripts/reclassify_guidance_docs.py --apply   # write changes
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import or_

from core.database import SessionLocal
from models.document import Document


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        rows = (
            db.query(Document)
            .filter(
                Document.document_type == "news",
                or_(
                    Document.title.ilike("%მეთოდური%"),
                    Document.title.ilike("%სიტუაციური სახელმძღვანელო%"),
                ),
            )
            .all()
        )
        for doc in rows:
            print(f"news -> guideline | {doc.id} | {doc.title[:90]}")
            if args.apply:
                doc.document_type = "guideline"
                doc.updated_at = datetime.utcnow()
        if args.apply:
            db.commit()
            print(f"Updated {len(rows)} documents.")
        else:
            print(f"Dry-run: {len(rows)} documents would be updated. Re-run with --apply.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
