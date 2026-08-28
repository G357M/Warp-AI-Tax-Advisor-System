"""Disposable-PostgreSQL integration checks for temporal schema triggers."""

from __future__ import annotations

from datetime import date, datetime
import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from core.database import engine
from legal_temporal.snapshots import prepare_snapshot, store_prepared_snapshot
from models.legal_temporal import (
    LegalAct,
    LegalActPublication,
    LegalProvision,
    LegalProvisionVersion,
)


pytestmark = pytest.mark.skipif(
    os.getenv("LEGAL_TEMPORAL_POSTGRES_TESTS") != "1",
    reason="requires the disposable CI PostgreSQL temporal-schema job",
)


def _rollback_expected_failure(db: Session, statement, params=None) -> DBAPIError:
    savepoint = db.begin_nested()
    try:
        with pytest.raises(DBAPIError) as exc_info:
            db.execute(text(statement), params or {})
        return exc_info.value
    finally:
        savepoint.rollback()


def test_postgres_enforces_immutable_evidence_and_nonoverlapping_heads():
    assert engine.dialect.name == "postgresql"
    with Session(engine) as db:
        prepared = prepare_snapshot(
            source_url="https://matsne.gov.ge/ka/document/view/1043717?publication=245",
            content=b"official-temporal-ci-fixture",
            media_type="text/html",
            captured_at=datetime(2026, 8, 28, 12, 0, 0),
        )
        stored = store_prepared_snapshot(db, prepared)
        act = LegalAct(
            canonical_key="ge:matsne:1043717:ci",
            jurisdiction="GE",
            act_type="code",
            official_title_ka="საქართველოს საგადასახადო კოდექსი",
            document_number="ci-fixture",
            canonical_source_url=prepared.source_url,
        )
        db.add(act)
        db.flush()
        publication = LegalActPublication(
            legal_act_id=act.id,
            publication_key="245-ci",
            official_url=prepared.source_url,
            source_snapshot_id=stored.snapshot_id,
            publication_date=date(2026, 8, 28),
            consolidated_as_of=date(2026, 8, 28),
            is_consolidated=True,
        )
        db.add(publication)
        db.flush()
        provision = LegalProvision(
            legal_act_id=act.id,
            stable_key="article:168:ci",
            provision_type="article",
            ordinal_path="168",
            display_label_ka="მუხლი 168",
        )
        db.add(provision)
        db.flush()
        original = LegalProvisionVersion(
            provision_id=provision.id,
            publication_id=publication.id,
            source_snapshot_id=stored.snapshot_id,
            authoritative_text_ka="საწყისი რედაქცია",
            text_sha256="1" * 64,
            valid_from=date(2020, 1, 1),
            official_locator=prepared.source_url + "#article-168",
            legal_status="in_force",
            recorded_at=datetime(2026, 8, 28, 12, 1, 0),
        )
        db.add(original)
        db.flush()

        immutable_error = _rollback_expected_failure(
            db,
            "UPDATE legal_source_blobs SET media_type = 'text/plain' "
            "WHERE content_sha256 = :sha256",
            {"sha256": prepared.content_sha256},
        )
        assert getattr(immutable_error.orig, "pgcode", None) == "55000"

        overlap_error = _rollback_expected_failure(
            db,
            "INSERT INTO legal_provision_versions "
            "(id, provision_id, publication_id, source_snapshot_id, "
            " authoritative_text_ka, text_sha256, valid_from, official_locator, "
            " legal_status, recorded_at) "
            "VALUES (:id, :provision_id, :publication_id, :snapshot_id, "
            " 'overlap', :text_sha256, DATE '2024-01-01', :locator, "
            " 'in_force', NOW())",
            {
                "id": str(uuid4()),
                "provision_id": str(provision.id),
                "publication_id": str(publication.id),
                "snapshot_id": str(stored.snapshot_id),
                "text_sha256": "2" * 64,
                "locator": prepared.source_url + "#overlap",
            },
        )
        assert getattr(overlap_error.orig, "pgcode", None) == "23P01"

        corrected = LegalProvisionVersion(
            provision_id=provision.id,
            publication_id=publication.id,
            source_snapshot_id=stored.snapshot_id,
            authoritative_text_ka="შესწორებული ისტორიული რედაქცია",
            text_sha256="3" * 64,
            valid_from=date(2020, 1, 1),
            valid_to=date(2025, 1, 1),
            official_locator=prepared.source_url + "#article-168",
            legal_status="in_force",
            recorded_at=datetime(2026, 8, 28, 12, 2, 0),
            supersedes_version_id=original.id,
            correction_reason="CI bitemporal correction fixture",
        )
        current = LegalProvisionVersion(
            provision_id=provision.id,
            publication_id=publication.id,
            source_snapshot_id=stored.snapshot_id,
            authoritative_text_ka="მოქმედი რედაქცია",
            text_sha256="4" * 64,
            valid_from=date(2025, 1, 1),
            official_locator=prepared.source_url + "#article-168-current",
            legal_status="in_force",
            recorded_at=datetime(2026, 8, 28, 12, 3, 0),
        )
        db.add(corrected)
        db.flush()
        db.add(current)
        db.flush()

        second_successor_error = _rollback_expected_failure(
            db,
            "INSERT INTO legal_provision_versions "
            "(id, provision_id, publication_id, source_snapshot_id, "
            " authoritative_text_ka, text_sha256, valid_from, valid_to, "
            " official_locator, legal_status, recorded_at, supersedes_version_id) "
            "VALUES (:id, :provision_id, :publication_id, :snapshot_id, "
            " 'second successor', :text_sha256, DATE '2020-01-01', DATE '2025-01-01', "
            " :locator, 'in_force', NOW(), :original_id)",
            {
                "id": str(uuid4()),
                "provision_id": str(provision.id),
                "publication_id": str(publication.id),
                "snapshot_id": str(stored.snapshot_id),
                "text_sha256": "5" * 64,
                "locator": prepared.source_url + "#second-successor",
                "original_id": str(original.id),
            },
        )
        assert getattr(second_successor_error.orig, "pgcode", None) in {
            "23505",
            "55000",
        }
        db.rollback()
