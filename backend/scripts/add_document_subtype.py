#!/usr/bin/env python
"""Add the ``subtype``/``subtype_source`` columns to the ``documents`` table.

``init_db``'s ``create_all`` only creates missing tables; it does not add
columns to tables that already exist, so the news subcategory fields need this
one-off ALTER. Idempotent.

Usage (inside infohub-backend):
    python scripts/add_document_subtype.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from core.database import SessionLocal


def main() -> None:
    db = SessionLocal()
    try:
        db.execute(text(
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS subtype VARCHAR(50)"
        ))
        db.execute(text(
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS subtype_source VARCHAR(10)"
        ))
        db.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_documents_subtype ON documents (subtype)"
        ))
        db.commit()
        print("documents.subtype:", dict(db.execute(
            text("SELECT coalesce(subtype, '(null)'), count(*) FROM documents GROUP BY 1 ORDER BY 2 DESC")
        ).all()))
    finally:
        db.close()


if __name__ == "__main__":
    main()
