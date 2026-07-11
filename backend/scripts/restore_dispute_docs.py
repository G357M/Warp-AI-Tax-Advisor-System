#!/usr/bin/env python
"""Restore dispute-council orders wrongly retyped to guideline (2026-07-11 incident).

What happened: the news-subtype rule tagged ~5.9k old bulk-imported council
orders ("ბრძანება N 15328" — no metadata, title ends with a number) as
guidance, and fix_guide_doctype.py then retyped them to guideline and deleted
their decision_facts rows (decision_links went with them via CASCADE).

Recovery criteria — a guideline-typed doc is a dispute decision when:
  1. its trailing title number is NOT in the official situational-guides
     registry (parsed with the same code /guides uses), AND
  2. its full_text carries dispute markers (საჩივ / დავების განხილვ / მომჩივან).

Dry-run by default; --apply retypes back to court_decision and clears the
wrong subtype. After applying, re-run extract_decision_facts.py (the restored
docs are pending again) and link_decision_chains.py --apply.

Usage (inside infohub-backend):
    python scripts/restore_dispute_docs.py           # report
    python scripts/restore_dispute_docs.py --apply
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text as sa_text

from core.database import SessionLocal
from api.routes.guides import REGISTRY_TITLE, parse_registry

NUM_RE = re.compile(r"N ?([0-9]{3,5})\s*$")
DISPUTE_MARKERS = ("საჩივ", "დავების განხილვ", "მომჩივან")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        registry_row = db.execute(sa_text(
            "SELECT full_text FROM documents WHERE title = :t "
            "ORDER BY date_published DESC NULLS LAST LIMIT 1"
        ), {"t": REGISTRY_TITLE}).first()
        registry_numbers = set()
        if registry_row and registry_row[0]:
            for section in parse_registry(registry_row[0]):
                for item in section["items"]:
                    registry_numbers.add(item["number"])
        print(f"Official registry guide numbers: {len(registry_numbers)}")

        rows = db.execute(sa_text("""
            SELECT id, title,
                   (full_text ILIKE '%საჩივ%' OR full_text ILIKE '%დავების განხილვ%'
                    OR full_text ILIKE '%მომჩივან%') AS disputeish
            FROM documents
            WHERE document_type = 'guideline' AND title ~ 'N ?[0-9]{3,5}\\s*$'
        """)).all()

        restore, kept_registry, kept_no_marker = [], 0, []
        for r in rows:
            m = NUM_RE.search(r.title or "")
            num = m.group(1) if m else None
            if num and num in registry_numbers:
                kept_registry += 1
                continue
            if r.disputeish:
                restore.append(r.id)
            else:
                kept_no_marker.append(r.title or "")

        print(f"Guideline docs with trailing number: {len(rows)}")
        print(f"  keep (in guides registry):   {kept_registry}")
        print(f"  keep (no dispute markers):   {len(kept_no_marker)}")
        print(f"  RESTORE to court_decision:   {len(restore)}")
        print("\nSample kept-no-marker titles (eyeball these):")
        for t in kept_no_marker[:10]:
            print(f"  - {t[:90]}")

        if not args.apply:
            print("\nDry-run only. Re-run with --apply to restore.")
            return

        if restore:
            db.execute(sa_text("""
                UPDATE documents
                SET document_type = 'court_decision', subtype = NULL, subtype_source = NULL
                WHERE id = ANY(:ids)
            """), {"ids": restore})
            db.commit()
        pending = db.execute(sa_text("""
            SELECT count(*) FROM documents d
            LEFT JOIN decision_facts f ON f.document_id = d.id
            WHERE d.document_type = 'court_decision' AND f.id IS NULL
              AND (d.metadata->>'kind') IS DISTINCT FROM 'digest'
        """)).scalar()
        print(f"\nRestored {len(restore)} docs. decision_facts pending re-extraction: {pending}")
        print("Next: nohup extract_decision_facts.py (full run), then link_decision_chains.py --apply")
    finally:
        db.close()


if __name__ == "__main__":
    main()
