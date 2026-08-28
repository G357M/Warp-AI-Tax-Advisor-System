#!/usr/bin/env python3
"""Install the additive Temporal Legal Engine foundation.

Dry-run is the default and performs no database call.  Apply mode is restricted
to PostgreSQL, requires the exact reviewed contract SHA-256 and creates only new
tables, functions and triggers.  It never backfills or updates legal content.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import inspect, text

from core.database import engine
from legal_temporal.schema_contract import (
    EXPECTED_TABLES,
    POSTGRES_DDL,
    SCHEMA_CONTRACT_SHA256,
    SCHEMA_VERSION,
)
from models.legal_temporal import LEGAL_TEMPORAL_TABLES


def migration_plan(*, execute: bool) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "contract_sha256": SCHEMA_CONTRACT_SHA256,
        "execute": execute,
        "additive_only": True,
        "backfill_allowed": False,
        "public_answer_routing_changed": False,
        "expected_tables": list(EXPECTED_TABLES),
        "table_count": len(EXPECTED_TABLES),
    }


def apply_schema(expected_contract_sha256: str) -> dict[str, object]:
    if expected_contract_sha256 != SCHEMA_CONTRACT_SHA256:
        raise ValueError(
            "expected contract SHA-256 does not match the reviewed temporal schema"
        )
    if engine.dialect.name != "postgresql":
        raise ValueError("temporal legal schema apply requires PostgreSQL")

    with engine.begin() as connection:
        connection.execute(
            text(
                "SELECT pg_advisory_xact_lock("
                "hashtextextended(:lock_key, 0))"
            ),
            {"lock_key": "infohub:legal-temporal-schema"},
        )
        if "documents" not in set(inspect(connection).get_table_names()):
            raise ValueError(
                "legacy documents table must exist before temporal schema apply"
            )
        for table in LEGAL_TEMPORAL_TABLES:
            table.create(bind=connection, checkfirst=True)
        for statement in POSTGRES_DDL:
            connection.execute(text(statement))
        existing = connection.execute(
            text(
                "SELECT contract_sha256 FROM legal_temporal_schema_migrations "
                "WHERE schema_version = :schema_version"
            ),
            {"schema_version": SCHEMA_VERSION},
        ).scalar_one_or_none()
        if existing is None:
            connection.execute(
                text(
                    "INSERT INTO legal_temporal_schema_migrations "
                    "(schema_version, contract_sha256, applied_at) "
                    "VALUES (:schema_version, :contract_sha256, NOW())"
                ),
                {
                    "schema_version": SCHEMA_VERSION,
                    "contract_sha256": SCHEMA_CONTRACT_SHA256,
                },
            )
        elif existing != SCHEMA_CONTRACT_SHA256:
            raise ValueError(
                "installed temporal schema version has a different contract SHA-256"
            )
    return migration_plan(execute=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-contract-sha256")
    args = parser.parse_args()

    if not args.apply:
        print(
            "LEGAL_TEMPORAL_SCHEMA_PLAN="
            + json.dumps(migration_plan(execute=False), sort_keys=True)
        )
        return 0
    if not args.expected_contract_sha256:
        parser.error("--apply requires --expected-contract-sha256")

    report = apply_schema(args.expected_contract_sha256)
    print("LEGAL_TEMPORAL_SCHEMA_APPLY=" + json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
