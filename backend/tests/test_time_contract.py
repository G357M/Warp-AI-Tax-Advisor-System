"""Regression tests for the project's legacy-compatible UTC clock."""

from datetime import UTC, datetime, timedelta

from core.time_utils import utc_now


def test_utc_now_is_current_naive_utc_for_existing_database_columns():
    before = datetime.now(UTC).replace(tzinfo=None)

    actual = utc_now()

    after = datetime.now(UTC).replace(tzinfo=None)
    assert actual.tzinfo is None
    assert before <= actual <= after
    assert after - actual < timedelta(seconds=1)
