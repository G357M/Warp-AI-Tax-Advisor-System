#!/usr/bin/env python
"""Backfill documents written by the nightly API scraper before it normalized types.

Rows created from the raw InfoHub ``type.name`` carry Georgian labels (or the
literal "document") in ``document_type`` and a NULL ``date_published``, which
hides them from the RAG lanes filtering on canonical types. This re-runs
``infer_document_type`` over those rows and fills ``date_published`` from the
stored ``receiptDate`` metadata.

Usage (inside infohub-backend):
    python scripts/backfill_document_types.py           # dry-run: print planned changes
    python scripts/backfill_document_types.py --apply   # write changes
"""
import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import SessionLocal
from models.document import Document
from scraper.normalize import infer_document_type, parse_receipt_date

CANONICAL_TYPES = {"law", "regulation", "court_decision", "guideline", "bill", "news"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        rows = db.query(Document).filter(~Document.document_type.in_(CANONICAL_TYPES)).all()
        type_changes = Counter()
        dates_filled = 0
        for doc in rows:
            meta = doc.metadata_json or {}
            new_type = infer_document_type(doc.title or "", meta)
            if new_type != doc.document_type:
                type_changes[(doc.document_type, new_type)] += 1
                doc.document_type = new_type
            if doc.date_published is None:
                parsed = parse_receipt_date(meta.get("receiptDate"))
                if parsed:
                    doc.date_published = parsed
                    dates_filled += 1

        print(f"Rows with non-canonical document_type: {len(rows)}")
        for (old, new), n in sorted(type_changes.items(), key=lambda kv: -kv[1]):
            print(f"  {n:5d}  {old!r} -> {new!r}")
        print(f"date_published filled from receiptDate: {dates_filled}")

        if args.apply:
            db.commit()
            print("APPLIED.")
        else:
            db.rollback()
            print("DRY-RUN — nothing written (use --apply).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
