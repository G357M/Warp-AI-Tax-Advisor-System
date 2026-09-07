"""Exercise the additive billing migration against CI PostgreSQL."""
import os
from uuid import UUID

import pytest
from sqlalchemy import text

from core.database import engine
from scripts.add_billing_provider_foundation import apply_schema, contract_sha256


pytestmark = pytest.mark.skipif(
    os.getenv("BILLING_PROVIDER_POSTGRES_TESTS") != "1",
    reason="requires the dedicated PostgreSQL CI service",
)

LEGACY_PAYMENT_ID = UUID("10000000-0000-0000-0000-000000000001")
LEGACY_CHECKOUT_ID = UUID("20000000-0000-0000-0000-000000000001")


def test_additive_billing_provider_schema_is_idempotent_and_backfills_money():
    assert contract_sha256() == "e452a92829e9e3d8aaf5e7c8227d1fd5e477c095ade99856135ca338ffe1baad"
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS billing_provider_events CASCADE"))
        connection.execute(text("DROP TABLE IF EXISTS billing_checkouts CASCADE"))
        connection.execute(text("DROP TABLE IF EXISTS payments CASCADE"))
        connection.execute(
            text(
                """CREATE TABLE payments (
                    id UUID PRIMARY KEY,
                    amount_gel DOUBLE PRECISION NOT NULL,
                    provider VARCHAR(20) NOT NULL,
                    provider_tx_id VARCHAR(255)
                )"""
            )
        )
        connection.execute(
            text(
                """CREATE TABLE billing_checkouts (
                    id UUID PRIMARY KEY,
                    provider VARCHAR(20) NOT NULL,
                    provider_order_id VARCHAR(255)
                )"""
            )
        )
        connection.execute(
            text(
                """INSERT INTO payments (id, amount_gel, provider)
                VALUES (:id, 49.00, 'manual')"""
            ),
            {"id": LEGACY_PAYMENT_ID},
        )
        connection.execute(
            text(
                """INSERT INTO billing_checkouts (id, provider)
                VALUES (:id, 'manual')"""
            ),
            {"id": LEGACY_CHECKOUT_ID},
        )

        first = apply_schema(connection)
        second = apply_schema(connection)
        amount_minor = connection.execute(
            text("SELECT amount_minor FROM payments WHERE id = :id"),
            {"id": LEGACY_PAYMENT_ID},
        ).scalar_one()

    assert first == second
    assert first == {
        "missing_columns": {},
        "missing_indexes": [],
        "null_payment_amounts": 0,
    }
    assert amount_minor == 4900
