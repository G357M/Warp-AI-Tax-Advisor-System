#!/usr/bin/env python
"""Evaluate deterministic RAG v2 locators against the connected live corpus.

The suite explicitly disables semantic retrieval. It therefore performs no LLM
translation or answer-generation calls and never writes to PostgreSQL.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SUITE_PATH = BACKEND_ROOT / "evaluation" / "rag_v2_live_corpus_set.json"
sys.path.insert(0, str(BACKEND_ROOT))

from rag_v2.db_utils import db_status, run_query  # noqa: E402
from rag_v2.official_provisions import enrich_source, has_official_provision_link  # noqa: E402
from rag_v2.pipeline_v2 import pipeline_v2  # noqa: E402


METRIC_NAMES = (
    "classification_accuracy",
    "top1_contract_recall",
    "source_audit_rate",
    "official_provision_link_rate",
    "min_language_contract_recall",
)

BASELINE_FIELDS = (
    "schema_version",
    "suite_version",
    "suite_sha256",
    "generated_at_utc",
    "deployed_commit",
    "backend",
    "retrieval_profile",
    "corpus",
    "cases",
    "passed_cases",
    "failed_cases",
    "metrics",
    "language_metrics",
    "failed_metrics",
)

CORPUS_SNAPSHOT_SQL = """
SELECT
  (SELECT count(*) FROM documents) AS total_documents,
  (SELECT count(*) FROM document_chunks) AS total_chunks,
  (SELECT count(*) FROM documents WHERE document_type = 'court_decision')
    AS court_decisions,
  (SELECT count(*) FROM decision_facts) AS decision_facts,
  (SELECT max(updated_at) FROM documents) AS latest_document_update
