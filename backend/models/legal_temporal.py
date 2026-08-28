"""Normalized temporal legal-data and immutable source-evidence models."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from core.database import Base
from core.time_utils import utc_now


class LegalTemporalSchemaMigration(Base):
    __tablename__ = "legal_temporal_schema_migrations"

    schema_version = Column(Integer, primary_key=True)
    contract_sha256 = Column(String(64), nullable=False)
    applied_at = Column(DateTime, default=utc_now, nullable=False)


class LegalSourceBlob(Base):
    """Exact official bytes, addressed by SHA-256 and never mutated."""

    __tablename__ = "legal_source_blobs"

    content_sha256 = Column(String(64), primary_key=True)
    byte_length = Column(Integer, nullable=False)
    media_type = Column(String(100), nullable=False)
    payload = Column(LargeBinary, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    __table_args__ = (
        CheckConstraint("byte_length > 0", name="ck_legal_source_blob_nonempty"),
        CheckConstraint(
            "length(content_sha256) = 64",
            name="ck_legal_source_blob_sha256_length",
        ),
    )


class LegalSourceSnapshot(Base):
    """One immutable URL/content identity; repeated fetches are observations."""

    __tablename__ = "legal_source_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    source_url = Column(Text, nullable=False)
    blob_sha256 = Column(
        String(64),
        ForeignKey("legal_source_blobs.content_sha256", ondelete="RESTRICT"),
        nullable=False,
    )
    captured_at = Column(DateTime, default=utc_now, nullable=False)
    capture_method = Column(String(32), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "source_url",
            "blob_sha256",
            name="uq_legal_source_snapshot_url_blob",
        ),
    )


Index("idx_legal_source_snapshots_blob", LegalSourceSnapshot.blob_sha256)


class LegalSourceObservation(Base):
    """Append-only evidence that an official URL returned a snapshot."""

    __tablename__ = "legal_source_observations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    observation_key = Column(String(64), nullable=False, unique=True)
    snapshot_id = Column(
        UUID(as_uuid=True),
        ForeignKey("legal_source_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    observed_at = Column(DateTime, nullable=False)
    http_status = Column(Integer, nullable=True)
    etag = Column(String(512), nullable=True)
    last_modified = Column(String(255), nullable=True)
    metadata_json = Column("metadata", JSON, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "http_status IS NULL OR (http_status >= 100 AND http_status <= 599)",
            name="ck_legal_source_observation_http_status",
        ),
        CheckConstraint(
            "length(observation_key) = 64",
            name="ck_legal_source_observation_key_length",
        ),
    )


Index("idx_legal_source_observations_snapshot", LegalSourceObservation.snapshot_id)
Index("idx_legal_source_observations_time", LegalSourceObservation.observed_at)


class LegalAct(Base):
    """Stable identity of one legal act independent of its publications."""

    __tablename__ = "legal_acts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    canonical_key = Column(String(255), nullable=False, unique=True)
    jurisdiction = Column(String(16), nullable=False, default="GE")
    act_type = Column(String(50), nullable=False)
    official_title_ka = Column(Text, nullable=False)
    document_number = Column(String(100), nullable=True)
    issuing_authority = Column(String(255), nullable=True)
    canonical_source_url = Column(Text, nullable=False)
    legacy_document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )
    created_at = Column(DateTime, default=utc_now, nullable=False)


Index("idx_legal_acts_type", LegalAct.act_type)
Index("idx_legal_acts_number", LegalAct.document_number)


class LegalActPublication(Base):
    """One official publication or consolidated edition of a legal act."""

    __tablename__ = "legal_act_publications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    legal_act_id = Column(
        UUID(as_uuid=True),
        ForeignKey("legal_acts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    publication_key = Column(String(100), nullable=False)
    official_url = Column(Text, nullable=False)
    source_snapshot_id = Column(
        UUID(as_uuid=True),
        ForeignKey("legal_source_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    publication_date = Column(Date, nullable=True)
    consolidated_as_of = Column(Date, nullable=True)
    effective_from = Column(Date, nullable=True)
    effective_to = Column(Date, nullable=True)
    is_consolidated = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "legal_act_id",
            "publication_key",
            name="uq_legal_act_publication_key",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_from IS NULL OR effective_to > effective_from",
            name="ck_legal_act_publication_interval",
        ),
    )


Index("idx_legal_act_publications_act", LegalActPublication.legal_act_id)
Index("idx_legal_act_publications_effective", LegalActPublication.effective_from)


class LegalProvision(Base):
    """Stable identity of an article, part, point or subpoint."""

    __tablename__ = "legal_provisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    legal_act_id = Column(
        UUID(as_uuid=True),
        ForeignKey("legal_acts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    parent_provision_id = Column(
        UUID(as_uuid=True),
        ForeignKey("legal_provisions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    stable_key = Column(String(255), nullable=False)
    provision_type = Column(String(32), nullable=False)
    ordinal_path = Column(String(255), nullable=False)
    display_label_ka = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "legal_act_id",
            "stable_key",
            name="uq_legal_provision_stable_key",
        ),
        CheckConstraint(
            "provision_type IN ('article','part','point','subpoint','annex','note')",
            name="ck_legal_provision_type",
        ),
    )


Index("idx_legal_provisions_act", LegalProvision.legal_act_id)
Index("idx_legal_provisions_parent", LegalProvision.parent_provision_id)
Index("idx_legal_provisions_ordinal", LegalProvision.ordinal_path)


class LegalProvisionVersion(Base):
    """Append-only valid-time fact with an append-only system-time chain."""

    __tablename__ = "legal_provision_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    provision_id = Column(
        UUID(as_uuid=True),
        ForeignKey("legal_provisions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    publication_id = Column(
        UUID(as_uuid=True),
        ForeignKey("legal_act_publications.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_snapshot_id = Column(
        UUID(as_uuid=True),
        ForeignKey("legal_source_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    authoritative_text_ka = Column(Text, nullable=False)
    text_sha256 = Column(String(64), nullable=False)
    valid_from = Column(Date, nullable=False)
    valid_to = Column(Date, nullable=True)
    official_locator = Column(Text, nullable=False)
    legal_status = Column(String(24), nullable=False, default="in_force")
    recorded_at = Column(DateTime, default=utc_now, nullable=False)
    supersedes_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("legal_provision_versions.id", ondelete="RESTRICT"),
        nullable=True,
        unique=True,
    )
    correction_reason = Column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "valid_to IS NULL OR valid_to > valid_from",
            name="ck_legal_provision_version_interval",
        ),
        CheckConstraint(
            "length(text_sha256) = 64",
            name="ck_legal_provision_version_sha256_length",
        ),
        CheckConstraint(
            "legal_status IN ('in_force','suspended','repealed','not_yet_effective')",
            name="ck_legal_provision_version_status",
        ),
    )


Index("idx_legal_provision_versions_provision", LegalProvisionVersion.provision_id)
Index(
    "idx_legal_provision_versions_validity",
    LegalProvisionVersion.provision_id,
    LegalProvisionVersion.valid_from,
    LegalProvisionVersion.valid_to,
)
Index("idx_legal_provision_versions_recorded", LegalProvisionVersion.recorded_at)


class LegalAmendmentOperation(Base):
    """One structured add/replace/repeal/etc. operation from an amendment act."""

    __tablename__ = "legal_amendment_operations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    operation_key = Column(String(64), nullable=False, unique=True)
    amendment_publication_id = Column(
        UUID(as_uuid=True),
        ForeignKey("legal_act_publications.id", ondelete="RESTRICT"),
        nullable=False,
    )
    target_provision_id = Column(
        UUID(as_uuid=True),
        ForeignKey("legal_provisions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    source_snapshot_id = Column(
        UUID(as_uuid=True),
        ForeignKey("legal_source_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    operation_type = Column(String(32), nullable=False)
    effective_from = Column(Date, nullable=True)
    effective_to = Column(Date, nullable=True)
    source_locator = Column(Text, nullable=False)
    structured_payload = Column(JSON, nullable=False)
    extraction_method = Column(String(32), nullable=False)
    recorded_at = Column(DateTime, default=utc_now, nullable=False)
    supersedes_operation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("legal_amendment_operations.id", ondelete="RESTRICT"),
        nullable=True,
        unique=True,
    )

    __table_args__ = (
        CheckConstraint(
            "length(operation_key) = 64",
            name="ck_legal_amendment_operation_key_length",
        ),
        CheckConstraint(
            "operation_type IN ('add','replace','repeal','renumber','suspend','resume','transitional')",
            name="ck_legal_amendment_operation_type",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_from IS NULL OR effective_to > effective_from",
            name="ck_legal_amendment_operation_interval",
        ),
        CheckConstraint(
            "extraction_method IN ('deterministic','official_consolidation','llm_assisted','expert')",
            name="ck_legal_amendment_operation_method",
        ),
    )


Index(
    "idx_legal_amendment_operations_publication",
    LegalAmendmentOperation.amendment_publication_id,
)
Index(
    "idx_legal_amendment_operations_target",
    LegalAmendmentOperation.target_provision_id,
)
Index(
    "idx_legal_amendment_operations_effective",
    LegalAmendmentOperation.effective_from,
)


class LegalReviewEvent(Base):
    """Append-only expert/machine lifecycle event for a temporal entity."""

    __tablename__ = "legal_review_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    entity_type = Column(String(40), nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    event_type = Column(String(32), nullable=False)
    reviewer = Column(String(255), nullable=True)
    rationale = Column(Text, nullable=True)
    evidence_locator = Column(Text, nullable=True)
    recorded_at = Column(DateTime, default=utc_now, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('act','publication','provision','provision_version','amendment_operation','source_snapshot')",
            name="ck_legal_review_event_entity_type",
        ),
        CheckConstraint(
            "event_type IN ('machine_extracted','needs_review','expert_verified','published','rejected','withdrawn')",
            name="ck_legal_review_event_type",
        ),
    )


Index(
    "idx_legal_review_events_entity",
    LegalReviewEvent.entity_type,
    LegalReviewEvent.entity_id,
    LegalReviewEvent.recorded_at,
)


LEGAL_TEMPORAL_TABLES = (
    LegalTemporalSchemaMigration.__table__,
    LegalSourceBlob.__table__,
    LegalSourceSnapshot.__table__,
    LegalSourceObservation.__table__,
    LegalAct.__table__,
    LegalActPublication.__table__,
    LegalProvision.__table__,
    LegalProvisionVersion.__table__,
    LegalAmendmentOperation.__table__,
    LegalReviewEvent.__table__,
)
