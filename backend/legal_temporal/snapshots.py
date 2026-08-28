"""Prepare and persist immutable official-source snapshots without fetching."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy.orm import Session

from core.time_utils import utc_now
from models.legal_temporal import (
    LegalSourceBlob,
    LegalSourceObservation,
    LegalSourceSnapshot,
)


OFFICIAL_SOURCE_HOSTS = frozenset(
    {
        "matsne.gov.ge",
        "new.matsne.gov.ge",
        "infohub.rs.ge",
        "infohubapi.rs.ge",
    }
)
ALLOWED_CAPTURE_METHODS = frozenset({"http", "api", "manual", "legacy_backfill"})
MAX_SNAPSHOT_BYTES = 64 * 1024 * 1024


class SnapshotValidationError(ValueError):
    """Raised before untrusted source content reaches persistence."""


@dataclass(frozen=True)
class PreparedSnapshot:
    source_url: str
    content: bytes
    content_sha256: str
    byte_length: int
    media_type: str
    captured_at: datetime
    capture_method: str
    http_status: int | None
    etag: str | None
    last_modified: str | None
    metadata: dict[str, Any]
    observation_key: str


@dataclass(frozen=True)
class StoredSnapshot:
    snapshot_id: object
    observation_id: object
    content_sha256: str
    reused_blob: bool
    reused_snapshot: bool
    reused_observation: bool


def _naive_utc(value: datetime | None) -> datetime:
    if value is None:
        return utc_now()
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


def normalize_official_source_url(value: str) -> str:
    raw = str(value or "").strip()
    if not raw or len(raw) > 4096:
        raise SnapshotValidationError("official source URL is missing or too long")
    parsed = urlsplit(raw)
    host = (parsed.hostname or "").lower()
    if parsed.fragment:
        raise SnapshotValidationError(
            "official source snapshot URL must not contain a fragment"
        )
    if (
        parsed.scheme.lower() != "https"
        or host not in OFFICIAL_SOURCE_HOSTS
        or parsed.username
        or parsed.password
        or parsed.port not in {None, 443}
        or not parsed.path.startswith("/")
    ):
        raise SnapshotValidationError("source URL must be an approved official HTTPS URL")
    return urlunsplit(("https", host, parsed.path, parsed.query, ""))


def _bounded_header(value: str | None, field: str, limit: int) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    if not cleaned:
        return None
    if len(cleaned) > limit or "\r" in cleaned or "\n" in cleaned:
        raise SnapshotValidationError(f"invalid {field}")
    return cleaned


def prepare_snapshot(
    *,
    source_url: str,
    content: bytes,
    media_type: str,
    captured_at: datetime | None = None,
    capture_method: str = "http",
    http_status: int | None = 200,
    etag: str | None = None,
    last_modified: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> PreparedSnapshot:
    normalized_url = normalize_official_source_url(source_url)
    if not isinstance(content, bytes):
        raise SnapshotValidationError("snapshot content must be bytes")
    if not content or len(content) > MAX_SNAPSHOT_BYTES:
        raise SnapshotValidationError(
            f"snapshot content must contain 1..{MAX_SNAPSHOT_BYTES} bytes"
        )
    normalized_media_type = str(media_type or "").split(";", 1)[0].strip().lower()
    if not normalized_media_type or len(normalized_media_type) > 100:
        raise SnapshotValidationError("snapshot media type is missing or too long")
    if capture_method not in ALLOWED_CAPTURE_METHODS:
        raise SnapshotValidationError("unsupported snapshot capture method")
    if http_status is not None and not 100 <= int(http_status) <= 599:
        raise SnapshotValidationError("HTTP status must be between 100 and 599")
    if metadata is not None and not isinstance(metadata, dict):
        raise SnapshotValidationError("snapshot metadata must be an object")

    observed_at = _naive_utc(captured_at)
    sha256 = hashlib.sha256(content).hexdigest()
    clean_etag = _bounded_header(etag, "etag", 512)
    clean_last_modified = _bounded_header(last_modified, "last_modified", 255)
    safe_metadata = dict(metadata or {})
    observation_material = {
        "source_url": normalized_url,
        "content_sha256": sha256,
        "observed_at": observed_at.isoformat(timespec="microseconds"),
        "http_status": http_status,
        "etag": clean_etag,
        "last_modified": clean_last_modified,
    }
    observation_key = hashlib.sha256(
        json.dumps(
            observation_material,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return PreparedSnapshot(
        source_url=normalized_url,
        content=content,
        content_sha256=sha256,
        byte_length=len(content),
        media_type=normalized_media_type,
        captured_at=observed_at,
        capture_method=capture_method,
        http_status=http_status,
        etag=clean_etag,
        last_modified=clean_last_modified,
        metadata=safe_metadata,
        observation_key=observation_key,
    )


def store_prepared_snapshot(db: Session, prepared: PreparedSnapshot) -> StoredSnapshot:
    """Store one prepared snapshot without committing the caller's transaction."""
    blob = db.get(LegalSourceBlob, prepared.content_sha256)
    reused_blob = blob is not None
    if blob is None:
        blob = LegalSourceBlob(
            content_sha256=prepared.content_sha256,
            byte_length=prepared.byte_length,
            media_type=prepared.media_type,
            payload=prepared.content,
            created_at=prepared.captured_at,
        )
        db.add(blob)
        db.flush()
    elif (
        blob.byte_length != prepared.byte_length
        or blob.media_type != prepared.media_type
        or bytes(blob.payload) != prepared.content
    ):
        raise SnapshotValidationError(
            "stored content or media type does not match its SHA-256 identity"
        )

    snapshot = (
        db.query(LegalSourceSnapshot)
        .filter(
            LegalSourceSnapshot.source_url == prepared.source_url,
            LegalSourceSnapshot.blob_sha256 == prepared.content_sha256,
        )
        .one_or_none()
    )
    reused_snapshot = snapshot is not None
    if snapshot is None:
        snapshot = LegalSourceSnapshot(
            source_url=prepared.source_url,
            blob_sha256=prepared.content_sha256,
            captured_at=prepared.captured_at,
            capture_method=prepared.capture_method,
        )
        db.add(snapshot)
        db.flush()

    observation = (
        db.query(LegalSourceObservation)
        .filter(LegalSourceObservation.observation_key == prepared.observation_key)
        .one_or_none()
    )
    reused_observation = observation is not None
    if observation is None:
        observation = LegalSourceObservation(
            observation_key=prepared.observation_key,
            snapshot_id=snapshot.id,
            observed_at=prepared.captured_at,
            http_status=prepared.http_status,
            etag=prepared.etag,
            last_modified=prepared.last_modified,
            metadata_json=prepared.metadata,
        )
        db.add(observation)
        db.flush()

    return StoredSnapshot(
        snapshot_id=snapshot.id,
        observation_id=observation.id,
        content_sha256=prepared.content_sha256,
        reused_blob=reused_blob,
        reused_snapshot=reused_snapshot,
        reused_observation=reused_observation,
    )
