#!/usr/bin/env python
"""Tag CJEU decision translations with subtype='cjeu_practice' (П3 follow-up).

Two passes, idempotent, dry-run by default:
  1. Walk the donor listing (q-search for the CJEU type) and tag our documents
     by source_url, merging the donor type/baseType into metadata.
  2. Catch old bulk-imported copies the donor no longer lists: documents whose
     full_text carries the distinctive CJEU header phrase.

Usage (inside infohub-backend):
    python scripts/backfill_cjeu_practice.py           # dry-run report
    python scripts/backfill_cjeu_practice.py --apply
"""
import argparse
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text as sa_text

from core.database import SessionLocal

API = "https://infohubapi.rs.ge/api/documents?skip=0&take=50&q=%E1%83%9B%E1%83%90%E1%83%A0%E1%83%97%E1%83%9A%E1%83%9B%E1%83%A1%E1%83%90%E1%83%AF%E1%83%A3%E1%83%9A%E1%83%94%E1%83%91%E1%83%98%E1%83%A1"
CJEU_MARKER = "მართლმსაჯულების სასამართლო"
CJEU_TEXT_PHRASE = "ევროპის კავშირის მართლმსაჯულების"


def fetch_listing() -> list:
    req = urllib.request.Request(API, headers={
        "User-Agent": "InfoHubAI-Bot/1.0",
        "Accept": "application/json, text/plain, */*",
        "languagecode": "ka",
        "Referer": "https://infohub.rs.ge/",
    })
    with urllib.request.urlopen(req, timeout=60) as r:
        payload = json.loads(r.read().decode("utf-8", "replace"))
    items = []
    for item in payload.get("data", []):
        t = item.get("type")
        type_name = t.get("name") if isinstance(t, dict) else None
        if type_name and CJEU_MARKER in type_name:
            bt = item.get("baseType")
            items.append({
                "uniqueKey": item.get("uniqueKey"),
                "type": type_name,
                "baseType": bt.get("name") if isinstance(bt, dict) else None,
                "name": item.get("name") or "",
            })
    return items


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    listing = fetch_listing()
    print(f"Donor listing: {len(listing)} CJEU items")

    db = SessionLocal()
    try:
        tagged = missing = 0
        for item in listing:
            source_url = f"https://infohub.rs.ge/ka/workspace/document/{item['uniqueKey']}"
            row = db.execute(sa_text(
                "SELECT id, subtype FROM documents WHERE source_url = :u"
            ), {"u": source_url}).one_or_none()
            if row is None:
                missing += 1
                print(f"  not in DB: {item['name'][:70]}")
                continue
            if row.subtype == "cjeu_practice":
                continue
            tagged += 1
            print(f"  tag: {item['name'][:80]}")
            if args.apply:
                db.execute(sa_text("""
                    UPDATE documents
                    SET subtype = 'cjeu_practice', subtype_source = 'rule',
                        metadata = (coalesce(metadata::jsonb, '{}'::jsonb)
                                    || jsonb_build_object('type', :t, 'baseType', :bt))::json
                    WHERE id = :id
                """), {"id": row.id, "t": item["type"], "bt": item["baseType"]})

        # Pass 2: old bulk copies by the distinctive text phrase.
        rows = db.execute(sa_text("""
            SELECT id, title FROM documents
            WHERE coalesce(subtype, '') != 'cjeu_practice'
              AND document_type = 'court_decision'
              AND full_text ILIKE :phrase
        """), {"phrase": f"%{CJEU_TEXT_PHRASE}%"}).all()
        for row in rows:
            tagged += 1
            print(f"  tag by text: {(row.title or '')[:80]}")
            if args.apply:
                db.execute(sa_text(
                    "UPDATE documents SET subtype = 'cjeu_practice', subtype_source = 'rule' WHERE id = :id"
                ), {"id": row.id})

        if args.apply:
            db.commit()
            total = db.execute(sa_text(
                "SELECT count(*) FROM documents WHERE subtype = 'cjeu_practice'"
            )).scalar()
            print(f"\nApplied. cjeu_practice total: {total} (tagged now: {tagged}, not in DB: {missing})")
        else:
            print(f"\nDry-run: would tag {tagged}, not in DB: {missing}. Re-run with --apply.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
