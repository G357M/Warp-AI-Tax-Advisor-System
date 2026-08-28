#!/usr/bin/env python3
"""Audit the Temporal Legal Engine schema and immutable evidence boundary.

Dry-run reports the reviewed contract without connecting to PostgreSQL.
Execute mode is read-only and emits aggregate counts only; source URLs, legal
texts and snapshot bytes never appear in output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import inspect, text

from core.database import engine
from legal_temporal.schema_contract import (
    EXPECTED_TABLES,
    IMMUTABLE_TABLES,
    SCHEMA_CONTRACT_SHA256,
    SCHEMA_VERSION,
    schema_contract,
)


def audit_plan() -> dict[str, object]:
    contract = schema_contract()
    return {
        "schema_version": contract["schema_version"],
        "contract_sha256": contract["contract_sha256"],
        "expected_tables": contract["expected_tables"],
        "immutable_tables": contract["immutable_tables"],
        "valid_time_bounds": contract["valid_time_bounds"],
        "system_time_strategy": contract["system_time_strategy"],
        "snapshot_strategy": contract["snapshot_strategy"],
        "execute": False,
        "database_calls_allowed": False,
        "database_writes_allowed": False,
        "full_legal_text_output_allowed": False,
    }


def _scalar(connection, sql: str) -> int:
    return int(connection.execute(text(sql)).scalar_one() or 0)


def execute_audit(
    *, expected_contract_sha256: str, max_blob_hash_checks: int
) -> dict[str, object]:
    if expected_contract_sha256 != SCHEMA_CONTRACT_SHA256:
        raise ValueError("unexpected temporal schema contract SHA-256")
    if not 0 <= max_blob_hash_checks <= 1000:
        raise ValueError("max blob hash checks must be between 0 and 1000")
    if engine.dialect.name != "postgresql":
        raise ValueError("temporal legal schema audit requires PostgreSQL")

    errors: list[str] = []
    counts: dict[str, int] = {}
    with engine.connect() as connection:
        installed_tables = set(inspect(connection).get_table_names())
        missing_tables = sorted(set(EXPECTED_TABLES) - installed_tables)
        if missing_tables:
            errors.append("missing tables: " + ",".join(missing_tables))
            return {
                "schema_version": SCHEMA_VERSION,
                "contract_sha256": SCHEMA_CONTRACT_SHA256,
                "execute": True,
                "database_writes_allowed": False,
                "missing_tables": missing_tables,
                "counts": counts,
                "error_count": len(errors),
                "errors": errors,
                "result": "fail",
            }

        installed_contract = connection.execute(
            text(
                "SELECT contract_sha256 FROM legal_temporal_schema_migrations "
                "WHERE schema_version = :schema_version"
            ),
            {"schema_version": SCHEMA_VERSION},
        ).scalar_one_or_none()
        if installed_contract != SCHEMA_CONTRACT_SHA256:
            errors.append("installed schema contract does not match code")

        trigger_rows = connection.execute(
            text(
                "SELECT event_object_table, trigger_name "
                "FROM information_schema.triggers "
                "WHERE trigger_schema = current_schema() "
                "AND event_object_table = ANY(:tables)"
            ),
            {"tables": list(EXPECTED_TABLES)},
        ).all()
        trigger_names = {(row[0], row[1]) for row in trigger_rows}
        for table in IMMUTABLE_TABLES:
            expected = (table, f"trg_{table}_immutable")
            if expected not in trigger_names:
                errors.append(f"missing immutability trigger: {table}")
        if (
            "legal_provision_versions",
            "trg_legal_provision_versions_interval",
        ) not in trigger_names:
            errors.append("missing provision interval trigger")

        for table in EXPECTED_TABLES:
            counts[table] = _scalar(connection, f"SELECT count(*) FROM {table}")

        integrity = {
            "orphan_snapshots": _scalar(
                connection,
                "SELECT count(*) FROM legal_source_snapshots s "
                "LEFT JOIN legal_source_blobs b ON b.content_sha256 = s.blob_sha256 "
                "WHERE b.content_sha256 IS NULL",
            ),
            "invalid_blob_lengths": _scalar(
                connection,
                "SELECT count(*) FROM legal_source_blobs "
                "WHERE byte_length <> octet_length(payload) OR byte_length <= 0",
            ),
            "invalid_provision_intervals": _scalar(
                connection,
                "SELECT count(*) FROM legal_provision_versions "
                "WHERE valid_to IS NOT NULL AND valid_to <= valid_from",
            ),
            "overlapping_head_intervals": _scalar(
                connection,
                "WITH heads AS ("
                " SELECT v.* FROM legal_provision_versions v"
                " WHERE NOT EXISTS ("
                "  SELECT 1 FROM legal_provision_versions s"
                "  WHERE s.supersedes_version_id = v.id"
                " )"
                ") SELECT count(*) FROM heads a JOIN heads b"
                " ON a.provision_id = b.provision_id AND a.id < b.id"
                " AND daterange(a.valid_from, COALESCE(a.valid_to, 'infinity'::date), '[)')"
                "  && daterange(b.valid_from, COALESCE(b.valid_to, 'infinity'::date), '[)')",
            ),
        }
        if any(integrity.values()):
            errors.append("temporal referential or interval integrity failed")

        blob_rows = connection.execute(
            text(
                "SELECT content_sha256, payload FROM legal_source_blobs "
                "ORDER BY content_sha256 LIMIT :limit"
            ),
            {"limit": max_blob_hash_checks},
        ).all()
        blob_hash_mismatches = sum(
            hashlib.sha256(bytes(payload)).hexdigest() != expected
            for expected, payload in blob_rows
        )
        integrity["blob_hash_mismatches"] = blob_hash_mismatches
        integrity["blob_hashes_checked"] = len(blob_rows)
        if blob_hash_mismatches:
            errors.append("immutable source blob SHA-256 mismatch")

    return {
        "schema_version": SCHEMA_VERSION,
        "contract_sha256": SCHEMA_CONTRACT_SHA256,
        "execute": True,
        "database_writes_allowed": False,
        "missing_tables": [],
        "counts": counts,
        "integrity": integrity,
        "error_count": len(errors),
        "errors": errors,
        "result": "pass" if not errors else "fail",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--expected-contract-sha256")
    parser.add_argument("--max-blob-hash-checks", type=int, default=100)
    args = parser.parse_args()

    if not args.execute:
        print("LEGAL_TEMPORAL_SCHEMA_AUDIT=" + json.dumps(audit_plan(), sort_keys=True))
        return 0
    if not args.expected_contract_sha256:
        parser.error("--execute requires --expected-contract-sha256")
    report = execute_audit(
        expected_contract_sha256=args.expected_contract_sha256,
        max_blob_hash_checks=args.max_blob_hash_checks,
    )
    print("LEGAL_TEMPORAL_SCHEMA_AUDIT=" + json.dumps(report, sort_keys=True))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
