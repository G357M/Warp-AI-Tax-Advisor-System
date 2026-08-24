"""Contracts for the deterministic live-corpus RAG evaluator."""

import hashlib
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from rag_v2.faq_tax_matrix import CANONICAL_TAX_CODE_SOURCE_URL
from scripts import evaluate_rag_v2_live_corpus as live_eval


def _balanced_suite():
    cases = []
    for language in ("ru", "en", "ka"):
        cases.append(
            {
                "id": f"article_{language}",
                "language": language,
                "query": f"query-{language}",
                "expected_class": "canonical_law_lookup",
                "expected_top": {
                    "document_type": "law",
                    "channel": "article_resolver",
                    "document_id_format": "uuid",
                    "metadata": {"article_ref": "168"},
                },
                "expected_source_audit": True,
                "expected_official_provision_link": True,
            }
        )
    return {
        "schema_version": 1,
        "suite_version": "test.1",
        "retrieval_profile": {
            "disabled_channels": ["semantic_search"],
            "llm_calls_allowed": False,
        },
        "thresholds": {name: 1.0 for name in live_eval.METRIC_NAMES},
        "cases": cases,
    }


class _FakePipeline:
    def __init__(self):
        self.calls = []

    def build_trace(self, query, *, language, disabled_channels):
        self.calls.append((query, language, set(disabled_channels)))
        return SimpleNamespace(
            classification={"question_class": "canonical_law_lookup"},
            reranking={
                "top_ranked_documents": [
                    {
                        "document_id": "7413ae69-672c-4c48-b3d5-8c04b09dfb43",
                        "title": "Tax Code article 168",
                        "document_type": "law",
                        "source_url": CANONICAL_TAX_CODE_SOURCE_URL,
                        "channel": "article_resolver",
                        "final_score": 1.0,
                        "metadata": {"article_ref": "168"},
                    }
                ]
            },
            source_audit={"passed": True, "warnings": []},
        )


def test_default_live_suite_is_balanced_and_prohibits_llm_calls():
    suite = live_eval.load_suite()

    assert len(suite["cases"]) == 63
    assert {case["language"] for case in suite["cases"]} == {"ru", "en", "ka"}
    assert suite["retrieval_profile"]["llm_calls_allowed"] is False
    assert "semantic_search" in suite["retrieval_profile"]["disabled_channels"]


def test_committed_baseline_matches_the_versioned_suite_and_is_aggregate_only():
    suite = live_eval.load_suite()
    suite_bytes = json.dumps(
        suite, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    baseline_path = (
        live_eval.BACKEND_ROOT.parent
        / "evaluation"
        / "baselines"
        / "rag_v2_live_corpus_2026-08-24_provision-links.json"
    )
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))

    assert baseline["suite_sha256"] == hashlib.sha256(suite_bytes).hexdigest()
    assert baseline["suite_version"] == suite["suite_version"]
    assert baseline["passed_cases"] == baseline["cases"] == 63
    assert baseline["metrics"]["official_provision_link_rate"] == 1.0
    assert "results" not in baseline
    assert "query" not in json.dumps(baseline)


def test_live_evaluator_uses_db_and_disables_semantic_channel(monkeypatch):
    fake_pipeline = _FakePipeline()
    monkeypatch.setattr(
        live_eval,
        "db_status",
        lambda: {"mode": "db", "driver": "psycopg2", "connectable": True},
    )
    monkeypatch.setattr(
        live_eval,
        "run_query",
        lambda _sql: [
            {
                "total_documents": 10,
                "total_chunks": 20,
                "court_decisions": 3,
                "decision_facts": 2,
                "latest_document_update": datetime(2026, 8, 20, tzinfo=timezone.utc),
            }
        ],
    )
    monkeypatch.setattr(live_eval, "pipeline_v2", fake_pipeline)

    report = live_eval.evaluate(
        _balanced_suite(),
        deployed_commit="a" * 40,
        generated_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
    )

    assert report["passed_cases"] == 3
    assert all(value == 1.0 for value in report["metrics"].values())
    assert report["corpus"]["latest_document_update"] == "2026-08-20T00:00:00+00:00"
    assert all(call[2] == {"semantic_search"} for call in fake_pipeline.calls)

    baseline = live_eval.baseline_summary(report)
    assert "results" not in baseline
    assert baseline["metrics"] == report["metrics"]
    assert set(baseline) == set(live_eval.BASELINE_FIELDS)


def test_live_evaluator_refuses_fixture_or_disconnected_mode(monkeypatch):
    monkeypatch.setattr(
        live_eval,
        "db_status",
        lambda: {"mode": "fixtures", "driver": None, "connectable": False},
    )

    with pytest.raises(RuntimeError, match="requires INFOHUB_V2_BACKEND_MODE=db"):
        live_eval.evaluate(_balanced_suite())
