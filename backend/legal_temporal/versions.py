"""Pure and database-backed bitemporal provision-version selection."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from models.legal_temporal import LegalProvisionVersion


class TemporalVersionConflict(ValueError):
    """Raised when active head records violate the temporal contract."""


def _identity(value: Any) -> str:
    return str(value)


def _visible_versions(
    versions: Iterable[Any], as_known_at: datetime | None
) -> list[Any]:
    rows = list(versions)
    if as_known_at is not None:
        rows = [row for row in rows if row.recorded_at <= as_known_at]
    superseded_ids = {
        _identity(row.supersedes_version_id)
        for row in rows
        if row.supersedes_version_id is not None
    }
    return [row for row in rows if _identity(row.id) not in superseded_ids]


def select_provision_version(
    versions: Iterable[Any],
    *,
    as_of: date,
    as_known_at: datetime | None = None,
) -> Any | None:
    """Select the unique append-only head valid on ``as_of``.

    ``valid_to`` is exclusive.  ``as_known_at`` replays only records that the
    system had observed by that system-time timestamp.
    """
    applicable = [
        row
        for row in _visible_versions(versions, as_known_at)
        if row.valid_from <= as_of
        and (row.valid_to is None or as_of < row.valid_to)
    ]
    if len(applicable) > 1:
        raise TemporalVersionConflict(
            "multiple head versions are valid for the same provision and date"
        )
    return applicable[0] if applicable else None


def validate_non_overlapping_heads(
    versions: Iterable[Any], *, as_known_at: datetime | None = None
) -> None:
    heads = sorted(
        _visible_versions(versions, as_known_at),
        key=lambda row: (row.valid_from, row.valid_to or date.max),
    )
    previous = None
    for row in heads:
        if row.valid_to is not None and row.valid_to <= row.valid_from:
            raise TemporalVersionConflict("invalid provision valid-time interval")
        if previous is not None and (
            previous.valid_to is None or row.valid_from < previous.valid_to
        ):
            raise TemporalVersionConflict("overlapping provision head intervals")
        previous = row


def resolve_provision_version(
    db: Session,
    provision_id: object,
    *,
    as_of: date,
    as_known_at: datetime | None = None,
) -> LegalProvisionVersion | None:
    rows = (
        db.query(LegalProvisionVersion)
        .filter(LegalProvisionVersion.provision_id == provision_id)
        .order_by(LegalProvisionVersion.recorded_at.asc())
        .all()
    )
    return select_provision_version(
        rows,
        as_of=as_of,
        as_known_at=as_known_at,
    )
