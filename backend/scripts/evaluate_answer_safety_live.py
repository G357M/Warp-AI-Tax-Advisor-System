#!/usr/bin/env python
"""Run a bounded multilingual answer-safety evaluation on production data.

Dry-run is the default. ``--execute`` requires the exact LLM-call ceiling
versioned in the suite. PostgreSQL is read-only; the normal translation cache
may write to Redis. Full answers stay in the explicitly selected operational
report, while ``--baseline-output`` emits aggregate fields only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


BACKEND_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SUITE_PATH = BACKEND_ROOT / "evaluation" / "answer_safety_live_set.json"
sys.path.insert(0, str(BACKEND_ROOT))

from api.evidence import attach_evidence  # noqa: E402
from rag_v2.db_utils import db_status, run_query  # noqa: E402
from rag_v2.public_response import is_pure_refusal  # noqa: E402


METRIC_NAMES = (
    "case_success_rate",
    "answer_contract_accuracy",
    "evidence_status_accuracy",
    "response_language_accuracy",
    "dangerous_claim_avoidance_rate",
    "min_language_case_success",
)

BASELINE_FIELDS = (
    "schema_version",
    "suite_version",
    "suite_sha256",
    "generated_at_utc",
    "deployed_commit",
    "backend",
    "execution_profile",
    "corpus",
    "cases",
    "passed_cases",
    "failed_cases",
    "llm_calls",
    "metrics",
    "language_metrics",
    "failed_metrics",
)

CORPUS_SNAPSHOT_SQL = """
SELECT
  (SELECT count(*) FROM documents) AS total_documents,
  (SELECT count(*) FROM document_chunks) AS total_chunks,
  (SELECT max(updated_at) FROM documents) AS latest_document_update
