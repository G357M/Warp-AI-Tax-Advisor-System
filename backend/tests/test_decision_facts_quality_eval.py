"""Contracts for the read-only decision-facts quality evaluator."""

from datetime import datetime, timezone

from scripts import evaluate_decision_facts_quality as facts_eval


def _quality(**overrides):
    row = {
        "eligible_documents": 100,
        "facts_total": 100,
        "covered_documents": 100,
        "current_version_rows": 100,
        "structural_issue_rows": 0,
        "amount_rows": 80,
        "positive_amount_rows": 80,
        "nonpositive_amount_rows": 0,
        "outcome_alignment_issue_rows": 0,
        "self_prior_reference_rows": 0,
        "article_rows": 90,
        "non_simple_article_rows": 0,
        "missing_decision_number_rows": 0,
        "missing_decision_date_rows": 0,
        "unclear_outcome_rows": 0,
        "outdated_extraction_rows": 0,
        "latest_fact_created_at": datetime(2026, 8, 20, tzinfo=timezone.utc),
        "duplicate_identity_groups": 0,
    }
    row.update(overrides)
    return row


def _links(**overrides):
    row = {
        "links_total": 20,
        "invalid_link_rows": 0,
        "prior_ref_links": 10,
        "case_number_links": 10,
    }
    row.update(overrides)
    return row


def test_default_contract_is_read_only_and_matches_extraction_version():
    contract = facts_eval.load_contract()

    assert contract["expected_extraction_version"] == facts_eval.EXTRACTION_VERSION
    assert contract["execution_profile"]["llm_calls_allowed"] is False
    assert contract["execution_profile"]["postgresql_writes_allowed"] is False
    assert set(contract["thresholds"]) == set(facts_eval.METRIC_NAMES)


def test_perfect_quality_snapshot_has_perfect_metrics():
    metrics = facts_eval.calculate_metrics(_quality(), _links())

    assert all(value == 1.0 for value in metrics.values())


def test_quality_metrics_surface_known_debt_without_division_errors():
    metrics = facts_eval.calculate_metrics(
        _quality(
            current_version_rows=99,
            amount_rows=0,
            positive_amount_rows=0,
            outcome_alignment_issue_rows=2,
            self_prior_reference_rows=1,
            article_rows=0,
            non_simple_article_rows=0,
        ),
        _links(links_total=0),
    )

    assert metrics["current_extraction_rate"] == 0.99
    assert metrics["positive_amount_rate"] == 1.0
    assert metrics["outcome_alignment_rate"] == 0.98
    assert metrics["prior_reference_safety_rate"] == 0.99
    assert metrics["simple_article_reference_rate"] == 1.0
    assert metrics["appeal_link_integrity_rate"] == 1.0


def test_evaluator_uses_only_select_queries_and_baseline_excludes_review_manifest():
    sql_text = " ".join(
        (
            facts_eval.QUALITY_SQL,
            facts_eval.LINK_SQL,
            facts_eval.DISTRIBUTION_SQL,
            facts_eval.STRATIFIED_REVIEW_SQL,
            facts_eval.ANOMALY_REVIEW_SQL,
        )
    ).lower()
    for forbidden in ("insert ", "update ", "delete ", "alter ", "drop ", "truncate "):
        assert forbidden not in sql_text

    report = {field: {} for field in facts_eval.BASELINE_FIELDS}
    report["review_manifest"] = {"stratified": [{"document_id": "private"}]}
    baseline = facts_eval.baseline_summary(report)

    assert set(baseline) == set(facts_eval.BASELINE_FIELDS)
    assert "review_manifest" not in baseline
