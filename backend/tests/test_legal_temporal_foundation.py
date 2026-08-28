"""Contracts for the additive Temporal Legal Engine foundation."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
import re
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from legal_temporal.schema_contract import (
    EXPECTED_TABLES,
    IMMUTABLE_TABLES,
    POSTGRES_DDL,
    SCHEMA_CONTRACT_SHA256,
    SCHEMA_VERSION,
    schema_contract,
)
from legal_temporal.snapshots import (
    MAX_SNAPSHOT_BYTES,
    SnapshotValidationError,
    prepare_snapshot,
    store_prepared_snapshot,
)
from legal_temporal.versions import (
    TemporalVersionConflict,
    select_provision_version,
    validate_non_overlapping_heads,
)
from models.legal_temporal import (
    LEGAL_TEMPORAL_TABLES,
    LegalSourceBlob,
    LegalSourceObservation,
    LegalSourceSnapshot,
)
from scripts import audit_legal_temporal_schema as audit_script
from scripts import install_legal_temporal_schema as install_script


def _version(
    *,
    valid_from: date,
    valid_to: date | None,
    recorded_at: datetime,
    supersedes_version_id=None,
):
    return SimpleNamespace(
        id=uuid4(),
        valid_from=valid_from,
        valid_to=valid_to,
        recorded_at=recorded_at,
        supersedes_version_id=supersedes_version_id,
    )


def test_schema_contract_covers_models_and_append_only_guards():
    assert SCHEMA_VERSION == 1
    assert len(SCHEMA_CONTRACT_SHA256) == 64
    assert tuple(table.name for table in LEGAL_TEMPORAL_TABLES) == EXPECTED_TABLES
    assert set(IMMUTABLE_TABLES) < set(EXPECTED_TABLES)
    contract = schema_contract()
    assert contract["contract_sha256"] == SCHEMA_CONTRACT_SHA256
    assert contract["valid_time_bounds"] == "[valid_from, valid_to)"
    assert contract["system_time_strategy"] == "append-only supersedes chain"
    ddl = "\n".join(POSTGRES_DDL)
    for table in IMMUTABLE_TABLES:
        assert f"trg_{table}_immutable" in ddl
    assert "trg_legal_provision_versions_interval" in ddl
    assert "pg_advisory_xact_lock" in ddl


def test_dry_run_plans_do_not_enable_database_calls_or_backfill():
    migration = install_script.migration_plan(execute=False)
    assert migration["execute"] is False
    assert migration["additive_only"] is True
    assert migration["backfill_allowed"] is False
    assert migration["public_answer_routing_changed"] is False
    audit = audit_script.audit_plan()
    assert audit["execute"] is False
    assert audit["database_calls_allowed"] is False
    assert audit["database_writes_allowed"] is False


def test_public_runtime_does_not_implicitly_register_temporal_models():
    models_init = (
        Path(__file__).parents[1] / "models" / "__init__.py"
    ).read_text(encoding="utf-8")
    assert "legal_temporal" not in models_init


def test_prepare_snapshot_is_exact_bounded_and_official_only():
    captured = datetime(2026, 8, 28, 10, 11, 12)
    prepared = prepare_snapshot(
        source_url="https://MATSNE.gov.ge/ka/document/view/1043717?publication=245",
        content="მუხლი 168".encode(),
        media_type="text/html; charset=utf-8",
        captured_at=captured,
        etag='"official-etag"',
    )
    assert prepared.source_url.startswith("https://matsne.gov.ge/")
    assert prepared.media_type == "text/html"
    assert prepared.byte_length == len(prepared.content)
    assert len(prepared.content_sha256) == 64
    assert len(prepared.observation_key) == 64

    with pytest.raises(SnapshotValidationError, match="approved official"):
        prepare_snapshot(
            source_url="https://example.com/law",
            content=b"law",
            media_type="text/plain",
        )
    with pytest.raises(SnapshotValidationError, match="fragment"):
        prepare_snapshot(
            source_url="https://matsne.gov.ge/law#article-1",
            content=b"law",
            media_type="text/plain",
        )
    with pytest.raises(SnapshotValidationError, match="1.."):
        prepare_snapshot(
            source_url="https://matsne.gov.ge/law",
            content=b"",
            media_type="text/plain",
        )
    assert MAX_SNAPSHOT_BYTES == 64 * 1024 * 1024


def test_snapshot_store_deduplicates_bytes_url_identity_and_observation():
    engine = create_engine("sqlite://")
    tables = (
        LegalSourceBlob.__table__,
        LegalSourceSnapshot.__table__,
        LegalSourceObservation.__table__,
    )
    for table in tables:
        table.create(engine)
    try:
        captured = datetime(2026, 8, 28, 10, 11, 12)
        first = prepare_snapshot(
            source_url="https://infohubapi.rs.ge/api/document/1",
            content=b"official-json",
            media_type="application/json",
            captured_at=captured,
            capture_method="api",
            metadata={"publication": "245"},
        )
        with Session(engine) as db:
            stored_first = store_prepared_snapshot(db, first)
            stored_repeat = store_prepared_snapshot(db, first)
            second_observation = prepare_snapshot(
                source_url=first.source_url,
                content=first.content,
                media_type=first.media_type,
                captured_at=captured + timedelta(minutes=1),
                capture_method="api",
            )
            stored_second = store_prepared_snapshot(db, second_observation)
            db.commit()

            assert stored_first.reused_blob is False
            assert stored_repeat.reused_blob is True
            assert stored_repeat.reused_snapshot is True
            assert stored_repeat.reused_observation is True
            assert stored_second.reused_blob is True
            assert stored_second.reused_snapshot is True
            assert stored_second.reused_observation is False
            assert db.query(LegalSourceBlob).count() == 1
            assert db.query(LegalSourceSnapshot).count() == 1
            assert db.query(LegalSourceObservation).count() == 2
    finally:
        for table in reversed(tables):
            table.drop(engine)


def test_bitemporal_selection_replays_valid_and_system_time():
    recorded_1 = datetime(2026, 1, 1)
    recorded_2 = datetime(2026, 2, 1)
    original = _version(
        valid_from=date(2020, 1, 1),
        valid_to=None,
        recorded_at=recorded_1,
    )
    corrected = _version(
        valid_from=date(2020, 1, 1),
        valid_to=date(2025, 1, 1),
        recorded_at=recorded_2,
        supersedes_version_id=original.id,
    )
    current = _version(
        valid_from=date(2025, 1, 1),
        valid_to=None,
        recorded_at=recorded_2,
    )
    rows = [original, corrected, current]

    assert select_provision_version(
        rows, as_of=date(2024, 6, 1), as_known_at=datetime(2026, 1, 15)
    ) is original
    assert select_provision_version(rows, as_of=date(2024, 6, 1)) is corrected
    assert select_provision_version(rows, as_of=date(2025, 6, 1)) is current
    validate_non_overlapping_heads(rows)


def test_bitemporal_selection_rejects_overlapping_head_intervals():
    recorded = datetime(2026, 1, 1)
    rows = [
        _version(
            valid_from=date(2020, 1, 1),
            valid_to=date(2025, 1, 1),
            recorded_at=recorded,
        ),
        _version(
            valid_from=date(2024, 1, 1),
            valid_to=None,
            recorded_at=recorded,
        ),
    ]
    with pytest.raises(TemporalVersionConflict, match="overlapping"):
        validate_non_overlapping_heads(rows)
    with pytest.raises(TemporalVersionConflict, match="multiple head"):
        select_provision_version(rows, as_of=date(2024, 6, 1))


def test_deploy_runs_pinned_schema_install_and_read_only_audit():
    deploy = (Path(__file__).parents[2] / "scripts" / "deploy_production.sh").read_text(
        encoding="utf-8"
    )
    assert "install_legal_temporal_schema.py" in deploy
    assert "audit_legal_temporal_schema.py" in deploy
    pinned = re.search(
        r'LEGAL_TEMPORAL_SCHEMA_CONTRACT_SHA256="([0-9a-f]{64})"', deploy
    )
    assert pinned
    assert pinned.group(1) == SCHEMA_CONTRACT_SHA256
    assert deploy.index("install_legal_temporal_schema.py") < deploy.index(
        "docker compose up -d --wait --no-deps backend frontend"
    )
