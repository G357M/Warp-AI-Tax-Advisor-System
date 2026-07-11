#!/usr/bin/env python
"""Retype guide documents misclassified as court_decision.

Guide announcements carry the guide TOPIC as their title ("უიმედო ვალი
(სასამართლოს გადაწყვეტილება...) N 0301"), which fooled the keyword-based
``infer_document_type`` into ``court_decision``. Consequences: the /guides
registry can't link them (it looks for guideline-typed docs), they sit in the
wrong RAG lane, and the decision-facts extractor treats them as disputes.

After the subtype reclassification, ``subtype='guidance' AND
document_type='court_decision'`` identifies exactly this class. This retypes
them to ``guideline`` and removes their bogus decision_facts rows.
Idempotent; dry-run by default.

Usage (inside infohub-backend):
    python scripts/fix_guide_doctype.py           # dry-run report
    python scripts/fix_guide_doctype.py --apply
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text as sa_text

from core.database import SessionLocal


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        rows = db.execute(sa_text("""
            SELECT d.id, d.title, f.id AS facts_id
            FROM documents d
            LEFT JOIN decision_facts f ON f.document_id = d.id
            WHERE d.document_type = 'court_decision' AND d.subtype = 'guidance'
        """)).all()
        print(f"Mistyped guide documents: {len(rows)}")
        for r in rows:
            print(f"  - {(r.title or '')[:90]}  (facts row: {'yes' if r.facts_id else 'no'})")

        if not args.apply:
            print("\nDry-run only. Re-run with --apply to retype and clean decision_facts.")
            return

        doc_ids = [r.id for r in rows]
        if doc_ids:
            deleted = db.execute(sa_text(
                "DELETE FROM decision_facts WHERE document_id = ANY(:ids)"
            ), {"ids": doc_ids}).rowcount
            db.execute(sa_text(
                "UPDATE documents SET document_type = 'guideline' WHERE id = ANY(:ids)"
            ), {"ids": doc_ids})
            db.commit()
            print(f"\nRetyped {len(doc_ids)} docs to guideline; removed {deleted} bogus decision_facts rows.")
        else:
            print("\nNothing to do.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