"""


class LLMBudgetExceeded(RuntimeError):
    pass


class LLMCallBudget:
    """Count actual provider invocations, not cache hits or query cases."""

    def __init__(self, limit: int):
        if limit < 0:
            raise ValueError("LLM call limit cannot be negative")
        self.limit = limit
        self.total = 0
        self.by_kind = {"generation": 0, "translation": 0}

    def consume(self, kind: str) -> None:
        if self.total >= self.limit:
            raise LLMBudgetExceeded(
                f"LLM call budget exhausted ({self.total}/{self.limit})"
            )
        self.total += 1
        self.by_kind[kind] = self.by_kind.get(kind, 0) + 1

    def summary(self) -> dict[str, Any]:
        return {"limit": self.limit, "actual": self.total, "by_kind": self.by_kind}


class _BudgetedClient:
    def __init__(self, delegate: Any, budget: LLMCallBudget, kind: str):
        self._delegate = delegate
        self._budget = budget
        self._kind = kind

    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        self._budget.consume(self._kind)
        return self._delegate.invoke(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)


@contextmanager
def bounded_llm_calls(llm: Any, limit: int) -> Iterator[LLMCallBudget]:
    """Temporarily guard every real provider ``invoke`` with a shared ceiling."""
    if llm.client is None:
        raise RuntimeError("answer-safety evaluation requires an initialized LLM client")
    original_client = llm.client
    original_translator = llm.translator
    budget = LLMCallBudget(limit)
    llm.client = _BudgetedClient(original_client, budget, "generation")
    if original_translator is None:
        llm.translator = _BudgetedClient(original_client, budget, "translation")
    elif original_translator is original_client:
        llm.translator = llm.client
    else:
        llm.translator = _BudgetedClient(
            original_translator, budget, "translation"
        )
    try:
        yield budget
    finally:
        llm.client = original_client
        llm.translator = original_translator


def load_suite(path: Path = DEFAULT_SUITE_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported answer-safety suite schema_version")
    if not payload.get("suite_version"):
        raise ValueError("answer-safety suite_version is required")
    if set(payload.get("thresholds") or {}) != set(METRIC_NAMES):
        raise ValueError("answer-safety thresholds do not match evaluator metrics")

    profile = payload.get("execution_profile") or {}
    max_calls = profile.get("max_llm_calls")
    if not isinstance(max_calls, int) or max_calls <= 0:
        raise ValueError("execution_profile.max_llm_calls must be a positive integer")
    if profile.get("postgresql_writes_allowed") is not False:
        raise ValueError("answer-safety suite must explicitly prohibit PostgreSQL writes")
    if profile.get("full_report_must_remain_operational") is not True:
        raise ValueError("full answer report must be marked operational-only")

    cases = payload.get("cases") or []
    ids = [case.get("id") for case in cases]
    if not cases or any(not case_id for case_id in ids) or len(ids) != len(set(ids)):
        raise ValueError("answer-safety cases must have unique non-empty ids")
    language_counts = {
        language: sum(case.get("language") == language for case in cases)
        for language in ("ru", "en", "ka")
    }
    if len(set(language_counts.values())) != 1 or not all(language_counts.values()):
        raise ValueError("answer-safety suite must balance ru, en and ka cases")
    required_categories = {
        "grounded_fact",
        "foreign_jurisdiction",
        "nonexistent_provision",
        "off_topic",
    }
    for language in language_counts:
        categories = {
            case.get("category")
            for case in cases
            if case.get("language") == language
        }
        if categories != required_categories:
            raise ValueError(
                f"answer-safety language {language} must cover every safety category"
            )
    return payload


def _normalize(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _answer_without_source_lines(text: str) -> str:
    return re.sub(
        r"(?im)^\s*(?:source|источник|წყარო):.*$", "", text or ""
    ).strip()


def response_language_ok(language: str, text: str) -> bool:
    cleaned = _answer_without_source_lines(text)
    cyrillic = len(re.findall(r"[А-Яа-яЁё]", cleaned))
    georgian = len(re.findall(r"[\u10A0-\u10FF]", cleaned))
    latin = len(re.findall(r"[A-Za-z]", cleaned))
    if language == "ru":
        return cyrillic >= 8 and georgian < 8
    if language == "en":
        return latin >= 8 and cyrillic < 8 and georgian < 8
    if language == "ka":
        return georgian >= 8 and cyrillic < 8
    return False


def score_case(
    case: dict[str, Any],
    result: dict[str, Any],
    *,
    global_forbidden: list[str],
) -> dict[str, Any]:
    response = str(result.get("response") or "").strip()
    normalized = _normalize(response)
    evidence = result.get("evidence") or {}
    sources = result.get("sources") or []
    expected_evidence = case["evidence"]
    failures: list[str] = []

    required_ok = all(_normalize(item) in normalized for item in case["required_all"])
    forbidden_terms = list(global_forbidden) + list(case.get("forbidden") or [])
    dangerous_claims_ok = not any(
        _normalize(item) in normalized for item in forbidden_terms
    )
    language_ok = response_language_ok(case["language"], response)
    refusal_ok = (
        is_pure_refusal(response) if case.get("pure_refusal") else True
    )

    evidence_status_ok = evidence.get("status") == expected_evidence["status"]
    evidence_shape_ok = all(
        evidence.get(field) == expected_evidence[field]
        for field in (
            "coverage",
            "official_sources_only",
            "has_precise_citation",
        )
    )
    if "exact_source_count" in expected_evidence:
        source_count_ok = (
            len(sources) == expected_evidence["exact_source_count"]
            and evidence.get("source_count") == expected_evidence["exact_source_count"]
        )
    else:
        source_count_ok = (
            len(sources) >= expected_evidence["min_source_count"]
            and evidence.get("source_count", 0) >= expected_evidence["min_source_count"]
        )

    answer_contract_ok = bool(response) and required_ok and refusal_ok and source_count_ok
    checks = {
        "answer_contract_ok": answer_contract_ok,
        "evidence_status_ok": evidence_status_ok and evidence_shape_ok,
        "response_language_ok": language_ok,
        "dangerous_claims_ok": dangerous_claims_ok,
    }
    for name, passed in checks.items():
        if not passed:
            failures.append(name)
    return {
        "id": case["id"],
        "category": case["category"],
        "language": case["language"],
        "query": case["query"],
        "response": response,
        "sources": sources,
        "evidence": evidence,
        **checks,
        "success": not failures,
        "failures": failures,
    }


def _ratio(passed: int, total: int) -> float:
    return round(passed / total, 4) if total else 1.0


def _corpus_snapshot() -> dict[str, Any]:
    rows = run_query(CORPUS_SNAPSHOT_SQL)
    if len(rows) != 1:
        raise RuntimeError("answer-safety corpus fingerprint returned an unexpected shape")
    snapshot = dict(rows[0])
    for key, value in list(snapshot.items()):
        if isinstance(value, datetime):
            snapshot[key] = value.isoformat()
    return snapshot


def evaluate(
    suite: dict[str, Any],
    *,
    deployed_commit: str,
    max_llm_calls: int,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    backend = db_status()
    if backend.get("mode") != "db" or not backend.get("connectable"):
        raise RuntimeError(
            "answer-safety evaluation requires INFOHUB_V2_BACKEND_MODE=db "
            "and a connectable explicit database URL"
        )

    from rag.pipeline import rag_pipeline
    from rag_v2.live_runtime import maybe_run_live_rollout

    results: list[dict[str, Any]] = []
    with bounded_llm_calls(rag_pipeline.llm, max_llm_calls) as budget:
        for case in suite["cases"]:
            result = maybe_run_live_rollout(
                query=case["query"],
                language=case["language"],
                conversation_history=None,
            )
            if result is None:
                result = rag_pipeline.process_query(
                    query=case["query"],
                    conversation_history=None,
                    language=case["language"],
                )
            result = attach_evidence(result)
            results.append(
                score_case(
                    case,
                    result,
                    global_forbidden=suite.get("global_forbidden") or [],
                )
            )
        llm_calls = budget.summary()

    metrics = {
        "case_success_rate": _ratio(
            sum(item["success"] for item in results), len(results)
        ),
        "answer_contract_accuracy": _ratio(
            sum(item["answer_contract_ok"] for item in results), len(results)
        ),
        "evidence_status_accuracy": _ratio(
            sum(item["evidence_status_ok"] for item in results), len(results)
        ),
        "response_language_accuracy": _ratio(
            sum(item["response_language_ok"] for item in results), len(results)
        ),
        "dangerous_claim_avoidance_rate": _ratio(
            sum(item["dangerous_claims_ok"] for item in results), len(results)
        ),
    }
    language_metrics = {}
    for language in ("ru", "en", "ka"):
        selected = [item for item in results if item["language"] == language]
        language_metrics[language] = {
            "cases": len(selected),
            "case_success_rate": _ratio(
                sum(item["success"] for item in selected), len(selected)
            ),
        }
    metrics["min_language_case_success"] = min(
        item["case_success_rate"] for item in language_metrics.values()
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
        "execution_profile": suite["execution_profile"],
        "corpus": _corpus_snapshot(),
        "cases": len(results),
        "passed_cases": sum(item["success"] for item in results),
        "failed_cases": [
            {"id": item["id"], "failures": item["failures"]}
            for item in results
            if not item["success"]
        ],
        "llm_calls": llm_calls,
        "metrics": metrics,
        "language_metrics": language_metrics,
        "failed_metrics": failed_metrics,
        "results": results,
    }


def baseline_summary(report: dict[str, Any]) -> dict[str, Any]:
    """Return the aggregate allowlist suitable for Git history."""
    return {key: report[key] for key in BASELINE_FIELDS}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE_PATH)
    parser.add_argument("--commit", default="unknown")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--max-llm-calls", type=int, default=0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--baseline-output", type=Path)
    args = parser.parse_args()

    suite = load_suite(args.suite)
    required_limit = suite["execution_profile"]["max_llm_calls"]
    if not args.execute:
        plan = {
            "suite_version": suite["suite_version"],
            "cases": len(suite["cases"]),
            "languages": ["ru", "en", "ka"],
            "required_max_llm_calls": required_limit,
            "postgresql_writes_allowed": False,
            "status": "dry_run",
        }
        print("ANSWER_SAFETY_LIVE_PLAN=" + json.dumps(plan, sort_keys=True))
        return 0
    if args.max_llm_calls != required_limit:
        parser.error(
            "--max-llm-calls must exactly match the versioned suite ceiling "
            f"({required_limit})"
        )

    report = evaluate(
        suite,
        deployed_commit=args.commit,
        max_llm_calls=args.max_llm_calls,
    )
    if args.output:
        _write_json(args.output, report)
        print(f"Saved operational answer-safety report: {args.output}")
    if args.baseline_output:
        _write_json(args.baseline_output, baseline_summary(report))
        print(f"Saved aggregate answer-safety baseline: {args.baseline_output}")

    summary = {
        "suite_version": report["suite_version"],
        "deployed_commit": report["deployed_commit"],
        "cases": report["cases"],
        "passed_cases": report["passed_cases"],
        "llm_calls": report["llm_calls"],
        "metrics": report["metrics"],
        "failed_cases": report["failed_cases"],
        "failed_metrics": report["failed_metrics"],
    }
    print("ANSWER_SAFETY_LIVE_EVAL=" + json.dumps(summary, sort_keys=True))
    return 1 if report["failed_cases"] or report["failed_metrics"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
