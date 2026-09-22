"""Jev transport, fallbacks and route admission without network access."""
import json
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr

from rag_v2.jev_router import CRITERIA, ENDPOINT, MODEL, JevOptions, JevRouter, validate_answer
from rag_v2.query_classifier import classify_query
from rag_v2.query_parser import parse_query


def payload(choice="dispute_practice", confidence=.99):
    probabilities = dict.fromkeys(CRITERIA, 0.0)
    probabilities[choice] = confidence
    probabilities["canonical_law_lookup" if choice != "canonical_law_lookup" else "dispute_practice"] = 1 - confidence
    return {"model": MODEL, "answers": {"route": {
        "type": "choice", "choice": choice, "confidence": confidence, "probabilities": probabilities,
    }}}


def setup_router(handler=None, *, clock=lambda: 0):
    calls = []

    def respond(request):
        calls.append(request)
        return handler(request) if handler else httpx.Response(200, json=payload())

    router = JevRouter(client_factory=lambda **kw: httpx.Client(transport=httpx.MockTransport(respond), **kw), clock=clock)
    return router, calls


def decide(router, *, query="Find court precedents where judges overturned an additional VAT assessment.", mode="assist", key="test-secret"):
    parsed = parse_query(query, "en")
    baseline = classify_query(parsed)
    return router.decide(parsed, baseline, JevOptions(mode=mode, api_key=key)), baseline


def test_assist_changes_route_and_sends_only_current_question():
    router, calls = setup_router()
    result, baseline = decide(router)
    assert baseline.question_class == "canonical_law_lookup"
    assert result.classification.question_class == "dispute_practice"
    assert result.status == "applied"
    request = calls[0]
    assert str(request.url) == ENDPOINT
    assert request.headers["Authorization"] == "Bearer test-secret"
    body = json.loads(request.content)
    assert body["model"] == MODEL
    assert set(json.loads(body["state"])) == {"query", "language"}
    assert set(body["questions"]) == {"route"}


def test_shadow_calls_provider_without_changing_classification():
    router, calls = setup_router()
    result, baseline = decide(router, mode="shadow")
    assert result.classification is baseline
    assert result.status == "observed" and len(calls) == 1


@pytest.mark.parametrize("mode,key,status", [("off", "test", "off"), ("assist", "", "missing_key")])
def test_disabled_or_missing_key_never_calls_provider(mode, key, status):
    router, calls = setup_router()
    result, baseline = decide(router, mode=mode, key=key)
    assert result.classification is baseline and result.status == status and not calls


@pytest.mark.parametrize("query", [
    "What does Article 168 of the Tax Code say?", "What does document No. 1432 say?",
    "Какое решение по спору №19068/2/2023?", "How do I appeal a tax assessment?",
])
def test_exact_references_and_appeal_procedure_never_call_provider(query):
    router, calls = setup_router()
    result, baseline = decide(router, query=query)
    assert result.classification is baseline and result.status == "protected_reference" and not calls


@pytest.mark.parametrize("confidence", [.43, .89])
def test_low_confidence_keeps_baseline(confidence):
    data = payload()
    data["answers"]["route"]["confidence"] = confidence
    router, _ = setup_router(lambda _: httpx.Response(200, json=data))
    result, baseline = decide(router)
    assert result.classification is baseline and result.status == "low_confidence"


def test_confidence_does_not_replace_probability_validation():
    data = payload(confidence=.6)
    data["answers"]["route"]["confidence"] = .99
    router, _ = setup_router(lambda _: httpx.Response(200, json=data))
    result, baseline = decide(router)
    assert result.classification is baseline and result.status == "low_confidence"


@pytest.mark.parametrize("mode,clarify", [("assist", True), ("shadow", False)])
def test_unclear_is_an_explicit_clarification_not_an_invalid_question_class(mode, clarify):
    router, _ = setup_router(lambda _: httpx.Response(200, json=payload("unclear")))
    result, baseline = decide(router, query="Can you explain this?", mode=mode)
    assert result.needs_clarification is clarify and result.classification is baseline


