from rag_v2.faq_tax_matrix import CANONICAL_TAX_CODE_SOURCE_URL
from rag_v2.official_provisions import (
    enrich_source,
    has_official_provision_link,
    is_official_provision_link,
    load_official_provision_registries,
    load_tax_code_registry,
)


def _source(**overrides):
    source = {
        "title": "საქართველოს საგადასახადო კოდექსი",
        "url": CANONICAL_TAX_CODE_SOURCE_URL,
    }
    source.update(overrides)
    return source


def test_registry_is_complete_and_contains_verified_key_articles():
    registry = load_tax_code_registry()

    assert len(registry["article_anchors"]) == 326
    assert registry["article_anchors"]["34"] == "part_41"
    assert registry["article_anchors"]["88"] == "part_108"
    assert registry["article_anchors"]["169"] == "part_557"
    assert registry["article_anchors"]["272"] == "part_345"
    assert registry["article_anchors"]["288-2"] == "part_430"
    assert "208" not in registry["article_anchors"]


def test_general_administrative_code_registry_is_complete_and_verified():
    registries = {
        registry["registry_id"]: registry
        for registry in load_official_provision_registries()
    }
    registry = registries["general_administrative_code"]

    assert len(registry["article_anchors"]) == 232
    assert registry["article_anchors"]["177"] == "part_207"
    assert registry["article_anchors"]["180"] == "part_210"
    assert registry["article_anchors"]["201"] == "part_231"
    assert registry["article_anchors"]["27-1"] == "part_33"


def test_civil_code_registry_is_complete_and_verified():
    registries = {
        registry["registry_id"]: registry
        for registry in load_official_provision_registries()
    }
    registry = registries["civil_code"]

    assert len(registry["article_anchors"]) == 1595
    assert registry["article_anchors"]["18-1"] == "part_24"
    assert registry["article_anchors"]["623"] == "part_745"
    assert registry["article_anchors"]["624-1"] == "part_1838"
    assert registry["article_anchors"]["882-1"] == "part_1870"


def test_entrepreneurs_law_registry_uses_verified_structured_anchors():
    registries = {
        registry["registry_id"]: registry
        for registry in load_official_provision_registries()
    }
    registry = registries["entrepreneurs_law"]

    assert len(registry["article_anchors"]) == 256
    assert registry["article_anchors"]["1"] == (
        "DOCUMENT:1;PART:1;CHAPTER:1;ARTICLE:1;"
    )
    assert registry["article_anchors"]["34-1"] == (
        "DOCUMENT:1;PART:1;CHAPTER:5;ARTICLE:34_1;"
    )
    assert registry["article_anchors"]["208"] == (
        "DOCUMENT:1;PART:2;CHAPTER:14;ARTICLE:208;"
    )
    assert registry["article_anchors"]["255"] == (
        "DOCUMENT:1;PART:2;CHAPTER:16;ARTICLE:255;"
    )


def test_entrepreneurs_law_article_gets_exact_structured_official_link():
    source = enrich_source(
        {
            "title": "მეწარმეთა შესახებ საქართველოს კანონი",
            "url": "https://infohub.rs.ge/ka/workspace/document/1f5a284f-9bf6-4109-afde-63d3afaeb09e",
            "article_ref": "208",
        }
    )

    assert source["official_act_url"] == "https://matsne.gov.ge/ka/document/view/5230186"
    assert source["provision_links"] == [
        {
            "article_ref": "208",
            "point_ref": None,
            "url": (
                "https://matsne.gov.ge/ka/document/view/5230186"
                "#DOCUMENT:1;PART:2;CHAPTER:14;ARTICLE:208;"
            ),
        }
    ]
    assert source["provision_publication_url"].endswith("?publication=13")
    assert has_official_provision_link(source) is True


def test_malformed_structured_official_link_is_rejected():
    valid = {
        "article_ref": "208",
        "url": (
            "https://matsne.gov.ge/ka/document/view/5230186"
            "#DOCUMENT:1;PART:2;CHAPTER:14;ARTICLE:208;"
        ),
    }
    malformed = {
        "article_ref": "208",
        "url": (
            "https://matsne.gov.ge/ka/document/view/5230186"
            "#DOCUMENT:1;PART:2;CHAPTER:14;ARTICLE:208;javascript"
        ),
    }

    assert is_official_provision_link(valid) is True
    assert is_official_provision_link(malformed) is False


