#!/usr/bin/env python3
"""Install the additive, idempotent provider-payment schema foundation."""
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
    "ALTER TABLE payments ADD COLUMN IF NOT EXISTS amount_minor INTEGER",
    "UPDATE payments SET amount_minor = ROUND(amount_gel * 100)::INTEGER WHERE amount_minor IS NULL",
    "ALTER TABLE payments ALTER COLUMN amount_minor SET NOT NULL",
    "ALTER TABLE billing_checkouts ADD COLUMN IF NOT EXISTS provider_status VARCHAR(40)",
    "ALTER TABLE billing_checkouts ADD COLUMN IF NOT EXISTS provider_redirect_url VARCHAR(1000)",
    "ALTER TABLE billing_checkouts ADD COLUMN IF NOT EXISTS provider_checked_at TIMESTAMP WITHOUT TIME ZONE",
    "ALTER TABLE billing_checkouts ADD COLUMN IF NOT EXISTS terms_version VARCHAR(32)",
    "ALTER TABLE billing_checkouts ADD COLUMN IF NOT EXISTS terms_accepted_at TIMESTAMP WITHOUT TIME ZONE",
    "ALTER TABLE billing_checkouts ADD COLUMN IF NOT EXISTS immediate_service_requested_at TIMESTAMP WITHOUT TIME ZONE",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_payments_provider_tx ON payments (provider, provider_tx_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_billing_checkouts_provider_order ON billing_checkouts (provider, provider_order_id)",
    """CREATE TABLE IF NOT EXISTS billing_provider_events (
        id UUID PRIMARY KEY,
        checkout_id UUID NOT NULL REFERENCES billing_checkouts(id) ON DELETE CASCADE,
        provider VARCHAR(20) NOT NULL,
        event_id VARCHAR(200) NOT NULL,
        provider_status VARCHAR(40) NOT NULL,
        payload_sha256 VARCHAR(64) NOT NULL,
        processing_status VARCHAR(20) NOT NULL,
        error_code VARCHAR(80),
        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        processed_at TIMESTAMP WITHOUT TIME ZONE,
        CONSTRAINT uq_billing_provider_event UNIQUE (provider, event_id)
    )""",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_billing_provider_event ON billing_provider_events (provider, event_id)",
    "CREATE INDEX IF NOT EXISTS ix_billing_provider_events_checkout_created ON billing_provider_events (checkout_id, created_at)",
)

EXPECTED_COLUMNS = {
    "payments": {"amount_minor"},
    "billing_checkouts": {
        "provider_status",
        "provider_redirect_url",
        "provider_checked_at",
        "terms_version",
        "terms_accepted_at",
        "immediate_service_requested_at",
    },
    "billing_provider_events": {
        "id",
        "checkout_id",
        "provider",
        "event_id",
        "provider_status",
        "payload_sha256",
        "processing_status",
        "error_code",
        "created_at",
        "processed_at",
    },
}


def contract_sha256() -> str:
    normalized = "\n".join(" ".join(statement.split()) for statement in DDL)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _assert_no_provider_duplicates(connection) -> None:
    duplicate_payments = connection.execute(
        text(
            """SELECT COUNT(*) FROM (
                SELECT provider, provider_tx_id
                FROM payments
                WHERE provider_tx_id IS NOT NULL
                GROUP BY provider, provider_tx_id
                HAVING COUNT(*) > 1
            ) AS duplicate_groups"""
        )
    ).scalar_one()
    duplicate_orders = connection.execute(
        text(
            """SELECT COUNT(*) FROM (
                SELECT provider, provider_order_id
                FROM billing_checkouts
                WHERE provider_order_id IS NOT NULL
                GROUP BY provider, provider_order_id
                HAVING COUNT(*) > 1
            ) AS duplicate_groups"""
        )
    ).scalar_one()
    if duplicate_payments or duplicate_orders:
        raise RuntimeError(
            "provider identifier duplicates block billing schema installation"
        )


def _audit(connection) -> dict:
    inspector = inspect(connection)
    missing: dict[str, list[str]] = {}
    for table, expected in EXPECTED_COLUMNS.items():
        if not inspector.has_table(table):
            missing[table] = sorted(expected)
            continue
        actual = {column["name"] for column in inspector.get_columns(table)}
        absent = sorted(expected - actual)
        if absent:
            missing[table] = absent

    null_amounts = connection.execute(
        text("SELECT COUNT(*) FROM payments WHERE amount_minor IS NULL")
    ).scalar_one()
    indexes = {
        row[0]
        for row in connection.execute(
            text(
                """SELECT indexname FROM pg_indexes
                WHERE schemaname = current_schema()
                  AND indexname IN (
                    'uq_payments_provider_tx',
                    'uq_billing_checkouts_provider_order',
                    'uq_billing_provider_event',
                    'ix_billing_provider_events_checkout_created'
                  )"""
            )
        )
    }
    expected_indexes = {
        "uq_payments_provider_tx",
        "uq_billing_checkouts_provider_order",
        "uq_billing_provider_event",
        "ix_billing_provider_events_checkout_created",
    }
    return {
        "missing_columns": missing,
        "missing_indexes": sorted(expected_indexes - indexes),
        "null_payment_amounts": null_amounts,
    }


def apply_schema(connection) -> dict:
    """Apply and audit the exact contract inside the caller's transaction."""
    _assert_no_provider_duplicates(connection)
    for statement in DDL:
        connection.execute(text(statement))
    audit = _audit(connection)
    if audit["missing_columns"] or audit["missing_indexes"] or audit["null_payment_amounts"]:
        raise RuntimeError(f"billing provider schema audit failed: {audit}")
    return audit


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-contract-sha256")
    args = parser.parse_args()

    contract = contract_sha256()
    if args.apply and args.expected_contract_sha256 != contract:
        raise SystemExit(
            "billing schema contract mismatch: explicit reviewed SHA-256 is required"
        )
    if not args.apply:
        print(
            "BILLING_PROVIDER_SCHEMA_PLAN="
            + json.dumps(
                {
                    "additive_only": True,
                    "contract_sha256": contract,
                    "execute": False,
                    "statement_count": len(DDL),
                },
                sort_keys=True,
            )
        )
        return 0
    if engine.dialect.name != "postgresql":
        raise SystemExit("billing provider schema apply requires PostgreSQL")

    with engine.begin() as connection:
        audit = apply_schema(connection)

    print(
        "BILLING_PROVIDER_SCHEMA_APPLY="
        + json.dumps(
            {
                "additive_only": True,
                "contract_sha256": contract,
                "execute": True,
                **audit,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
