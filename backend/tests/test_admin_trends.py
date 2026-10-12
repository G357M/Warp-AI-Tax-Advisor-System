"""Admin trends: Tbilisi-local bucket windows (no database)."""
from datetime import date, datetime
from pathlib import Path

from core.admin_trends import window

NOW = datetime(2026, 10, 12, 10, 0)  # 14:00 in Tbilisi, a Monday


def test_day_window():
    w = window("30d", NOW)
    assert w.bucket == "day" and len(w.starts) == 30
    assert w.starts[0] == date(2026, 9, 13) and w.starts[-1] == date(2026, 10, 12)
    assert w.end == date(2026, 10, 13) and w.previous_start == date(2026, 8, 14)


def test_local_midnight_moves_the_day():
    assert window("30d", datetime(2026, 10, 11, 20, 30)).starts[-1] == date(2026, 10, 12)
    assert window("30d", datetime(2026, 10, 11, 19, 59)).starts[-1] == date(2026, 10, 11)


def test_week_window_starts_monday():
    w = window("90d", datetime(2026, 10, 15, 10, 0))
    assert w.bucket == "week" and len(w.starts) == 13
    assert w.starts[-1] == date(2026, 10, 12) and w.starts[0] == date(2026, 7, 20)
    assert all(s.weekday() == 0 for s in w.starts)


def test_month_window():
    w = window("12m", NOW)
    assert w.bucket == "month" and len(w.starts) == 12
    assert w.starts[0] == date(2025, 11, 1) and w.starts[-1] == date(2026, 10, 1)
    assert w.end == date(2026, 11, 1) and w.previous_start == date(2024, 11, 1)


def test_month_window_crosses_year_start():
    w = window("12m", datetime(2027, 1, 5, 10, 0))
    assert w.starts[0] == date(2026, 2, 1) and w.starts[-1] == date(2027, 1, 1)
    assert w.end == date(2027, 2, 1)


def test_router_requires_admin():
    source = (Path(__file__).parents[1] / "api" / "routes" / "admin_trends.py").read_text(encoding="utf-8")
    assert "dependencies=[Depends(require_admin)]" in source