def test_civil_code_article_gets_exact_official_link():
    source = enrich_source(
        {
            "title": "საქართველოს სამოქალაქო კოდექსი",
            "url": "https://infohub.rs.ge/ka/workspace/document/1aa5b5a8-f2d6-4858-b2dc-642a4068bf98",
            "article_ref": "623",
        }
    )

    assert source["official_act_url"] == "https://matsne.gov.ge/ka/document/view/31702"
    assert source["provision_links"] == [
        {
            "article_ref": "623",
            "point_ref": None,
            "url": "https://matsne.gov.ge/ka/document/view/31702#part_745",
        }
    ]
    assert source["provision_publication_url"].endswith("?publication=140")
    assert has_official_provision_link(source) is True


def test_general_administrative_code_article_gets_exact_official_link():
    source = enrich_source(
        {
            "title": "საქართველოს ზოგადი ადმინისტრაციული კოდექსი",
            "url": "https://infohub.rs.ge/ka/workspace/document/8e288090-11dc-497e-a867-ff233c9d79e7",
            "article_ref": "180",
        }
    )

    assert source["official_act_url"] == "https://matsne.gov.ge/ka/document/view/16270"
    assert source["provision_links"] == [
        {
            "article_ref": "180",
            "point_ref": None,
            "url": "https://matsne.gov.ge/ka/document/view/16270#part_210",
        }
    ]
    assert source["provision_publication_url"].endswith("?publication=45")
    assert has_official_provision_link(source) is True


def test_hyphenated_superscript_article_uses_verified_anchor():
    source = enrich_source(
        {
            "url": "https://infohub.rs.ge/ka/workspace/document/8e288090-11dc-497e-a867-ff233c9d79e7",
            "article_ref": "27-1",
        }
    )

    assert source["provision_links"][0]["article_ref"] == "27-1"
    assert source["provision_links"][0]["url"].endswith("#part_33")


def test_superscript_article_does_not_collide_with_plain_article_number():
    superscript = enrich_source(_source(article_ref="288²"))
    hyphenated = enrich_source(_source(article_ref="288-2"))
    ambiguous_removed = enrich_source(_source(article_ref="208"))

    assert superscript["provision_links"][0]["url"].endswith("#part_430")
    assert hyphenated["provision_links"][0]["url"].endswith("#part_430")
    assert "provision_links" not in ambiguous_removed


def test_canonical_article_source_gets_official_act_and_provision_link():
    source = enrich_source(_source(article_ref="88"))

    assert source["official_act_url"] == "https://matsne.gov.ge/ka/document/view/1043717"
    assert source["provision_links"] == [
        {
            "article_ref": "88",
            "point_ref": None,
            "url": "https://matsne.gov.ge/ka/document/view/1043717#part_108",
        }
    ]
    assert source["provision_publication_url"].endswith("?publication=245")
    assert has_official_provision_link(source) is True


def test_multiple_range_and_point_references_are_linked_precisely():
    multiple = enrich_source(_source(article_ref="88, 90"))
    ranged = enrich_source(_source(article_ref="97–98"))
    point = enrich_source(_source(point_ref="169.1"))
    superscript = enrich_source(_source(article_ref="165¹"))

    assert [link["article_ref"] for link in multiple["provision_links"]] == ["88", "90"]
    assert [link["article_ref"] for link in ranged["provision_links"]] == ["97", "98"]
    assert point["provision_links"][0] == {
        "article_ref": "169",
        "point_ref": "169.1",
        "url": "https://matsne.gov.ge/ka/document/view/1043717#part_557",
    }
    assert superscript["provision_links"][0]["article_ref"] == "165¹"
    assert superscript["provision_links"][0]["url"].endswith("#part_551")


def test_noncanonical_source_is_not_enriched():
    source = enrich_source(
        {
            "url": "https://infohub.rs.ge/ka/workspace/document/another-document",
            "article_ref": "88",
        }
    )

    assert "provision_links" not in source
    assert has_official_provision_link(source) is False


def test_unverified_links_are_removed_but_verified_generic_matsne_links_survive():
    unsafe = enrich_source(
        {
            "url": "https://infohub.rs.ge/ka/workspace/document/another-document",
            "official_act_url": "https://example.com/act",
            "provision_links": [
                {"article_ref": "5", "url": "https://example.com/act#part_5"}
            ],
        }
    )
    verified = enrich_source(
        {
            "url": "https://infohub.rs.ge/ka/workspace/document/another-document",
            "official_act_url": "https://matsne.gov.ge/ka/document/view/999",
            "provision_links": [
                {
                    "article_ref": "5",
                    "point_ref": None,
                    "url": "https://matsne.gov.ge/ka/document/view/999#part_5",
                }
            ],
        }
    )

    assert "official_act_url" not in unsafe
    assert "provision_links" not in unsafe
    assert has_official_provision_link(verified) is True
