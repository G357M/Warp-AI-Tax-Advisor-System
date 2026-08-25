"""Contracts for source-to-corpus ingestion freshness monitoring."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPOSITORY_ROOT / "scripts" / "audit_ingestion_freshness.py"
SPEC = importlib.util.spec_from_file_location("audit_ingestion_freshness", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _summary(*, source_total=100, ingested=0, detail_failures=0, processing_errors=0):
    return {
        "documents_scraped": ingested,
        "species": {
            "NewDocument": {
                "source_total": source_total,
                "pages_visited": 1,
                "known": 50,
                "unseen": ingested,
                "ingested": ingested,
                "skipped_short": 0,
                "detail_failures": detail_failures,
                "processing_errors": processing_errors,
            }
        },
    }


def _evaluate(summary, previous):
    return MODULE.evaluate_freshness(
        summary,
        previous,
        evaluated_at=datetime(2026, 8, 25, 3, 5, tzinfo=timezone.utc),
    )


def test_first_valid_run_establishes_a_non_alerting_baseline():
    report, state = _evaluate(_summary(), {})

    assert report["status"] == "baseline"
    assert report["violations"] == []
    assert report["species"]["NewDocument"]["source_delta"] is None
    assert state["species"]["NewDocument"]["source_total"] == 100


def test_catalog_growth_with_ingestion_is_healthy():
    report, _ = _evaluate(_summary(source_total=101, ingested=1), {"NewDocument": 100})

    assert report["status"] == "healthy"
    assert report["species"]["NewDocument"]["source_delta"] == 1
    assert report["violations"] == []


def test_catalog_growth_without_ingestion_is_a_warning():
    report, state = _evaluate(_summary(source_total=101), {"NewDocument": 100})

    assert report["status"] == "warning"
    assert report["violations"] == ["NewDocument:source_grew_without_ingest"]
    assert state["species"]["NewDocument"]["source_total"] == 101


@pytest.mark.parametrize(
    ("overrides", "violation"),
    [
        ({"detail_failures": 2}, "NewDocument:detail_failures"),
        ({"processing_errors": 1}, "NewDocument:processing_errors"),
    ],
)
def test_silent_processing_failures_are_warnings(overrides, violation):
    report, _ = _evaluate(_summary(**overrides), {"NewDocument": 100})

    assert violation in report["violations"]


def test_official_total_decrease_is_reported_as_an_anomaly():
    report, state = _evaluate(_summary(source_total=99), {"NewDocument": 100})

    assert report["violations"] == ["NewDocument:source_total_decreased"]
    assert state["species"]["NewDocument"]["source_total"] == 100


def test_unavailable_source_does_not_poison_the_last_good_baseline():
    summary = _summary(source_total=0)
    summary["species"]["NewDocument"]["pages_visited"] = 0

    report, state = _evaluate(summary, {"NewDocument": 100})

    assert "NewDocument:source_unavailable" in report["violations"]
    assert state["species"]["NewDocument"]["source_total"] == 100


def test_summary_parser_rejects_inconsistent_ingested_total():
    raw = _summary(ingested=1)
    raw["documents_scraped"] = 0

    with pytest.raises(MODULE.FreshnessAuditError, match="does not match"):
        MODULE.parse_summary_line(
            MODULE.SUMMARY_PREFIX + json.dumps(raw, separators=(",", ":"))
        )


@pytest.mark.skipif(
    os.name == "nt",
    reason="authoritative chmod/state-file contract runs on Linux CI",
)
def test_state_round_trip_is_aggregate_only(tmp_path):
    path = tmp_path / "freshness.json"
    _, state = _evaluate(_summary(), {})

    MODULE.write_state(path, state)

    assert MODULE.read_state(path) == {"NewDocument": 100}
    persisted = path.read_text(encoding="utf-8")
    assert "source_total" in persisted
    assert "title" not in persisted
    assert "source_url" not in persisted


def test_nightly_runner_uses_only_the_machine_summary_for_alerting():
    runner = (REPOSITORY_ROOT / "run_scraper.sh").read_text(encoding="utf-8")

    assert "audit_ingestion_freshness.py" in runner
    assert "INFOHUB_INGEST_FRESHNESS=" in runner
    assert '"ingestion freshness audit" "$FRESHNESS_SUMMARY"' in runner
    assert '"ingestion freshness audit" "$FRESHNESS_OUT"' not in runner
    assert "FRESHNESS_EXIT" in runner
    assert "exit $EXIT_CODE" in runner
