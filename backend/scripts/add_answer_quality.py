#!/usr/bin/env python3
"""Install answer-quality signals, user ratings and append-only admin reviews; dry plan by default."""
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import inspect, text

from scripts.schema_contract_cli import ddl_contract_sha256, run

DDL = (
    "ALTER TABLE messages ADD COLUMN IF NOT EXISTS evidence JSONB",
    "ALTER TABLE messages ADD COLUMN IF NOT EXISTS processing_ms INTEGER",
    '''DO $$ BEGIN
         IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_messages_processing_ms_nonneg'
                        AND conrelid = 'messages'::regclass) THEN
           ALTER TABLE messages ADD CONSTRAINT ck_messages_processing_ms_nonneg
             CHECK (processing_ms IS NULL OR processing_ms >= 0);
         END IF;
       END $$''',
    "CREATE INDEX IF NOT EXISTS ix_messages_role_created ON messages (role, created_at)",
    '''CREATE TABLE IF NOT EXISTS answer_ratings (
        id UUID PRIMARY KEY,
        message_id UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        value SMALLINT NOT NULL CHECK (value IN (-1, 1)),
        comment TEXT CHECK (comment IS NULL OR char_length(comment) <= 1000),
        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        CONSTRAINT uq_answer_ratings_message UNIQUE (message_id)
    )''',
    "CREATE INDEX IF NOT EXISTS ix_answer_ratings_value ON answer_ratings (value)",
    '''CREATE TABLE IF NOT EXISTS answer_reviews (
        id UUID PRIMARY KEY,
        message_id UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
        reviewer_id UUID NOT NULL,
        verdict VARCHAR(16) NOT NULL CHECK (verdict IN ('correct', 'partial', 'wrong')),
        reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
        note TEXT CHECK (note IS NULL OR char_length(note) <= 2000),
        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
    )''',
    "CREATE INDEX IF NOT EXISTS ix_answer_reviews_message_created ON answer_reviews (message_id, created_at)",
    '''CREATE OR REPLACE FUNCTION reject_answer_review_mutation() RETURNS trigger
       LANGUAGE plpgsql AS $$ BEGIN
         IF TG_OP = 'DELETE' THEN
           IF NOT EXISTS (SELECT 1 FROM messages WHERE id = OLD.message_id) THEN
             RETURN OLD;  -- cascade from a deleted message
           END IF;
         END IF;
         RAISE EXCEPTION 'answer reviews are append-only';
       END; $$''',
    "DROP TRIGGER IF EXISTS answer_reviews_immutable ON answer_reviews",
    '''CREATE TRIGGER answer_reviews_immutable BEFORE UPDATE OR DELETE
       ON answer_reviews FOR EACH ROW EXECUTE FUNCTION reject_answer_review_mutation()''',
    "DROP TRIGGER IF EXISTS answer_reviews_no_truncate ON answer_reviews",
    '''CREATE TRIGGER answer_reviews_no_truncate BEFORE TRUNCATE
       ON answer_reviews FOR EACH STATEMENT EXECUTE FUNCTION reject_answer_review_mutation()''',
    "ALTER TABLE answer_reviews ENABLE ALWAYS TRIGGER answer_reviews_immutable",
    "ALTER TABLE answer_reviews ENABLE ALWAYS TRIGGER answer_reviews_no_truncate",
)

EXPECTED = {
    "messages": {"evidence", "processing_ms"},
    "answer_ratings": {"id", "message_id", "user_id", "value", "comment", "created_at", "updated_at"},
    "answer_reviews": {"id", "message_id", "reviewer_id", "verdict", "reasons", "note", "created_at"},
}


def contract_sha256() -> str:
    return ddl_contract_sha256(DDL)


def apply_schema(connection) -> dict:
    for sql in DDL:
        connection.execute(text(sql))
    inspector = inspect(connection)
    missing = {table: sorted(cols - {c["name"] for c in inspector.get_columns(table)})
               for table, cols in EXPECTED.items()}
    triggers = connection.execute(text("""SELECT tgname, tgenabled FROM pg_trigger
        WHERE tgrelid = 'answer_reviews'::regclass
          AND tgname IN ('answer_reviews_immutable', 'answer_reviews_no_truncate')""")).all()
    if any(missing.values()) or sorted(triggers) != [("answer_reviews_immutable", "A"),
                                                     ("answer_reviews_no_truncate", "A")]:
        raise RuntimeError("Answer quality schema audit failed")
    return {"missing_columns": [], "append_only_triggers": True}


def main() -> int:
    return run(
        output_key="ANSWER_QUALITY_SCHEMA",
        label="Answer quality",
        contract=contract_sha256(),
        apply_schema=apply_schema,
    )


if __name__ == "__main__":
    raise SystemExit(main())