@pytest.mark.parametrize("choice", ["local_regulation_lookup", "named_document_lookup"])
def test_a_route_cannot_invent_a_missing_locator(choice):
    router, _ = setup_router(lambda _: httpx.Response(200, json=payload(choice)))
    result, baseline = decide(router)
    assert result.classification is baseline and result.status == "missing_locator"


@pytest.mark.parametrize("status", [302, 401, 429, 500])
def test_provider_errors_fall_back_without_retry_or_redirect(status):
    router, calls = setup_router(lambda _: httpx.Response(status, headers={"Location": "https://example.com"}))
    result, baseline = decide(router)
    assert result.classification is baseline and result.status == "provider_error"
    assert len(calls) == 1
    assert decide(router)[0].status == "cooldown" and len(calls) == 1


def test_timeout_falls_back_and_recovers_after_cooldown():
    now = [0]

    def respond(_):
        if now[0] == 0:
            raise httpx.ReadTimeout("sensitive provider message")
        return httpx.Response(200, json=payload())

    router, calls = setup_router(respond, clock=lambda: now[0])
    assert decide(router)[0].status == "provider_error"
    assert decide(router)[0].status == "cooldown"
    now[0] = 31
    assert decide(router)[0].status == "applied" and len(calls) == 2


@pytest.mark.parametrize("body", [b"not-json", b"[]", b"x" * 17000])
def test_invalid_or_oversized_response_falls_back(body):
    router, _ = setup_router(lambda _: httpx.Response(200, content=body))
    result, baseline = decide(router)
    assert result.classification is baseline and result.status == "provider_error"


@pytest.mark.parametrize("mutation", [
    lambda d: d.update(model="jev-latest"),
    lambda d: d.update(answers=[]),
    lambda d: d["answers"]["route"].update(choice=[]),
    lambda d: d["answers"]["route"].update(choice="invented"),
    lambda d: d["answers"]["route"].update(confidence=True),
    lambda d: d["answers"]["route"].update(confidence=float("nan")),
    lambda d: d["answers"]["route"].update(probabilities=[]),
    lambda d: d["answers"]["route"]["probabilities"].update(dispute_practice=-1),
    lambda d: d["answers"]["route"]["probabilities"].update(dispute_practice=.2),
    lambda d: d["answers"]["route"].update(choice="canonical_law_lookup"),
])
def test_malformed_typed_answers_are_rejected(mutation):
    data = payload()
    mutation(data)
    with pytest.raises(ValueError):
        validate_answer(data, MODEL)


def test_busy_worker_does_not_queue_another_external_call():
    router, calls = setup_router()
    router._slots.acquire()
    router._slots.acquire()
    try:
        assert decide(router)[0].status == "busy" and not calls
    finally:
        router._slots.release()
        router._slots.release()


def test_oversized_query_is_not_truncated_or_sent():
    router, calls = setup_router()
    assert decide(router, query="x" * 2001)[0].status == "query_size" and not calls


def test_logs_and_options_repr_exclude_secret_and_query(caplog):
    router, _ = setup_router()
    with caplog.at_level("INFO", logger="rag_v2.jev_router"):
        decide(router, query="Private case description 123456789", key="sensitive-key")
    assert "Private case" not in caplog.text and "123456789" not in caplog.text
    assert "sensitive-key" not in caplog.text
    assert "sensitive-key" not in repr(JevOptions(api_key="sensitive-key"))


def test_secret_settings_are_read_server_side():
    options = JevOptions.from_settings(SimpleNamespace(
        JEV_MODE="shadow", TYPESAFE_API_KEY=SecretStr("private-key"), JEV_MODEL=MODEL,
        JEV_TIMEOUT_SECONDS=2, JEV_MIN_CONFIDENCE=.9))
    assert options.api_key == "private-key" and options.mode == "shadow"
