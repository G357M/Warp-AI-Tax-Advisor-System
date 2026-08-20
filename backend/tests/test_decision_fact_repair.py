from types import SimpleNamespace

from scripts.repair_decision_fact_normalization import normalized_changes


def test_repair_clears_nonpositive_amount_deduplicates_and_removes_self_ref():
    row = SimpleNamespace(
        amount_gel=-10.0,
        contested_articles=["168", "168", "98²"],
        decision_number="19068/2/2023",
        prior_refs=[
            {"number": "№19068/2/2023", "body": "city_court", "date": None},
            {
                "number": "100/2022",
                "body": "revenue_service_council",
                "date": "2022-01-01",
            },
        ],
        prior_body="city_court",
    )

    assert normalized_changes(row) == {
        "amount_gel": None,
        "contested_articles": ["168", "98²"],
        "prior_refs": [
            {
                "number": "100/2022",
                "body": "revenue_service_council",
                "date": "2022-01-01",
            }
        ],
        "prior_body": "revenue_service_council",
    }


def test_repair_does_not_rewrite_legitimate_superscript_article_or_positive_amount():
    row = SimpleNamespace(
        amount_gel=1250.5,
        contested_articles=["98²", "16511"],
        decision_number="55/2026",
        prior_refs=[],
        prior_body=None,
    )

    assert normalized_changes(row) == {}
