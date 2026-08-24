from rag_v2.faq_tax_matrix import CANONICAL_TAX_CODE_SOURCE_URL
from rag_v2.official_provisions import (
    enrich_source,
    has_official_provision_link,
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

    assert len(registry["article_anchors"]) == 354
    assert registry["article_anchors"]["34"] == "part_41"
    assert registry["article_anchors"]["88"] == "part_108"
    assert registry["article_anchors"]["169"] == "part_557"
    assert registry["article_anchors"]["272"] == "part_345"


def test_general_administrative_code_registry_is_complete_and_verified():
    registries = {
        registry["registry_id"]: registry
        for registry in load_official_provision_registries()
    }
    registry = registries["general_administrative_code"]

    assert len(registry["article_anchors"]) == 233
    assert registry["article_anchors"]["177"] == "part_207"
    assert registry["article_anchors"]["180"] == "part_210"
    assert registry["article_anchors"]["201"] == "part_231"
    assert registry["article_anchors"]["271"] == "part_33"


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
