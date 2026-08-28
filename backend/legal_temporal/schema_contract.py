"""Versioned PostgreSQL contract for the temporal legal foundation."""

from __future__ import annotations

import hashlib
import json

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint

from models.legal_temporal import LEGAL_TEMPORAL_TABLES


SCHEMA_VERSION = 1

EXPECTED_TABLES = (
    "legal_temporal_schema_migrations",
    "legal_source_blobs",
    "legal_source_snapshots",
    "legal_source_observations",
    "legal_acts",
    "legal_act_publications",
    "legal_provisions",
    "legal_provision_versions",
    "legal_amendment_operations",
    "legal_review_events",
)

IMMUTABLE_TABLES = (
    "legal_temporal_schema_migrations",
    "legal_source_blobs",
    "legal_source_snapshots",
    "legal_source_observations",
    "legal_provision_versions",
    "legal_amendment_operations",
    "legal_review_events",
)

IMMUTABILITY_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION infohub_reject_legal_temporal_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'immutable legal temporal record: %', TG_TABLE_NAME
        USING ERRCODE = '55000';
END;
$$
""".strip()

PROVISION_INTERVAL_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION infohub_validate_provision_version_insert()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    predecessor_provision UUID;
BEGIN
    PERFORM pg_advisory_xact_lock(
        hashtextextended(NEW.provision_id::text, 0)
    );

    IF NEW.valid_to IS NOT NULL AND NEW.valid_to <= NEW.valid_from THEN
        RAISE EXCEPTION 'legal provision version has an invalid valid-time interval'
            USING ERRCODE = '23514';
    END IF;

    IF NEW.supersedes_version_id IS NOT NULL THEN
        SELECT provision_id
          INTO predecessor_provision
          FROM legal_provision_versions
         WHERE id = NEW.supersedes_version_id
         FOR SHARE;

        IF predecessor_provision IS NULL THEN
            RAISE EXCEPTION 'superseded legal provision version does not exist'
                USING ERRCODE = '23503';
        END IF;
        IF predecessor_provision <> NEW.provision_id THEN
            RAISE EXCEPTION 'a legal provision version may supersede only the same provision'
                USING ERRCODE = '23514';
        END IF;
        IF EXISTS (
            SELECT 1
              FROM legal_provision_versions successor
             WHERE successor.supersedes_version_id = NEW.supersedes_version_id
        ) THEN
            RAISE EXCEPTION 'legal provision version already has a successor'
                USING ERRCODE = '23505';
        END IF;
    END IF;

    IF EXISTS (
        SELECT 1
          FROM legal_provision_versions candidate
         WHERE candidate.provision_id = NEW.provision_id
           AND candidate.id IS DISTINCT FROM NEW.supersedes_version_id
           AND NOT EXISTS (
               SELECT 1
                 FROM legal_provision_versions successor
                WHERE successor.supersedes_version_id = candidate.id
           )
           AND daterange(
                   candidate.valid_from,
                   COALESCE(candidate.valid_to, 'infinity'::date),
                   '[)'
               ) && daterange(
                   NEW.valid_from,
                   COALESCE(NEW.valid_to, 'infinity'::date),
                   '[)'
               )
    ) THEN
        RAISE EXCEPTION 'overlapping head versions for one legal provision'
            USING ERRCODE = '23P01';
    END IF;

    RETURN NEW;
END;
$$
""".strip()

PROVISION_INTERVAL_TRIGGER_DROP_SQL = """
DROP TRIGGER IF EXISTS trg_legal_provision_versions_interval
    ON legal_provision_versions
""".strip()

PROVISION_INTERVAL_TRIGGER_CREATE_SQL = """
CREATE TRIGGER trg_legal_provision_versions_interval
BEFORE INSERT ON legal_provision_versions
FOR EACH ROW
EXECUTE FUNCTION infohub_validate_provision_version_insert()
""".strip()


