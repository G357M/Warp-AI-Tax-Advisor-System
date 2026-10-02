#!/usr/bin/env python3
"""Install an additive, append-only operator decision journal; dry plan by default."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import inspect, text
from core.database import engine

DDL = (
    '''CREATE TABLE IF NOT EXISTS billing_review_decisions (
        id UUID PRIMARY KEY,
        checkout_id UUID NOT NULL REFERENCES billing_checkouts(id) ON DELETE RESTRICT,
        actor_id UUID NOT NULL,
        idempotency_key VARCHAR(128) NOT NULL,
        request_sha256 VARCHAR(64) NOT NULL,
        action VARCHAR(32) NOT NULL,
        reason TEXT NOT NULL,
        access_effect VARCHAR(32) NOT NULL,
        "before" JSON NOT NULL,
        "after" JSON NOT NULL,
        provider_evidence JSON,
        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        CONSTRAINT uq_billing_review_key UNIQUE (checkout_id, idempotency_key)
    )''',
    "CREATE INDEX IF NOT EXISTS ix_billing_review_checkout_created ON billing_review_decisions (checkout_id, created_at)",
    '''CREATE OR REPLACE FUNCTION reject_billing_review_mutation() RETURNS trigger
       LANGUAGE plpgsql AS $$ BEGIN
         RAISE EXCEPTION 'billing review decisions are immutable';
       END; $$''',
    "DROP TRIGGER IF EXISTS billing_review_immutable ON billing_review_decisions",
    '''CREATE TRIGGER billing_review_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
       ON billing_review_decisions FOR EACH STATEMENT EXECUTE FUNCTION reject_billing_review_mutation()''',
    "ALTER TABLE billing_review_decisions ENABLE ALWAYS TRIGGER billing_review_immutable",
)


def contract_sha256() -> str:
    return hashlib.sha256("\n".join(" ".join(sql.split()) for sql in DDL).encode()).hexdigest()


def apply_schema(connection) -> dict:
    for sql in DDL:
        connection.execute(text(sql))
    expected = {"id", "checkout_id", "actor_id", "idempotency_key", "request_sha256", "action", "reason",
                "access_effect", "before", "after", "provider_evidence", "created_at"}
    missing = expected - {column["name"] for column in inspect(connection).get_columns("billing_review_decisions")}
    trigger = connection.execute(text("""SELECT tgenabled FROM pg_trigger
        WHERE tgrelid = 'billing_review_decisions'::regclass AND tgname = 'billing_review_immutable'""")).scalar_one()
    constraints = inspect(connection).get_unique_constraints("billing_review_decisions")
    unique = any(c["column_names"] == ["checkout_id", "idempotency_key"] for c in constraints)
    if missing or trigger != "A" or not unique:
        raise RuntimeError("Billing review journal schema audit failed")
    return {"missing_columns": [], "immutable_trigger": True, "idempotency_constraint": True}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-contract-sha256")
    args = parser.parse_args()
    contract = contract_sha256()
    if args.apply and args.expected_contract_sha256 != contract:
        raise SystemExit("Review journal contract mismatch: explicit reviewed SHA-256 is required")
    result = {"contract_sha256": contract, "execute": args.apply}
    if args.apply:
        if engine.dialect.name != "postgresql":
            raise SystemExit("Review journal schema requires PostgreSQL")
        with engine.begin() as connection:
            result.update(apply_schema(connection))
    print("BILLING_REVIEW_SCHEMA=" + json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
