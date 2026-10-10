#!/usr/bin/env python3
"""Install the additive, append-only administrator action journal; dry plan by default."""
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import inspect, text

from scripts.schema_contract_cli import ddl_contract_sha256, run

DDL = (
    '''CREATE TABLE IF NOT EXISTS admin_audit_log (
        id UUID PRIMARY KEY,
        actor_id UUID NOT NULL,
        action VARCHAR(64) NOT NULL,
        target_type VARCHAR(32) NOT NULL,
        target_id VARCHAR(64) NOT NULL,
        "before" JSON,
        "after" JSON,
        reason TEXT,
        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
    )''',
    "CREATE INDEX IF NOT EXISTS ix_admin_audit_created ON admin_audit_log (created_at DESC)",
    "CREATE INDEX IF NOT EXISTS ix_admin_audit_action_created ON admin_audit_log (action, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_admin_audit_actor_created ON admin_audit_log (actor_id, created_at)",
    '''CREATE OR REPLACE FUNCTION reject_admin_audit_mutation() RETURNS trigger
       LANGUAGE plpgsql AS $$ BEGIN
         RAISE EXCEPTION 'admin audit log is append-only';
       END; $$''',
    "DROP TRIGGER IF EXISTS admin_audit_immutable ON admin_audit_log",
    '''CREATE TRIGGER admin_audit_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
       ON admin_audit_log FOR EACH STATEMENT EXECUTE FUNCTION reject_admin_audit_mutation()''',
    "ALTER TABLE admin_audit_log ENABLE ALWAYS TRIGGER admin_audit_immutable",
)

EXPECTED_COLUMNS = {"id", "actor_id", "action", "target_type", "target_id", "before", "after",
                    "reason", "created_at"}


def contract_sha256() -> str:
    return ddl_contract_sha256(DDL)


def apply_schema(connection) -> dict:
    for sql in DDL:
        connection.execute(text(sql))
    columns = {column["name"] for column in inspect(connection).get_columns("admin_audit_log")}
    trigger = connection.execute(text("""SELECT tgenabled FROM pg_trigger
        WHERE tgrelid = 'admin_audit_log'::regclass AND tgname = 'admin_audit_immutable'""")).scalar_one()
    if EXPECTED_COLUMNS - columns or trigger != "A":
        raise RuntimeError("Admin audit journal schema audit failed")
    return {"missing_columns": [], "append_only_trigger": True}


def main() -> int:
    return run(
        output_key="ADMIN_AUDIT_SCHEMA",
        label="Admin audit journal",
        contract=contract_sha256(),
        apply_schema=apply_schema,
    )


if __name__ == "__main__":
    raise SystemExit(main())