def immutability_trigger_sql(table: str) -> tuple[str, str]:
    if table not in IMMUTABLE_TABLES:
        raise ValueError(f"unsupported immutable table: {table}")
    trigger = f"trg_{table}_immutable"
    return (
        f"DROP TRIGGER IF EXISTS {trigger} ON {table}",
        (
            f"CREATE TRIGGER {trigger}\n"
            f"BEFORE UPDATE OR DELETE ON {table}\n"
            "FOR EACH ROW\n"
            "EXECUTE FUNCTION infohub_reject_legal_temporal_mutation()"
        ),
    )


POSTGRES_DDL = (
    IMMUTABILITY_FUNCTION_SQL,
    PROVISION_INTERVAL_FUNCTION_SQL,
    PROVISION_INTERVAL_TRIGGER_DROP_SQL,
    PROVISION_INTERVAL_TRIGGER_CREATE_SQL,
    *(
        statement
        for table in IMMUTABLE_TABLES
        for statement in immutability_trigger_sql(table)
    ),
)


def _column_contract(column) -> dict[str, object]:
    column_type = column.type
    return {
        "name": column.name,
        "type": f"{type(column_type).__module__}.{type(column_type).__name__}",
        "length": getattr(column_type, "length", None),
        "timezone": getattr(column_type, "timezone", None),
        "as_uuid": getattr(column_type, "as_uuid", None),
        "nullable": bool(column.nullable),
        "primary_key": bool(column.primary_key),
        "autoincrement": str(column.autoincrement),
        "foreign_keys": sorted(
            (
                {
                    "target": foreign_key.target_fullname,
                    "ondelete": foreign_key.ondelete,
                }
                for foreign_key in column.foreign_keys
            ),
            key=lambda item: (item["target"], item["ondelete"] or ""),
        ),
    }


def _constraint_contract(constraint) -> dict[str, object] | None:
    if isinstance(constraint, CheckConstraint):
        return {
            "kind": "check",
            "name": constraint.name,
            "sql": str(constraint.sqltext),
        }
    if isinstance(constraint, UniqueConstraint):
        return {
            "kind": "unique",
            "name": constraint.name,
            "columns": sorted(column.name for column in constraint.columns),
        }
    if isinstance(constraint, ForeignKeyConstraint):
        return {
            "kind": "foreign_key",
            "name": constraint.name,
            "columns": [element.parent.name for element in constraint.elements],
            "targets": [element.target_fullname for element in constraint.elements],
            "ondelete": constraint.ondelete,
        }
    return None


def _model_contract() -> list[dict[str, object]]:
    tables: list[dict[str, object]] = []
    for table in LEGAL_TEMPORAL_TABLES:
        constraints = [
            item
            for item in (_constraint_contract(value) for value in table.constraints)
            if item is not None
        ]
        tables.append(
            {
                "table": table.name,
                "columns": [_column_contract(column) for column in table.columns],
                "constraints": sorted(
                    constraints,
                    key=lambda item: (
                        str(item["kind"]),
                        str(item.get("name") or ""),
                        json.dumps(item, sort_keys=True),
                    ),
                ),
                "indexes": sorted(
                    (
                        {
                            "name": index.name,
                            "unique": bool(index.unique),
                            "columns": [column.name for column in index.columns],
                        }
                        for index in table.indexes
                    ),
                    key=lambda item: str(item["name"]),
                ),
            }
        )
    return tables


def _contract_payload() -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "expected_tables": list(EXPECTED_TABLES),
        "immutable_tables": list(IMMUTABLE_TABLES),
        "model_contract": _model_contract(),
        "postgres_ddl": list(POSTGRES_DDL),
        "valid_time_bounds": "[valid_from, valid_to)",
        "system_time_strategy": "append-only supersedes chain",
        "snapshot_strategy": "content-addressed immutable bytes",
    }


SCHEMA_CONTRACT_SHA256 = hashlib.sha256(
    json.dumps(
        _contract_payload(),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()


def schema_contract() -> dict[str, object]:
    """Return a copy safe for audit output and tests."""
    return {
        **_contract_payload(),
        "contract_sha256": SCHEMA_CONTRACT_SHA256,
    }
