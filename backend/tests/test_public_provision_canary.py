"""Contracts for the bounded public exact-provision canary."""

import json
from datetime import datetime, timezone

import pytest

from scripts import evaluate_public_provision_canary as canary


def _public_body(case: dict, *, url: str | None = None):
    language = case["language"]
    article_ref = case["official_provision"]["article_ref"]
    answers = {
        "ru": f"Статья {article_ref} устанавливает применимое правило.",
        "en": f"Article {article_ref} provides the applicable rule.",
        "ka": f"საქართველოს კოდექსის {article_ref}-ე მუხლი ადგენს შესაბამის წესს.",
    }
    provision_url = url or case["official_provision"]["url"]
    return {
        "response": answers[language],
        "sources": [
            {
                "text": "საქართველოს ოფიციალური კანონი",
                "relevance": 1.0,
                "metadata": {
                    "article_ref": article_ref,
                    "provision_links": [
                        {
                            "article_ref": article_ref,
                            "point_ref": None,
                            "url": provision_url,
                        }
                    ],
                    "provision_publication_url": case["official_provision"]
                    ["verified_publication_url"],
                },
            }
        ],
        "evidence": {
            "status": "grounded",
            "coverage": "exact_provision",
            "source_count": 1,
            "official_sources_only": True,
            "has_precise_citation": True,
            "has_official_provision_link": True,
        },
        "retrieved_count": 1,
    }


def test_default_suite_is_balanced_and_request_bounded():
    suite = canary.load_suite()

    assert len(suite["cases"]) == 9
    assert {case["language"] for case in suite["cases"]} == {"ru", "en", "ka"}
    assert {
        language: sum(case["language"] == language for case in suite["cases"])
        for language in ("ru", "en", "ka")
    } == {"ru": 3, "en": 3, "ka": 3}
    assert {
        case["official_provision"]["article_ref"] for case in suite["cases"]
    } == {"47", "168", "299"}
    assert suite["execution_profile"]["max_public_requests"] == 9
    assert suite["execution_profile"]["postgresql_writes_allowed"] is False

    tax_registry = json.loads(
        (canary.BACKEND_ROOT / "rag_v2" / "official_tax_code_provisions.json")
        .read_text(encoding="utf-8")
    )
    for case in suite["cases"]:
        article_ref = case["official_provision"]["article_ref"]
        if article_ref not in {"168", "299"}:
            continue
        assert case["official_provision"]["url"] == (
            f"{tax_registry['matsne_document_url']}"
            f"#{tax_registry['article_anchors'][article_ref]}"
        )
        assert case["official_provision"]["verified_publication_url"] == (
            tax_registry["verified_publication_url"]
        )


def test_historical_committed_baseline_contains_no_public_payloads():
    baseline_path = (
        canary.BACKEND_ROOT.parent
        / "evaluation"
        / "baselines"
        / "public_provision_canary_2026-08-26_ceb7ac7.json"
    )
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))

    def nested_keys(value):
        if isinstance(value, dict):
            return set(value) | set().union(
                *(nested_keys(item) for item in value.values()), set()
            )
        if isinstance(value, list):
            return set().union(*(nested_keys(item) for item in value), set())
        return set()

    assert baseline["suite_sha256"] == (
        "489cd341f1749fb9a73d2c0fd3a5344c93d85b78faf2980c63ef2bbd07e55cab"
    )
    assert baseline["suite_version"] == "2026-08-26.1"
    assert baseline["passed_cases"] == baseline["cases"] == 3
    assert baseline["request_budget"] == {"limit": 3, "actual": 3}
    assert all(value == 1.0 for value in baseline["metrics"].values())
    assert "results" not in baseline
    assert {"query", "response", "sources"}.isdisjoint(nested_keys(baseline))


def test_exact_public_provision_and_language_contracts_pass():
    suite = canary.load_suite()

    for case in suite["cases"]:
        scored = canary.score_case(
            case,
            {"http_status": 200, "body": _public_body(case)},
        )
        assert scored["success"] is True
        assert scored["official_provision_link_ok"] is True
        assert scored["response_language_ok"] is True


def test_document_level_or_wrong_anchor_response_fails_closed():
    case = canary.load_suite()["cases"][0]
    body = _public_body(
        case, url="https://matsne.gov.ge/ka/document/view/1155567"
    )
    body["evidence"]["coverage"] = "official_documents"
    body["evidence"]["has_official_provision_link"] = False

    scored = canary.score_case(case, {"http_status": 200, "body": body})

    assert scored["success"] is False
    assert scored["evidence_contract_ok"] is False
    assert scored["official_provision_link_ok"] is False


def test_evaluator_makes_exactly_nine_requests_and_baseline_is_aggregate(monkeypatch):
    suite = canary.load_suite()
    calls = []

    def fake_post(_url, payload, _timeout):
        calls.append(payload)
        matching_case = next(
            case
            for case in suite["cases"]
            if case["query"] == payload["query"]
            and case["language"] == payload["language"]
        )
        return {"http_status": 200, "body": _public_body(matching_case)}

    monkeypatch.setattr(canary, "_post_json", fake_post)
    report = canary.evaluate(
        suite,
        url=canary.DEFAULT_URL,
        deployed_commit="a" * 40,
        max_public_requests=9,
        timeout=1.0,
        generated_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
    )

    assert len(calls) == 9
    assert report["passed_cases"] == report["cases"] == 9
    assert report["request_budget"] == {"limit": 9, "actual": 9}
    assert all(value == 1.0 for value in report["metrics"].values())

    baseline = canary.baseline_summary(report)
    serialized = str(baseline)
    assert set(baseline) == set(canary.BASELINE_FIELDS)
    assert "results" not in baseline
    assert "applicable rule" not in serialized


def test_execute_rejects_non_loopback_targets_and_wrong_ceiling():
    suite = canary.load_suite()
    with pytest.raises(ValueError, match="loopback"):
        canary.evaluate(
            suite,
            url="https://tax-advisor.ge/api/v1/public/query",
            deployed_commit="a" * 40,
            max_public_requests=9,
            timeout=1.0,
        )
    with pytest.raises(ValueError, match="versioned ceiling"):
        canary.evaluate(
            suite,
            url=canary.DEFAULT_URL,
            deployed_commit="a" * 40,
            max_public_requests=10,
            timeout=1.0,
        )
