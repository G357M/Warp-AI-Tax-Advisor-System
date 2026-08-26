import pytest

import rag_v2.db_exact_lookup as db_exact_lookup
from rag_v2.article_resolver import resolve_article
from rag_v2.citation_resolver import resolve_citations
from rag_v2.official_provisions import enrich_source, has_official_provision_link
from rag_v2.point_resolver import resolve_point
from rag_v2.pipeline_v2 import pipeline_v2
from rag_v2.query_parser import parse_query


GENERAL_ADMIN_SOURCE = (
    "https://infohub.rs.ge/ka/workspace/document/"
    "8e288090-11dc-497e-a867-ff233c9d79e7"
)
ORDER_996_SOURCE = (
    "https://infohub.rs.ge/ka/workspace/document/"
    "fe1cc7b3-a080-4283-85dd-ea9c9f85d947"
)
CIVIL_CODE_SOURCE = (
    "https://infohub.rs.ge/ka/workspace/document/"
    "1aa5b5a8-f2d6-4858-b2dc-642a4068bf98"
)
ENTREPRENEURS_LAW_SOURCE = (
    "https://infohub.rs.ge/ka/workspace/document/"
    "1f5a284f-9bf6-4109-afde-63d3afaeb09e"
)
LABOUR_CODE_SOURCE = (
    "https://infohub.rs.ge/ka/workspace/document/"
    "c16095a8-2c94-4024-8d25-561192e0ceb7"
)


@pytest.mark.parametrize(
    ("query", "language"),
    [
        (
            "Что устанавливает статья 180 Общего административного кодекса Грузии?",
            "ru",
        ),
        (
            "What does Article 180 of the General Administrative Code of Georgia provide?",
            "en",
        ),
        (
            "რას ადგენს საქართველოს ზოგადი ადმინისტრაციული კოდექსის 180-ე მუხლი?",
            "ka",
        ),
    ],
)
def test_named_general_administrative_code_article_resolves_in_all_languages(
    query, language
):
    parsed = parse_query(query, language=language)
    candidates = resolve_article(parsed)

    assert parsed.article_ref == "180"
    assert len(candidates) == 1
    assert candidates[0].source_url == GENERAL_ADMIN_SOURCE
    assert candidates[0].metadata["article_ref"] == "180"
    assert candidates[0].metadata["section_label"] == "მუხლი 180"


def test_named_general_administrative_code_point_resolves_to_same_act():
    parsed = parse_query(
        "Что устанавливает статья 180 пункт 1 Общего административного кодекса Грузии?",
        language="ru",
    )
    candidates = resolve_point(parsed)

    assert len(candidates) == 1
    assert candidates[0].source_url == GENERAL_ADMIN_SOURCE
    assert candidates[0].metadata["article_ref"] == "180"
    assert candidates[0].metadata["point_ref"] == "180.1"


@pytest.mark.parametrize(
    ("query", "language"),
    [
        ("Что устанавливает статья 623 Гражданского кодекса Грузии?", "ru"),
        ("What does Article 623 of the Civil Code of Georgia provide?", "en"),
        ("რას ადგენს საქართველოს სამოქალაქო კოდექსის 623-ე მუხლი?", "ka"),
    ],
)
def test_named_civil_code_article_resolves_in_all_languages(query, language):
    parsed = parse_query(query, language=language)
    candidates = resolve_article(parsed)

    assert parsed.article_ref == "623"
    assert len(candidates) == 1
    assert candidates[0].source_url == CIVIL_CODE_SOURCE
    assert candidates[0].metadata["article_ref"] == "623"
    assert candidates[0].metadata["section_label"] == "მუხლი 623"

    source = enrich_source(
        {
            "url": candidates[0].source_url,
            "article_ref": candidates[0].metadata["article_ref"],
        }
    )
    assert source["provision_links"][0]["url"].endswith("#part_745")
    assert has_official_provision_link(source) is True


