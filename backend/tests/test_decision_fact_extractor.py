"""Regression contracts for bounded decision-fact extraction."""

from scripts import extract_decision_facts as extractor


def test_llm_output_budget_fits_v2_schema(monkeypatch):
    captured = {}
    sentinel = object()

    def fake_chat_openai(**kwargs):
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(extractor, "ChatOpenAI", fake_chat_openai)

    assert extractor.build_llm() is sentinel
    assert captured["max_tokens"] == extractor.MAX_OUTPUT_TOKENS == 1600
    assert captured["temperature"] == 0
    assert captured["model_kwargs"] == {
        "response_format": {"type": "json_object"}
    }


def test_prompt_bounds_reference_arrays():
    assert "at most 20 Georgian Tax Code article numbers" in extractor.SYSTEM_PROMPT
    assert "array of at most 10" in extractor.SYSTEM_PROMPT