"""


def load_suite(path: Path = DEFAULT_SUITE_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported live-corpus suite schema_version")
    if not payload.get("suite_version"):
        raise ValueError("live-corpus suite_version is required")
    if set(payload.get("thresholds") or {}) != set(METRIC_NAMES):
        raise ValueError("live-corpus suite thresholds do not match evaluator metrics")
    if payload.get("retrieval_profile", {}).get("llm_calls_allowed") is not False:
        raise ValueError("live-corpus suite must explicitly prohibit LLM calls")
    disabled = set(payload.get("retrieval_profile", {}).get("disabled_channels") or [])
    if "semantic_search" not in disabled:
        raise ValueError("semantic_search must be disabled for the no-LLM live suite")

    cases = payload.get("cases") or []
    ids = [case.get("id") for case in cases]
    if not cases or any(not case_id for case_id in ids) or len(ids) != len(set(ids)):
        raise ValueError("live-corpus suite cases must have unique non-empty ids")
    language_counts = {
        language: sum(case.get("language") == language for case in cases)
        for language in ("ru", "en", "ka")
    }
    if len(set(language_counts.values())) != 1 or not all(language_counts.values()):
        raise ValueError("live-corpus suite must balance ru, en and ka cases")
    return payload


def _ratio(passed: int, total: int) -> float:
    return round(passed / total, 4) if total else 1.0


def _is_uuid(value: Any) -> bool:
    try:
        uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return False
    return True


def _top_contract(case: dict[str, Any], top: dict[str, Any]) -> tuple[bool, list[str]]:
    expected = case["expected_top"]
    failures: list[str] = []
    for field in ("document_type", "channel", "document_id"):
        if field in expected and str(top.get(field) or "") != str(expected[field]):
            failures.append(f"top.{field}")

    if "channel_any_of" in expected and top.get("channel") not in expected["channel_any_of"]:
        failures.append("top.channel")
    title = str(top.get("title") or "")
    if any(part not in title for part in expected.get("title_contains_all") or []):
        failures.append("top.title")
    if expected.get("document_id_format") == "uuid" and not _is_uuid(top.get("document_id")):
        failures.append("top.document_id_format")

    metadata = top.get("metadata") or {}
    for key, value in (expected.get("metadata") or {}).items():
        if metadata.get(key) != value:
            failures.append(f"top.metadata.{key}")
    return not failures, failures


def _corpus_snapshot() -> dict[str, Any]:
    rows = run_query(CORPUS_SNAPSHOT_SQL)
    if len(rows) != 1:
        raise RuntimeError("live corpus fingerprint query returned an unexpected shape")
    snapshot = dict(rows[0])
    for key, value in list(snapshot.items()):
        if isinstance(value, datetime):
            snapshot[key] = value.isoformat()
    return snapshot


def evaluate(
    suite: dict[str, Any],
    *,
    deployed_commit: str = "unknown",
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    backend = db_status()
    if backend.get("mode") != "db" or not backend.get("connectable"):
        raise RuntimeError(
            "live-corpus evaluation requires INFOHUB_V2_BACKEND_MODE=db "
            "and a connectable explicit database URL"
        )

    disabled_channels = set(
        suite.get("retrieval_profile", {}).get("disabled_channels") or []
    )
    results: list[dict[str, Any]] = []
    for case in suite["cases"]:
        trace = pipeline_v2.build_trace(
            case["query"],
            language=case["language"],
            disabled_channels=disabled_channels,
        )
        ranked = trace.reranking.get("top_ranked_documents") or []
        top = ranked[0] if ranked else {}
        classification_ok = (
            trace.classification.get("question_class") == case["expected_class"]
        )
        top1_ok, top_failures = _top_contract(case, top)
        source_audit_ok = bool(trace.source_audit.get("passed")) == bool(
            case["expected_source_audit"]
        )
        provision_link_expected = bool(case.get("expected_official_provision_link"))
        enriched_source = enrich_source(
            {
                "url": top.get("source_url"),
                "source_url": top.get("source_url"),
                "article_ref": (top.get("metadata") or {}).get("article_ref"),
                "point_ref": (top.get("metadata") or {}).get("point_ref"),
            }
        )
        provision_link_ok = (
            has_official_provision_link(enriched_source)
            if provision_link_expected
            else True
        )
        failures = list(top_failures)
        if not classification_ok:
            failures.insert(0, "classification")
        if not source_audit_ok:
            failures.append("source_audit")
        if not provision_link_ok:
            failures.append("official_provision_link")

        results.append(
            {
                "id": case["id"],
                "language": case["language"],
                "query": case["query"],
                "classification_ok": classification_ok,
                "top1_contract_ok": top1_ok,
                "source_audit_ok": source_audit_ok,
                "provision_link_expected": provision_link_expected,
                "provision_link_ok": provision_link_ok,
                "success": not failures,
                "failures": failures,
                "actual": {
                    "question_class": trace.classification.get("question_class"),
                    "top_document_id": top.get("document_id"),
                    "top_title": top.get("title"),
                    "top_document_type": top.get("document_type"),
                    "top_channel": top.get("channel"),
                    "top_score": top.get("final_score"),
                    "top_metadata": {
                        key: (top.get("metadata") or {}).get(key)
                        for key in (
                            "article_ref",
                            "point_ref",
                            "document_number",
                            "is_current",
                        )
                    },
                    "source_audit_passed": trace.source_audit.get("passed"),
                    "source_audit_warnings": trace.source_audit.get("warnings") or [],
                    "official_provision_urls": [
                        link["url"]
                        for link in enriched_source.get("provision_links") or []
                    ],
                },
            }
        )

    metrics = {
        "classification_accuracy": _ratio(
            sum(item["classification_ok"] for item in results), len(results)
        ),
        "top1_contract_recall": _ratio(
            sum(item["top1_contract_ok"] for item in results), len(results)
        ),
        "source_audit_rate": _ratio(
            sum(item["source_audit_ok"] for item in results), len(results)
        ),
        "official_provision_link_rate": _ratio(
            sum(
                item["provision_link_ok"]
                for item in results
                if item["provision_link_expected"]
            ),
            sum(item["provision_link_expected"] for item in results),
        ),
    }
    language_metrics = {}
    for language in ("ru", "en", "ka"):
        selected = [item for item in results if item["language"] == language]
        language_metrics[language] = {
            "cases": len(selected),
            "classification_accuracy": _ratio(
                sum(item["classification_ok"] for item in selected), len(selected)
            ),
            "top1_contract_recall": _ratio(
                sum(item["top1_contract_ok"] for item in selected), len(selected)
            ),
            "source_audit_rate": _ratio(
                sum(item["source_audit_ok"] for item in selected), len(selected)
            ),
            "official_provision_link_rate": _ratio(
                sum(
                    item["provision_link_ok"]
                    for item in selected
                    if item["provision_link_expected"]
                ),
                sum(item["provision_link_expected"] for item in selected),
            ),
        }
    metrics["min_language_contract_recall"] = min(
        item["top1_contract_recall"] for item in language_metrics.values()
    )
    failed_metrics = {
        name: {"actual": metrics[name], "required": suite["thresholds"][name]}
        for name in METRIC_NAMES
        if metrics[name] < suite["thresholds"][name]
    }
    generated_at = generated_at or datetime.now(timezone.utc)
    suite_bytes = json.dumps(
        suite, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")

    return {
        "schema_version": 1,
        "suite_version": suite["suite_version"],
        "suite_sha256": hashlib.sha256(suite_bytes).hexdigest(),
        "generated_at_utc": generated_at.astimezone(timezone.utc).isoformat(),
        "deployed_commit": deployed_commit,
        "backend": {
            "mode": backend.get("mode"),
            "driver": backend.get("driver"),
            "connectable": backend.get("connectable"),
        },
        "retrieval_profile": suite["retrieval_profile"],
        "corpus": _corpus_snapshot(),
        "cases": len(results),
        "passed_cases": sum(item["success"] for item in results),
        "failed_cases": [
            {"id": item["id"], "failures": item["failures"]}
            for item in results
            if not item["success"]
        ],
        "metrics": metrics,
        "language_metrics": language_metrics,
        "failed_metrics": failed_metrics,
        "results": results,
    }


def baseline_summary(report: dict[str, Any]) -> dict[str, Any]:
    """Return the secret-safe aggregate artifact suitable for Git history."""
    return {key: report[key] for key in BASELINE_FIELDS}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE_PATH)
    parser.add_argument("--commit", default="unknown")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--baseline-output", type=Path)
    args = parser.parse_args()

    suite = load_suite(args.suite)
    report = evaluate(suite, deployed_commit=args.commit)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Saved live-corpus report: {args.output}")
    if args.baseline_output:
        args.baseline_output.parent.mkdir(parents=True, exist_ok=True)
        args.baseline_output.write_text(
            json.dumps(baseline_summary(report), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Saved aggregate baseline: {args.baseline_output}")

    summary = {
        "suite_version": report["suite_version"],
        "deployed_commit": report["deployed_commit"],
        "cases": report["cases"],
        "passed_cases": report["passed_cases"],
        "metrics": report["metrics"],
        "failed_cases": report["failed_cases"],
        "failed_metrics": report["failed_metrics"],
    }
    print("RAG_V2_LIVE_CORPUS_EVAL=" + json.dumps(summary, sort_keys=True))
    return 1 if report["failed_cases"] or report["failed_metrics"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