@pytest.mark.parametrize(
    ("query", "language"),
    [
        ("Что устанавливает статья 208 Закона Грузии о предпринимателях?", "ru"),
        ("What does Article 208 of the Law of Georgia on Entrepreneurs provide?", "en"),
        ("რას ადგენს „მეწარმეთა შესახებ“ საქართველოს კანონის 208-ე მუხლი?", "ka"),
    ],
)
def test_named_entrepreneurs_law_article_resolves_in_all_languages(query, language):
    parsed = parse_query(query, language=language)
    candidates = resolve_article(parsed)

    assert parsed.article_ref == "208"
    assert len(candidates) == 1
    assert candidates[0].source_url == ENTREPRENEURS_LAW_SOURCE
    assert candidates[0].metadata["article_ref"] == "208"
    assert candidates[0].metadata["section_label"] == "მუხლი 208"

    source = enrich_source(
        {
            "url": candidates[0].source_url,
            "article_ref": candidates[0].metadata["article_ref"],
        }
    )
    assert source["provision_links"][0]["url"].endswith(
        "#DOCUMENT:1;PART:2;CHAPTER:14;ARTICLE:208;"
    )
    assert has_official_provision_link(source) is True


@pytest.mark.parametrize(
    ("query", "language"),
    [
        ("Что устанавливает статья 47 Трудового кодекса Грузии?", "ru"),
        ("What does Article 47 of the Labour Code of Georgia provide?", "en"),
        ("რას ადგენს საქართველოს შრომის კოდექსის 47-ე მუხლი?", "ka"),
    ],
)
def test_named_labour_code_article_resolves_in_all_languages(query, language):
    parsed = parse_query(query, language=language)
    candidates = resolve_article(parsed)

    assert parsed.article_ref == "47"
    assert len(candidates) == 1
    assert candidates[0].source_url == LABOUR_CODE_SOURCE
    assert candidates[0].metadata["article_ref"] == "47"
    assert candidates[0].metadata["section_label"] == "მუხლი 47"

    source = enrich_source(
        {
            "url": candidates[0].source_url,
            "article_ref": candidates[0].metadata["article_ref"],
        }
    )
    assert source["provision_links"][0]["url"].endswith("#part_173")
    assert has_official_provision_link(source) is True


@pytest.mark.parametrize(
    ("query", "language"),
    [
        ("Что устанавливает статья 47 приказа №996?", "ru"),
        ("What does Article 47 of Order No. 996 provide?", "en"),
        ("რას ადგენს №996 ბრძანების 47-ე მუხლი?", "ka"),
    ],
)
def test_order_996_keeps_exact_article_metadata_without_fabricated_deep_link(
    query, language
):
    parsed = parse_query(query, language=language)
    candidates = resolve_citations(parsed)

    assert parsed.document_ref == "996"
    assert parsed.article_ref == "47"
    assert len(candidates) == 1
    assert candidates[0].source_url == ORDER_996_SOURCE
    assert candidates[0].metadata["article_ref"] == "47"
    assert candidates[0].metadata["section_label"] == "მუხლი 47"

    source = enrich_source(
        {
            "url": candidates[0].source_url,
            "article_ref": candidates[0].metadata["article_ref"],
        }
    )
    assert has_official_provision_link(source) is False
    assert "provision_links" not in source


def test_database_document_number_match_preserves_requested_article(monkeypatch):
    parsed = parse_query("Что устанавливает статья 47 приказа №996?", language="ru")
    monkeypatch.setattr(db_exact_lookup, "db_available", lambda: True)
    monkeypatch.setattr(
        db_exact_lookup,
        "run_query",
        lambda sql, params: [
            {
                "document_id": "54d15b6c-e8a1-465a-bc56-8c20498588b8",
                "title": "გადასახადების ადმინისტრირების შესახებ.",
                "document_type": "regulation",
                "source_url": ORDER_996_SOURCE,
                "document_number": "996",
            }
        ],
    )

    candidate = db_exact_lookup.resolve_exact_from_backend(parsed)[0]

    assert candidate.metadata["article_ref"] == "47"
    assert candidate.metadata["section_label"] == "მუხლი 47"


