from datetime import datetime
from pathlib import Path

from api.evidence import attach_evidence
from api.schemas import EvidenceInfo, SourceInfo
from rag_v2.faq_tax_matrix import CANONICAL_TAX_CODE_SOURCE_URL


def _source(**overrides):
    source = {
        "document_id": "0a86a8b3-e0e6-4f89-8b35-6dd3909911f8",
        "title": "საქართველოს საგადასახადო კოდექსი",
        "document_type": "law",
        "url": CANONICAL_TAX_CODE_SOURCE_URL,
    }
    source.update(overrides)
    return source


def test_official_article_source_is_exactly_grounded():
    result = attach_evidence(
        {
            "response": "answer",
            "sources": [_source(article_ref="165")],
            "_rag_v2": {"mode": "rollout", "question_class": "canonical_law_lookup"},
        }
    )

    evidence = result["evidence"]
    assert evidence["status"] == "grounded"
    assert evidence["basis"] == "retrieval"
    assert evidence["coverage"] == "exact_provision"
    assert evidence["official_sources_only"] is True
    assert evidence["has_precise_citation"] is True
    assert evidence["has_official_provision_link"] is True
    assert result["sources"][0]["provision_links"][0]["url"].endswith(
        "1043717#part_550"
    )
    datetime.fromisoformat(evidence["generated_at"])


def test_official_document_without_article_is_document_level_grounding():
    evidence = attach_evidence({"sources": [_source()]})["evidence"]

    assert evidence["status"] == "grounded"
    assert evidence["coverage"] == "official_documents"
    assert evidence["has_precise_citation"] is False
    assert evidence["has_official_provision_link"] is False


def test_non_official_source_is_only_partial():
    evidence = attach_evidence(
        {
            "sources": [_source(url="https://example.com/commentary")],
        }
    )["evidence"]

    assert evidence["status"] == "partial"
    assert evidence["official_sources_only"] is False


def test_no_evidence_and_scope_responses_are_explicit():
    insufficient = attach_evidence(
        {
            "sources": [],
            "_rag_v2": {"mode": "rollout", "grounded_no_evidence": True},
        }
    )["evidence"]
    out_of_scope = attach_evidence(
        {
            "sources": [],
            "_rag_v2": {"mode": "rollout_scope"},
        }
    )["evidence"]

    assert insufficient["status"] == "insufficient"
    assert out_of_scope["status"] == "out_of_scope"


def test_pure_refusal_cannot_keep_unrelated_sources_or_grounded_status():
    result = attach_evidence(
        {
            "response": (
                "В предоставленных официальных источниках ответ на этот вопрос "
                "не найден."
            ),
            "sources": [_source(article_ref="168")],
            "retrieved_count": 5,
        }
    )

    assert result["sources"] == []
    assert result["retrieved_count"] == 0
    assert result["_rag_v2"]["grounded_no_evidence"] is True
    assert result["evidence"]["status"] == "insufficient"
    assert result["evidence"]["coverage"] == "none"
    assert result["evidence"]["source_count"] == 0


def test_authenticated_query_never_reuses_another_conversation_response():
    route = Path(__file__).parents[1] / "api" / "routes" / "query.py"
    source = route.read_text(encoding="utf-8")

    assert "cache_get(" not in source
    assert "cache_set(" not in source


def test_api_models_accept_curated_source_without_document_id():
    source = SourceInfo(
        title="საქართველოს საგადასახადო კოდექსი",
        document_type="law",
        url=CANONICAL_TAX_CODE_SOURCE_URL,
        relevance=1.0,
        article_ref="165",
    )
    evidence = EvidenceInfo(
        **attach_evidence({"sources": [source.model_dump()]})["evidence"]
    )

    assert source.document_id is None
    assert evidence.status == "grounded"
    assert evidence.has_official_provision_link is True
