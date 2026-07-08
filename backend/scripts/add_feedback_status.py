#!/usr/bin/env python
"""Add the ``status`` column to the existing ``feedback`` table.

``init_db``'s ``create_all`` only creates missing tables; it does not add
columns to tables that already exist, so the status field (new | in_progress |
fixed) needs this one-off ALTER. Idempotent.

Usage (inside infohub-backend):
    python scripts/add_feedback_status.py
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
            "ALTER TABLE feedback ADD COLUMN IF NOT EXISTS "
            "status VARCHAR(20) NOT NULL DEFAULT 'new'"
        ))
        db.commit()
        print("feedback.status:", dict(db.execute(
            text("SELECT status, count(*) FROM feedback GROUP BY status")
        ).all()))
    finally:
        db.close()


if __name__ == "__main__":
    main()