@pytest.mark.parametrize(
    ("query", "language"),
    [
        (
            "Что устанавливает статья 180 Общего административного кодекса Грузии?",
            "ru",
        ),
        (
            "What does Article 180 of the General Administrative Code of Georgia provide?",
            "en",
        ),
        (
            "რას ადგენს საქართველოს ზოგადი ადმინისტრაციული კოდექსის 180-ე მუხლი?",
            "ka",
        ),
    ],
)
def test_pipeline_prefers_named_general_administrative_code_article(
    query, language
):
    trace = pipeline_v2.build_trace(
        query,
        language=language,
        disabled_channels={"semantic_search"},
    )
    top = trace.reranking["top_ranked_documents"][0]

    assert top["document_id"] == "3f33cb75-b642-477e-9265-661b04571e5a"
    assert top["channel"] == "article_resolver"
    assert top["metadata"]["article_ref"] == "180"


@pytest.mark.parametrize(
    ("query", "language"),
    [
        ("Что устанавливает статья 623 Гражданского кодекса Грузии?", "ru"),
        ("What does Article 623 of the Civil Code of Georgia provide?", "en"),
        ("რას ადგენს საქართველოს სამოქალაქო კოდექსის 623-ე მუხლი?", "ka"),
    ],
)
def test_pipeline_prefers_named_civil_code_article(query, language):
    trace = pipeline_v2.build_trace(
        query,
        language=language,
        disabled_channels={"semantic_search"},
    )
    top = trace.reranking["top_ranked_documents"][0]

    assert top["document_id"] == "2d2f2e3c-78ce-49f1-94a6-b2580c0da1ef"
    assert top["channel"] == "article_resolver"
    assert top["metadata"]["article_ref"] == "623"


@pytest.mark.parametrize(
    ("query", "language"),
    [
        ("Что устанавливает статья 208 Закона Грузии о предпринимателях?", "ru"),
        ("What does Article 208 of the Law of Georgia on Entrepreneurs provide?", "en"),
        ("რას ადგენს „მეწარმეთა შესახებ“ საქართველოს კანონის 208-ე მუხლი?", "ka"),
    ],
)
def test_pipeline_prefers_named_entrepreneurs_law_article(query, language):
    trace = pipeline_v2.build_trace(
        query,
        language=language,
        disabled_channels={"semantic_search"},
    )
    top = trace.reranking["top_ranked_documents"][0]

    assert trace.classification["question_class"] == "canonical_law_lookup"
    assert top["document_id"] == "74d06788-7c76-420d-bb6c-0a79874dbc9e"
    assert top["channel"] == "article_resolver"
    assert top["metadata"]["article_ref"] == "208"


@pytest.mark.parametrize(
    ("query", "language"),
    [
        ("Что устанавливает статья 47 Трудового кодекса Грузии?", "ru"),
        ("What does Article 47 of the Labour Code of Georgia provide?", "en"),
        ("რას ადგენს საქართველოს შრომის კოდექსის 47-ე მუხლი?", "ka"),
    ],
)
def test_pipeline_prefers_named_labour_code_article(query, language):
    trace = pipeline_v2.build_trace(
        query,
        language=language,
        disabled_channels={"semantic_search"},
    )
    top = trace.reranking["top_ranked_documents"][0]

    assert trace.classification["question_class"] == "canonical_law_lookup"
    assert top["document_id"] == "a24ab0d4-4124-414e-aa99-b526839abdd3"
    assert top["channel"] == "article_resolver"
    assert top["metadata"]["article_ref"] == "47"


def test_pipeline_prefers_order_996_and_keeps_article_locator():
    trace = pipeline_v2.build_trace(
        "Что устанавливает статья 47 приказа №996?",
        language="ru",
        disabled_channels={"semantic_search"},
    )
    top = trace.reranking["top_ranked_documents"][0]

    assert top["document_id"] == "54d15b6c-e8a1-465a-bc56-8c20498588b8"
    assert top["channel"] == "citation_resolver"
    assert top["metadata"]["article_ref"] == "47"
