from datetime import date

import pytest

from decision_fact_contract import (
    clean_amount,
    clean_article_refs,
    clean_prior_refs,
    normalize,
    normalize_reference_number,
    parse_date,
)


@pytest.mark.parametrize("value", [None, "", "bad", 0, -1, float("nan"), float("inf")])
def test_non_positive_or_non_finite_amount_is_not_published(value):
    assert clean_amount(value) is None


def test_positive_amount_and_iso_date_are_normalized():
    assert clean_amount("1250.50") == 1250.5
    assert parse_date("2026-08-20T12:00:00") == date(2026, 8, 20)


def test_article_references_are_deduplicated_without_losing_superscripts():
    assert clean_article_refs([" 98² ", "98²", "16511", None, ""]) == [
        "98²",
        "16511",
    ]


def test_prior_reference_cannot_point_to_its_own_decision():
    refs = clean_prior_refs(
        [
            {"number": "№ 19068 / 2 / 2023", "body": "city_court"},
            {
                "number": "123/2022",
                "body": "revenue_service_council",
                "date": "2022-04-05",
            },
        ],
        own_decision_number="19068/2/2023",
    )

    assert refs == [
        {
            "number": "123/2022",
            "body": "revenue_service_council",
            "date": "2022-04-05",
        }
    ]
    assert normalize_reference_number("№ 19068 / 2 / 2023") == "19068/2/2023"


def test_full_payload_defaults_invalid_enums_and_uses_first_valid_prior_body():
    fields = normalize(
        {
            "decision_number": "55/2026",
            "authority_body": "invented",
            "dispute_type": "invented",
            "outcome": "invented",
            "in_favor": "invented",
            "amount_gel": -5,
            "contested_articles": ["168", "168"],
            "prior_decisions": [
                {
                    "number": "10/2025",
                    "body": "mof_dispute_council",
                    "date": "2025-02-03",
                }
            ],
        }
    )

    assert fields["authority_body"] == "other"
    assert fields["dispute_type"] == "other"
    assert fields["outcome"] == "unclear"
    assert fields["in_favor"] == "unclear"
    assert fields["amount_gel"] is None
    assert fields["contested_articles"] == ["168"]
    assert fields["prior_body"] == "mof_dispute_council"
