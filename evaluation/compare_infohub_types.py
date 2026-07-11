#!/usr/bin/env python3
"""Print our corpus distribution in infohub.rs.ge's own taxonomy terms.

Read-only. The donor site groups documents by the Georgian type label (ვიდი)
that we keep verbatim in documents.metadata->>'type'; this prints our counts
along the same axes so the output can be diffed against the donor's filter
tree (see docs / session 2026-07-11).

Usage (inside infohub-backend, file docker-cp'd to /tmp):
    python3 /tmp/compare_infohub_types.py
"""
import sys

sys.path.insert(0, "/app")
sys.stdout.reconfigure(encoding="utf-8")

from sqlalchemy import text  # noqa: E402
from core.database import SessionLocal  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        total = db.execute(text("SELECT count(*) FROM documents")).scalar()
        print(f"TOTAL documents: {total}\n")

        print("== by document_type (наша грубая типизация) ==")
        for name, n in db.execute(text(
            "SELECT document_type, count(*) FROM documents GROUP BY 1 ORDER BY 2 DESC"
        )).all():
            print(f"  {n:6d}  {name}")

        print("\n== by metadata->>'species' ==")
        for name, n in db.execute(text(
            "SELECT coalesce(metadata->>'species','(нет)'), count(*) FROM documents GROUP BY 1 ORDER BY 2 DESC"
        )).all():
            print(f"  {n:6d}  {name}")

        print("\n== by metadata->>'type' (вид донора, топ-50) ==")
        for name, n in db.execute(text(
            "SELECT coalesce(metadata->>'type','(нет)'), count(*) FROM documents "
            "GROUP BY 1 ORDER BY 2 DESC LIMIT 50"
        )).all():
            print(f"  {n:6d}  {name}")

        print("\n== решения по спорам: наши decision_facts по инстанциям ==")
        for name, n in db.execute(text(
            "SELECT coalesce(authority_body,'(null)'), count(*) FROM decision_facts GROUP BY 1 ORDER BY 2 DESC"
        )).all():
            print(f"  {n:6d}  {name}")

        digests = db.execute(text(
            "SELECT count(*) FROM documents WHERE (metadata->>'kind') = 'digest'"
        )).scalar()
        print(f"\nВС-дайджесты 2013-2017 (наш отдельный импорт, у донора их нет): {digests}")

        no_type = db.execute(text(
            "SELECT count(*) FROM documents WHERE metadata->>'type' IS NULL"
        )).scalar()
        print(f"Документов без metadata.type (старый bulk-импорт): {no_type}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
