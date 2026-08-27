"""Mass contracts for the single-source multilingual answer factory."""

from types import SimpleNamespace

from api.evidence import attach_evidence
from rag_v2.faq_tax_matrix import (
    CANONICAL_TAX_CODE_SOURCE_URL,
    TAX_FAQ_MATRIX,
    build_tax_answer_contract_cases,
)
from rag_v2.legal_answer_contracts import (
    SUPPORTED_LANGUAGES,
    ensure_exact_provision_citations,
)
from rag_v2.public_response import (
    authoritative_tax_fact_response,
    direct_tax_faq_response,
    small_business_legal_form_response,
    tax_appeal_procedure_response,
)
from rag_v2.query_classifier import classify_query
from rag_v2.query_parser import parse_query
from scripts.audit_legal_answer_contracts import audit_contracts
from scripts.build_legal_answer_contract_canary import build_suite
from scripts.evaluate_public_provision_canary import validate_suite_payload


def _source(article_ref: str) -> dict:
    return {
        "title": "საქართველოს საგადასახადო კოდექსი.",
        "document_type": "law",
        "url": CANONICAL_TAX_CODE_SOURCE_URL,
        "article_ref": article_ref,
        "relevance": 1.0,
    }


def test_factory_generates_all_twenty_five_contracts_in_three_languages():
    cases = build_tax_answer_contract_cases()

    assert len(TAX_FAQ_MATRIX) == 25
    assert len(cases) == 75
    assert {case["language"] for case in cases} == set(SUPPORTED_LANGUAGES)
    assert {
        language: sum(case["language"] == language for case in cases)
        for language in SUPPORTED_LANGUAGES
    } == {"ru": 25, "en": 25, "ka": 25}
    assert len({case["id"] for case in cases}) == 75
    assert all(case["official_provision"]["url"].startswith("https://matsne.gov.ge/") for case in cases)
    assert all("#" in case["official_provision"]["url"] for case in cases)
    assert all(case["evidence"]["coverage"] == "exact_provision" for case in cases)


def test_every_contract_response_contains_fact_tokens_and_generated_citation():
    for contract in TAX_FAQ_MATRIX:
        for language in SUPPORTED_LANGUAGES:
            response = contract.response(language)
            assert contract.citation(language) in response
            assert all(
                token in response
                for token in (contract.smoke_contains or {}).get(language) or []
            )


def test_final_boundary_enforces_all_seventy_five_citations_idempotently():
    for contract in TAX_FAQ_MATRIX:
        for language in SUPPORTED_LANGUAGES:
            result = attach_evidence(
                {
                    "response": contract.response_by_lang[language],
                    "sources": [_source(", ".join(contract.article_refs))],
                    "_rag_v2": {
                        "mode": "rollout_authoritative",
                        "question_class": contract.question_class,
                    },
                }
            )
            enforced = ensure_exact_provision_citations(result, language)
            assert enforced["response"] == contract.response(language)
            assert enforced["evidence"]["coverage"] == "exact_provision"
            assert (
                ensure_exact_provision_citations(enforced, language)["response"]
                == contract.response(language)
            )


def test_enforcer_does_not_upgrade_document_level_evidence():
    result = attach_evidence(
        {
            "response": "Ответ основан на официальном документе.",
            "sources": [
                {
                    "title": "Official document",
                    "document_type": "guideline",
                    "url": "https://infohub.rs.ge/ka/workspace/document/not-a-registry-act",
                }
            ],
        }
    )
    before = result["response"]

    assert result["evidence"]["coverage"] == "official_documents"
    assert ensure_exact_provision_citations(result, "ru")["response"] == before


def test_enforcer_does_not_confuse_inserted_and_base_article_numbers():
    contract = next(item for item in TAX_FAQ_MATRIX if item.article_ref == "165")
    wrong_citation = next(
        item for item in TAX_FAQ_MATRIX if item.article_ref == "165-1"
    ).citation("ru")
    result = attach_evidence(
        {
            "response": f"Проверяем точность номера статьи.\n\n{wrong_citation}",
            "sources": [_source(contract.article_ref)],
            "_rag_v2": {"mode": "rollout_authoritative"},
        }
    )

    enforced = ensure_exact_provision_citations(result, "ru")["response"]

    assert wrong_citation in enforced
    assert contract.citation("ru") in enforced


