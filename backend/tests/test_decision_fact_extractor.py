"""Regression contracts for bounded decision-fact extraction."""

from decision_fact_contract import (
    MAX_ARTICLE_REFS,
    MAX_OUTPUT_TOKENS,
    MAX_PRIOR_REFS,
    clean_article_refs,
    clean_prior_refs,
    llm_options,
)


def test_llm_output_budget_fits_v2_schema():
    options = llm_options(model="test-model", api_key="test-key")

    assert options["max_tokens"] == MAX_OUTPUT_TOKENS == 1600
    assert options["temperature"] == 0
    assert options["model_kwargs"] == {
        "response_format": {"type": "json_object"}
    }


def test_reference_normalization_enforces_prompt_bounds():
    articles = [str(index) for index in range(MAX_ARTICLE_REFS + 5)]
    prior_refs = [
        {"number": str(index), "body": "other", "date": None}
        for index in range(MAX_PRIOR_REFS + 5)
    ]

    assert len(clean_article_refs(articles)) == MAX_ARTICLE_REFS == 20
    assert len(clean_prior_refs(prior_refs)) == MAX_PRIOR_REFS == 10
