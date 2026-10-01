"""Exercise the real live entry point with only DB/model boundaries stubbed."""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from core.config import settings as app_settings
from rag_v2.jev_router import RoutingDecision
from rag_v2.models import QuestionClassification
from rag_v2.pipeline_v2 import PipelineV2
from rag_v2 import dispute_context


@pytest.fixture
def live(monkeypatch):
    rag = ModuleType("rag")
    rag.__path__ = []
    pipeline = ModuleType("rag.pipeline")
    pipeline.rag_pipeline = SimpleNamespace()
    database = ModuleType("core.database")
    database.SessionLocal = lambda: None
    models = ModuleType("models")
    models.Document = models.DocumentChunk = object
    with monkeypatch.context() as imports:
        for name, module in {"rag": rag, "rag.pipeline": pipeline, "core.database": database, "models": models}.items():
            imports.setitem(sys.modules, name, module)
        path = Path(__file__).parents[1] / "rag_v2/live_runtime.py"
        spec = importlib.util.spec_from_file_location("rag_v2._jev_integration_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    module.settings = app_settings.model_copy(update={"JEV_MODE": "off", "TYPESAFE_API_KEY": None})
    monkeypatch.setattr(module, "_mode", lambda: "rollout")
    monkeypatch.setattr(module, "out_of_scope_response", lambda _: None)
    monkeypatch.setattr(module, "direct_tax_faq_response", lambda _: None)
    monkeypatch.setattr(module, "match_tax_faq_entry", lambda *_: None)
    # Keep singleton state shared by production modules untouched.
    module.jev_router = SimpleNamespace(decide=lambda p, c, o: RoutingDecision(c, "off"))
    module.pipeline_v2 = SimpleNamespace(build_trace=lambda *a, **kw: pytest.fail("unexpected retrieval"))
    return module


@pytest.mark.parametrize("guard", ["scope", "contract"])
def test_scope_and_curated_answers_bypass_jev(live, monkeypatch, guard):
    live.jev_router.decide = lambda *_: pytest.fail("protected answer must not call Jev")
    if guard == "scope":
        monkeypatch.setattr(live, "out_of_scope_response", lambda _: "Out of scope")
    else:
        monkeypatch.setattr(live, "direct_tax_faq_response", lambda _: "Curated answer")
        monkeypatch.setattr(live, "_curated_source", lambda *a, **kw: {"title": "Verified"})
    result = live.maybe_run_live_rollout(query="Test question", language="en")
    assert result["response"] == ("Out of scope" if guard == "scope" else "Curated answer")


@pytest.mark.parametrize("language", ["ru", "en", "ka"])
def test_clarification_returns_without_retrieval_or_generation(live, language):
    live.jev_router.decide = lambda p, c, o: RoutingDecision(c, "clarification", True)
    result = live.maybe_run_live_rollout(query="Help with this", language=language)
    assert result["_rag_v2"]["mode"] == "rollout_clarification"
    assert result["sources"] == []
    assert result["retrieved_count"] == 0
    assert result["response"]


@pytest.mark.parametrize("changed", [False, True])
def test_live_entry_passes_admitted_route_to_retrieval(live, changed):
    selected = QuestionClassification("dispute_practice", .99)
    live.jev_router.decide = lambda p, c, o: RoutingDecision(selected if changed else c, "applied" if changed else "off")
    calls = []

    class ReachedRetrieval(Exception):
        pass

    def build(query, **kwargs):
        calls.append(kwargs)
        raise ReachedRetrieval()

    live.pipeline_v2.build_trace = build
    with pytest.raises(ReachedRetrieval):
        live.maybe_run_live_rollout(query="Find court precedents", language="en")
    assert (calls[0].get("classification_override") is selected) is changed


@pytest.mark.parametrize("reference", [None, "decision_ref", "document_ref"])
def test_dispute_prompt_requires_number_match_only_for_requested_reference(live, reference):
    parsed = {"language": "ru"}
    if reference:
        parsed[reference] = "123/2025"
    trace = SimpleNamespace(parsed_query=parsed, reranking={},
                            classification={"question_class": "dispute_practice"})
    prompt = live._generation_query("Summarize the retrieved decision", trace, "Excerpt")
    assert "Answer in Russian" in prompt
    if reference:
        assert "confirmed match for the dispute number" in prompt
        assert "No specific dispute number was requested" not in prompt
    else:
        assert "confirmed match for the dispute number" not in prompt
        assert "No specific dispute number was requested" in prompt
        assert "do not infer an outcome" in prompt
        assert "explicitly present in the retrieved excerpts" in prompt


def test_pipeline_uses_override_for_candidate_channels(monkeypatch):
    import rag_v2.pipeline_v2 as module
    captured = []

    def generate(parsed, routing_profile):
        captured.append(routing_profile)
        return {}

    monkeypatch.setattr(module, "generate_candidates", generate)
    pipeline = PipelineV2()
    baseline = pipeline.build_trace("Find court precedents", language="en")
    admitted = pipeline.build_trace("Find court precedents", language="en",
                                    classification_override=QuestionClassification("dispute_practice", .99))
    assert baseline.classification["question_class"] == "canonical_law_lookup"
    assert admitted.routing["retrieval_mode"] == "dispute_first"
    assert admitted.routing["primary_source_classes"] == ["court_decision"]
    assert len(captured) == 2


@pytest.mark.parametrize("language,refusal", [
    ("ru", "В предоставленных официальных источниках ответ на этот вопрос не найден."),
    ("en", "In the provided official sources, the answer to this question was not found."),
    ("ka", "მოწოდებულ ოფიციალურ წყაროებში ამ კითხვაზე პასუხი ვერ მოიძებნა."),
])
def test_dispute_refusal_cannot_become_grounded_by_appended_statistics(live, monkeypatch, language, refusal):
    from api.evidence import attach_evidence

    trace = SimpleNamespace(
        parsed_query={"language": language}, classification={"question_class": "dispute_practice"},
        source_audit={"passed": True}, candidate_generation={}, reranking={},
    )
    live.pipeline_v2.build_trace = lambda *args, **kwargs: trace
    monkeypatch.setattr(live, "small_business_legal_form_response", lambda _: None)
    monkeypatch.setattr(live, "tax_appeal_procedure_response", lambda _: None)
    monkeypatch.setenv("INFOHUB_RAG_V2_AUTHORITATIVE", "0")
    monkeypatch.setattr(live, "_build_rollout_chunks", lambda _: [{"content": "Related but insufficient source"}])
    monkeypatch.setattr(live, "_generation_query", lambda query, *args: query)
    monkeypatch.setattr(live, "import_vat_response", lambda _: None)
    monkeypatch.setattr(live, "finalize_rollout_response", lambda response, _: response)
    monkeypatch.setattr(live, "_dispute_stats_line", lambda _: pytest.fail("Refusal must not receive unrelated statistics"))
    live.rag_pipeline._assemble_context = lambda _: "Related but insufficient source"
    live.rag_pipeline.llm = SimpleNamespace(generate_response=lambda **kwargs: refusal)
    live.rag_pipeline._prepare_sources = lambda _: [{"url": "https://infohub.rs.ge/example"}]

    result = attach_evidence(live.maybe_run_live_rollout(query="Find court precedents", language=language))
    assert result["response"] == refusal
    assert result["sources"] == []
    assert result["evidence"]["status"] == "insufficient"


@pytest.mark.parametrize("question_class", ["dispute_practice", "canonical_law_lookup"])
def test_admitted_route_controls_actual_vector_filter(monkeypatch, question_class):
    from rag_v2 import candidate_generators as generators

    filters = []

    def search(*, query_embedding, n_results, where):
        filters.append(where)
        kind = where["document_types"][0]
        return {"ids": [[kind]], "documents": [["Synthetic source evidence"]],
                "metadatas": [[{"document_id": kind, "document_type": kind,
                                "title": "Synthetic source", "source_url": "https://example.org/source"}]],
                "distances": [[0.1]]}

    def legacy_hints(*args, **kwargs):
        pytest.fail("The admitted route must not be reclassified by legacy hints")

    rag = ModuleType("rag")
    rag.__path__ = []
    pipeline = ModuleType("rag.pipeline")
    pipeline.rag_pipeline = SimpleNamespace(
        _retrieval_query=lambda query, language: query,
        embeddings=SimpleNamespace(encode_query=lambda query: [0.1]),
        vector_store=SimpleNamespace(search=search),
        _extract_query_hints=legacy_hints,
    )
    monkeypatch.setitem(sys.modules, "rag", rag)
    monkeypatch.setitem(sys.modules, "rag.pipeline", pipeline)
    monkeypatch.setattr(generators, "CHANNEL_BUILDERS", {"semantic_search": generators.semantic_candidates})
    trace = PipelineV2().build_trace(
        "Find court precedents where judges overturned an additional VAT assessment.",
        language="en", classification_override=QuestionClassification(question_class, .99),
    )
    assert trace.source_audit["passed"]
    assert filters
    if question_class == "dispute_practice":
        assert filters == [{"document_types": ["court_decision"]}]
        assert trace.reranking["top_ranked_documents"][0]["document_type"] == "court_decision"
    else:
        assert all("court_decision" not in item["document_types"] for item in filters)
        assert trace.reranking["top_ranked_documents"][0]["document_type"] == "law"


@pytest.mark.parametrize("anchor", ["Matched heading", "x" * 467, "x" * 786, "x" * 1499])
def test_short_dispute_match_fetches_only_bounded_same_document_neighbors(monkeypatch, anchor):
    document_id = UUID("00000000-0000-0000-0000-000000000001")
    query = MagicMock()
    for method in ("filter", "order_by", "limit"):
        getattr(query, method).return_value = query
    query.all.return_value = [
        SimpleNamespace(chunk_index=1, content="Facts of this decision"),
        SimpleNamespace(chunk_index=2, content=anchor),
        SimpleNamespace(chunk_index=3, content="Reasoning of this decision"),
    ]
    session_factory = MagicMock()
    session_factory.return_value.__enter__.return_value.query.return_value = query
    monkeypatch.setattr(dispute_context, "SessionLocal", session_factory)
    doc = {"document_id": str(document_id), "document_type": "court_decision",
           "metadata": {"chunk_index": 2}}
    result = dispute_context.expand_dispute_context(doc, anchor, "dispute_practice")
    assert result == f"Facts of this decision\n\n{anchor}\n\nReasoning of this decision"
    assert query.filter.call_args_list[0].args[0].right.value == document_id
    bounds = query.filter.call_args_list[1].args
    assert [condition.right.value for condition in bounds] == [1, 4]
    query.limit.assert_called_once_with(4)


@pytest.mark.parametrize("kind,route,index,content", [
    ("law", "dispute_practice", 2, "Short"),
    ("court_decision", "canonical_law_lookup", 2, "Short"),
    ("court_decision", "dispute_practice", None, "Short"),
    ("court_decision", "dispute_practice", -1, "Short"),
    ("court_decision", "dispute_practice", True, "Short"),
    ("court_decision", "dispute_practice", 2, "x" * 1500),
])
def test_context_expansion_preserves_ineligible_matches(monkeypatch, kind, route, index, content):
    monkeypatch.setattr(dispute_context, "SessionLocal", lambda: pytest.fail("Unexpected DB lookup"))
    doc = {"document_id": "00000000-0000-0000-0000-000000000001",
           "document_type": kind, "metadata": {"chunk_index": index}}
    assert dispute_context.expand_dispute_context(doc, content, route) == content


def test_context_budget_preserves_anchor_and_never_uses_an_unmatched_document():
    anchor = "Matched heading"
    rows = [SimpleNamespace(chunk_index=1, content="x" * 6000),
            SimpleNamespace(chunk_index=2, content=anchor),
            SimpleNamespace(chunk_index=3, content="Bounded facts")]
    result = dispute_context._join_context(rows, anchor, 2)
    assert result == anchor + "\n\nBounded facts"
    assert len(result) <= 6000
    assert dispute_context._join_context(rows, anchor, 9) == anchor


def test_context_database_failure_preserves_original_match(monkeypatch):
    from sqlalchemy.exc import OperationalError
    factory = MagicMock(side_effect=OperationalError("lookup", {}, Exception("unavailable")))
    monkeypatch.setattr(dispute_context, "SessionLocal", factory)
    doc = {"document_id": "00000000-0000-0000-0000-000000000001",
           "document_type": "court_decision", "metadata": {"chunk_index": 2}}
    assert dispute_context.expand_dispute_context(doc, "Original heading", "dispute_practice") == "Original heading"