def test_contract_audit_is_complete_read_only_and_call_free():
    report = audit_contracts()

    assert report["result"] == "pass"
    assert report["contracts"] == 25
    assert report["localized_answers"] == 75
    assert report["generated_cases"] == 75
    assert report["verified_article_bindings"] == 28
    assert report["error_count"] == 0
    assert report["network_calls_allowed"] is False
    assert report["database_calls_allowed"] is False
    assert report["llm_calls_allowed"] is False


def test_factory_builds_a_valid_seventy_five_case_public_canary():
    suite = build_suite()

    assert validate_suite_payload(suite) is suite
    assert suite["suite_version"].startswith("legal-answer-contracts-")
    assert suite["execution_profile"]["max_public_requests"] == 75
    assert len(suite["cases"]) == 75
    assert all(
        any(
            item.startswith(("Источник:", "Source:", "წყარო:"))
            for item in case["required_response_all"]
        )
        for case in suite["cases"]
    )


def test_direct_router_matches_all_contract_cases_before_retrieval():
    for contract in TAX_FAQ_MATRIX:
        for language in SUPPORTED_LANGUAGES:
            parsed = parse_query(contract.sample_queries[language], language=language)
            classification = classify_query(parsed)
            trace = SimpleNamespace(
                parsed_query=parsed.model_dump(),
                classification=classification.model_dump(),
            )

            assert direct_tax_faq_response(trace) == contract.response(language)


def test_contract_router_has_per_topic_kill_switch(monkeypatch):
    contract = TAX_FAQ_MATRIX[0]
    language = "ru"
    parsed = parse_query(contract.sample_queries[language], language=language)
    trace = SimpleNamespace(
        parsed_query=parsed.model_dump(),
        classification=classify_query(parsed).model_dump(),
    )

    monkeypatch.setenv("INFOHUB_DISABLED_LEGAL_ANSWER_CONTRACTS", contract.topic)

    assert direct_tax_faq_response(trace) is None


def test_legacy_guard_kill_switch_does_not_disable_verified_contract(monkeypatch):
    contract = next(item for item in TAX_FAQ_MATRIX if item.topic == "property_tax")
    language = "ru"
    parsed = parse_query(contract.sample_queries[language], language=language)
    trace = SimpleNamespace(
        parsed_query=parsed.model_dump(),
        classification=classify_query(parsed).model_dump(),
    )

    monkeypatch.setenv("INFOHUB_DISABLED_GUARDS", contract.topic)

    assert direct_tax_faq_response(trace) == contract.response(language)


def test_migrated_contract_kill_switch_is_not_bypassed_by_legacy_delegates(
    monkeypatch,
):
    cases = (
        (
            "tax-residency-individual",
            "Когда физлицо становится налоговым резидентом Грузии?",
            authoritative_tax_fact_response,
        ),
        (
            "late-payment-interest",
            "Какая пеня начисляется за просрочку уплаты налога в Грузии?",
            authoritative_tax_fact_response,
        ),
        (
            "tax-appeal-procedure",
            "Как обжаловать решение налоговой?",
            tax_appeal_procedure_response,
        ),
        (
            "small-business-llc-ineligible",
            "Может ли ООО применять режим малого бизнеса 1%?",
            small_business_legal_form_response,
        ),
    )
    for slug, query, legacy_delegate in cases:
        with monkeypatch.context() as scoped:
            scoped.setenv("INFOHUB_DISABLED_LEGAL_ANSWER_CONTRACTS", slug)
            parsed = parse_query(query, language="ru")
            classification = classify_query(parsed)
            trace = SimpleNamespace(
                parsed_query=parsed.model_dump(),
                classification=classification.model_dump(),
            )

            assert direct_tax_faq_response(trace) is None
            assert legacy_delegate(trace) is None
