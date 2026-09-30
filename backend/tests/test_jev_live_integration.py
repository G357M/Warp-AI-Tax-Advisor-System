"""Exercise the real live entry point with only DB/model boundaries stubbed."""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

from core.config import settings as app_settings
from rag_v2.jev_router import RoutingDecision
from rag_v2.models import QuestionClassification
from rag_v2.pipeline_v2 import PipelineV2


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
    assert result["sources"] == [] and result["retrieved_count"] == 0 and result["response"]


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
