#!/usr/bin/env python3
"""Deterministic, offline quality gate for multilingual RAG v2 contracts."""

from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
GOLDEN_SET_PATH = Path(__file__).with_name("rag_v2_golden_set.json")
sys.path.insert(0, str(ROOT))

from backend.rag_v2.pipeline_v2 import pipeline_v2  # noqa: E402
from backend.rag_v2.public_response import format_precise_citation  # noqa: E402


METRIC_NAMES = (
    "classification_accuracy",
    "top1_locator_recall",
    "source_audit_accuracy",
    "exact_citation_rate",
)


def _load_golden_set() -> dict[str, Any]:
    payload = json.loads(GOLDEN_SET_PATH.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported RAG golden-set schema_version")
    cases = payload.get("cases") or []
    case_ids = [case.get("id") for case in cases]
    if not cases or any(not case_id for case_id in case_ids):
        raise ValueError("RAG golden set must contain named cases")
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("RAG golden-set case ids must be unique")
    if {case.get("language") for case in cases} != {"ru", "en", "ka"}:
        raise ValueError("RAG golden set must cover ru, en and ka")
    return payload


def _ratio(passed: int, total: int) -> float:
    return round(passed / total, 4) if total else 1.0


def evaluate() -> dict[str, Any]:
    payload = _load_golden_set()
    results: list[dict[str, Any]] = []

    for case in payload["cases"]:
        failures: list[str] = []
        # The deterministic fixture intentionally has no live ``rag`` package on
        # its import path. Silence the semantic channel's expected fallback note.
        with contextlib.redirect_stdout(io.StringIO()):
            trace = pipeline_v2.build_trace(case["query"], language=case["language"])
        ranked = trace.reranking.get("top_ranked_documents") or []
        top = ranked[0] if ranked else {}
        metadata = top.get("metadata") or {}

        classification_ok = (
            trace.classification.get("question_class") == case["expected_class"]
        )
        if not classification_ok:
            failures.append("classification")

        locator_checks = []
        for expected_key, actual_value in (
            ("expected_document_type", top.get("document_type")),
            ("expected_channel", top.get("channel")),
            ("expected_document_id", top.get("document_id")),
            ("expected_article_ref", metadata.get("article_ref")),
            ("expected_point_ref", metadata.get("point_ref")),
        ):
            if expected_key in case:
                locator_checks.append(str(actual_value or "") == str(case[expected_key]))
        if "expected_title_contains" in case:
            locator_checks.append(
                case["expected_title_contains"] in str(top.get("title") or "")
            )
        for key, expected_value in (case.get("expected_metadata") or {}).items():
            locator_checks.append(metadata.get(key) == expected_value)
        locator_ok = bool(locator_checks) and all(locator_checks)
        if not locator_ok:
            failures.append("top1_locator")

        source_audit_ok = bool(trace.source_audit.get("passed")) == bool(
            case["expected_source_audit"]
        )
        if not source_audit_ok:
            failures.append("source_audit")

        citation_required = bool(case.get("require_precise_citation"))
        citation = format_precise_citation(trace) if citation_required else None
        citation_ok = True
        if citation_required:
            expected_refs = [str(case.get("expected_article_ref") or "")]
            if case.get("expected_point_ref"):
                expected_refs = str(case["expected_point_ref"]).split(".", maxsplit=1)
            citation_ok = bool(citation) and all(
                expected_ref and expected_ref in citation
                for expected_ref in expected_refs
            )
            if not citation_ok:
                failures.append("exact_citation")

        results.append(
            {
                "id": case["id"],
                "classification_ok": classification_ok,
                "locator_ok": locator_ok,
                "source_audit_ok": source_audit_ok,
                "citation_required": citation_required,
                "citation_ok": citation_ok,
                "failures": failures,
            }
        )

    citation_results = [result for result in results if result["citation_required"]]
    metrics = {
        "classification_accuracy": _ratio(
            sum(result["classification_ok"] for result in results), len(results)
        ),
        "top1_locator_recall": _ratio(
            sum(result["locator_ok"] for result in results), len(results)
        ),
        "source_audit_accuracy": _ratio(
            sum(result["source_audit_ok"] for result in results), len(results)
        ),
        "exact_citation_rate": _ratio(
            sum(result["citation_ok"] for result in citation_results),
            len(citation_results),
        ),
    }
    failed_metrics = {
        name: {"actual": metrics[name], "required": payload["thresholds"][name]}
        for name in METRIC_NAMES
        if metrics[name] < payload["thresholds"][name]
    }
    return {
        "schema_version": payload["schema_version"],
        "cases": len(results),
        "languages": sorted({case["language"] for case in payload["cases"]}),
        "metrics": metrics,
        "failed_metrics": failed_metrics,
        "failed_cases": [
            {"id": result["id"], "failures": result["failures"]}
            for result in results
            if result["failures"]
        ],
    }


def main() -> int:
    report = evaluate()
    print("RAG_V2_CONTRACT_GATE=" + json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 1 if report["failed_metrics"] or report["failed_cases"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
