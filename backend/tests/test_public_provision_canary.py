"""Contracts for the bounded public exact-provision canary."""

import hashlib
import json
from datetime import datetime, timezone

import pytest

from scripts import evaluate_public_provision_canary as canary


def _public_body(language: str, *, url: str | None = None):
    answers = {
        "ru": "Статья 47 Трудового кодекса устанавливает основания прекращения трудового договора.",
        "en": "Article 47 of the Labour Code provides the grounds for terminating an employment agreement.",
        "ka": "შრომის კოდექსის 47-ე მუხლი ადგენს შრომითი ხელშეკრულების შეწყვეტის საფუძვლებს.",
    }
    provision_url = url or (
        "https://matsne.gov.ge/ka/document/view/1155567"
        "#part_173"
    )
    return {
        "response": answers[language],
        "sources": [
            {
                "text": "საქართველოს შრომის კოდექსი",
                "relevance": 1.0,
                "metadata": {
                    "article_ref": "47",
                    "provision_links": [
                        {"article_ref": "47", "point_ref": None, "url": provision_url}
                    ],
                    "provision_publication_url": (
                        "https://matsne.gov.ge/ka/document/view/1155567"
                        "?publication=28"
                    ),
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

    assert len(suite["cases"]) == 3
    assert {case["language"] for case in suite["cases"]} == {"ru", "en", "ka"}
    assert suite["execution_profile"]["max_public_requests"] == 3
    assert suite["execution_profile"]["postgresql_writes_allowed"] is False


def test_committed_baseline_matches_suite_and_contains_no_public_payloads():
    suite = canary.load_suite()
    suite_bytes = json.dumps(
        suite, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
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

    assert baseline["suite_sha256"] == hashlib.sha256(suite_bytes).hexdigest()
    assert baseline["suite_version"] == suite["suite_version"]
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
            {"http_status": 200, "body": _public_body(case["language"])},
        )
        assert scored["success"] is True
        assert scored["official_provision_link_ok"] is True
        assert scored["response_language_ok"] is True


def test_document_level_or_wrong_anchor_response_fails_closed():
    case = canary.load_suite()["cases"][0]
    body = _public_body("ru", url="https://matsne.gov.ge/ka/document/view/1155567")
    body["evidence"]["coverage"] = "official_documents"
    body["evidence"]["has_official_provision_link"] = False

    scored = canary.score_case(case, {"http_status": 200, "body": body})

    assert scored["success"] is False
    assert scored["evidence_contract_ok"] is False
    assert scored["official_provision_link_ok"] is False


def test_evaluator_makes_exactly_three_requests_and_baseline_is_aggregate(monkeypatch):
    suite = canary.load_suite()
    calls = []

    def fake_post(_url, payload, _timeout):
        calls.append(payload)
        return {"http_status": 200, "body": _public_body(payload["language"])}

    monkeypatch.setattr(canary, "_post_json", fake_post)
    report = canary.evaluate(
        suite,
        url=canary.DEFAULT_URL,
        deployed_commit="a" * 40,
        max_public_requests=3,
        timeout=1.0,
        generated_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
    )

    assert len(calls) == 3
    assert report["passed_cases"] == report["cases"] == 3
    assert report["request_budget"] == {"limit": 3, "actual": 3}
    assert all(value == 1.0 for value in report["metrics"].values())

    baseline = canary.baseline_summary(report)
    serialized = str(baseline)
    assert set(baseline) == set(canary.BASELINE_FIELDS)
    assert "results" not in baseline
    assert "terminating an employment agreement" not in serialized


def test_execute_rejects_non_loopback_targets_and_wrong_ceiling():
    suite = canary.load_suite()
    with pytest.raises(ValueError, match="loopback"):
        canary.evaluate(
            suite,
            url="https://tax-advisor.ge/api/v1/public/query",
            deployed_commit="a" * 40,
            max_public_requests=3,
            timeout=1.0,
        )
    with pytest.raises(ValueError, match="versioned ceiling"):
        canary.evaluate(
            suite,
            url=canary.DEFAULT_URL,
            deployed_commit="a" * 40,
            max_public_requests=4,
            timeout=1.0,
        )
