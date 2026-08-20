"""UTC time helpers compatible with the database's existing naive columns."""

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return naive UTC without using the deprecated ``datetime.utcnow`` API.

    Production columns currently use ``timestamp without time zone``. Dropping
    ``tzinfo`` only after constructing an aware UTC value preserves that schema
    contract until a dedicated timezone-aware database migration is planned.
    """
    return datetime.now(UTC).replace(tzinfo=None)
