#!/usr/bin/env python
"""Enable pg_trgm and index document titles for fuzzy search (П5).

Powers typo-tolerant / word-form-tolerant search on the public /news page
(word_similarity over Georgian titles). Idempotent.

Usage (inside infohub-backend):
    python scripts/add_trgm_search.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from core.database import SessionLocal


def main() -> None:
    db = SessionLocal()
    try:
        db.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        db.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_documents_title_trgm "
            "ON documents USING gin (title gin_trgm_ops)"
        ))
        db.commit()
        print("pg_trgm:", db.execute(text(
            "SELECT count(*) FROM pg_extension WHERE extname = 'pg_trgm'"
        )).scalar())
        print("sample word_similarity:", db.execute(text(
            "SELECT round(word_similarity('დანაკარგები', 'დანაკარგების ნორმების დამტკიცების შესახებ')::numeric, 3)"
        )).scalar())
    finally:
        db.close()


if __name__ == "__main__":
    main()
