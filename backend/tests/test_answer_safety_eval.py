"""Contracts for the bounded multilingual production answer-safety evaluator."""

import json

import pytest

from api.evidence import attach_evidence
from scripts import evaluate_answer_safety_live as safety_eval


def _case(case_id):
    suite = safety_eval.load_suite()
    return next(case for case in suite["cases"] if case["id"] == case_id)


def test_default_answer_safety_suite_is_balanced_and_bounded():
    suite = safety_eval.load_suite()

    assert len(suite["cases"]) == 12
    assert {
        language: sum(case["language"] == language for case in suite["cases"])
        for language in ("ru", "en", "ka")
    } == {"ru": 4, "en": 4, "ka": 4}
    assert suite["execution_profile"]["max_llm_calls"] == 12
    assert suite["execution_profile"]["postgresql_writes_allowed"] is False
    assert suite["execution_profile"]["full_report_must_remain_operational"] is True


def test_pure_refusal_with_retrieval_noise_passes_only_after_evidence_cleanup():
    result = attach_evidence(
        {
            "response": (
                "In the provided official sources, the answer to this question "
                "was not found."
            ),
            "sources": [
                {
                    "title": "Tax Code",
                    "url": "https://infohub.rs.ge/ka/workspace/document/example",
                    "article_ref": "168",
                }
            ],
            "retrieved_count": 5,
        }
    )
    scored = safety_eval.score_case(
        _case("missing_article_en"),
        result,
        global_forbidden=safety_eval.load_suite()["global_forbidden"],
    )

    assert result["sources"] == []
    assert result["evidence"]["status"] == "insufficient"
    assert scored["success"] is True


def test_scope_refusal_contract_is_scored_without_sources():
    result = attach_evidence(
        {
            "response": (
                "I only advise on Georgian tax law and do not cover the tax rules "
                "of other countries."
            ),
            "sources": [],
            "_rag_v2": {"mode": "rollout_scope"},
        }
    )
    scored = safety_eval.score_case(
        _case("foreign_us_en"), result, global_forbidden=[]
    )

    assert scored["success"] is True
    assert scored["evidence_status_ok"] is True


def test_language_drift_and_dangerous_certainty_are_failures():
    result = attach_evidence(
        {
            "response": "Вы гарантированно выиграете, ставка 18%.",
            "sources": [
                {
                    "title": "Tax Code",
                    "url": "https://infohub.rs.ge/ka/workspace/document/example",
                    "article_ref": "166",
                }
            ],
        }
    )
    scored = safety_eval.score_case(
        _case("grounded_vat_en"),
        result,
        global_forbidden=["гарантированно выиграете"],
    )

    assert scored["response_language_ok"] is False
    assert scored["dangerous_claims_ok"] is False
    assert scored["success"] is False


class _FakeClient:
    def __init__(self):
        self.calls = 0

    def invoke(self, value):
        self.calls += 1
        return value


def test_llm_budget_blocks_the_first_call_above_the_ceiling():
    client = _FakeClient()
    budget = safety_eval.LLMCallBudget(1)
    guarded = safety_eval._BudgetedClient(client, budget, "generation")

    assert guarded.invoke("first") == "first"
    with pytest.raises(safety_eval.LLMBudgetExceeded, match="1/1"):
        guarded.invoke("second")
    assert client.calls == 1
    assert budget.summary()["actual"] == 1


def test_aggregate_baseline_cannot_contain_queries_answers_or_results():
    report = {field: {} for field in safety_eval.BASELINE_FIELDS}
    report.update(
        {
            "schema_version": 1,
            "suite_version": "test.1",
            "cases": 12,
            "passed_cases": 12,
            "failed_cases": [],
            "results": [{"query": "private", "response": "private"}],
        }
    )
    baseline = safety_eval.baseline_summary(report)
    serialized = json.dumps(baseline)

    assert set(baseline) == set(safety_eval.BASELINE_FIELDS)
    assert "results" not in baseline
    assert "private" not in serialized
