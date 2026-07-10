#!/usr/bin/env python
"""Add appeal-chain columns to ``decision_facts`` (extraction v2).

``init_db``'s ``create_all`` only creates missing tables; it does not add
columns to tables that already exist. The new ``decision_links`` table itself
comes free via create_all — only the ALTERs need this one-off script. Idempotent.

Usage (inside infohub-backend):
    python scripts/add_decision_chain_fields.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from core.database import SessionLocal, Base, engine
from models.document import DecisionLink


def main() -> None:
    Base.metadata.create_all(bind=engine, tables=[DecisionLink.__table__])
    db = SessionLocal()
    try:
        for ddl in (
            "ALTER TABLE decision_facts ADD COLUMN IF NOT EXISTS case_number VARCHAR(100)",
            "ALTER TABLE decision_facts ADD COLUMN IF NOT EXISTS prior_refs JSON",
            "ALTER TABLE decision_facts ADD COLUMN IF NOT EXISTS prior_body VARCHAR(40)",
            "CREATE INDEX IF NOT EXISTS idx_decision_facts_case ON decision_facts (case_number)",
            "CREATE INDEX IF NOT EXISTS idx_decision_facts_number ON decision_facts (decision_number)",
        ):
            db.execute(text(ddl))
        db.commit()
        print("decision_facts extraction versions:", dict(db.execute(
            text("SELECT extraction_version, count(*) FROM decision_facts GROUP BY 1 ORDER BY 1")
        ).all()))
        print("decision_links:", db.execute(text("SELECT count(*) FROM decision_links")).scalar())
    finally:
        db.close()


if __name__ == "__main__":
    main()
