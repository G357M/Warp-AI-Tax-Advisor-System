from scripts.build_official_provision_registry import (
    canonical_article_ref,
    extract_article_anchors,
)


def test_canonical_article_ref_handles_matsne_markup_and_superscripts():
    assert canonical_article_ref("<span>მუხლი 18</span><sup>1</sup>. ტექსტი") == "18-1"
    assert (
        canonical_article_ref(
            '<span>მუხლი 288</span><span>\u200b</span>'
            '<sup><span style="top:-3pt">3</span></sup>. ტექსტი'
        )
        == "288-3"
    )
    assert canonical_article_ref("მუხლი 27¹. ტექსტი") == "27-1"
    assert canonical_article_ref("[მუხლი 657. მომავალი რედაქცია]") is None


def test_registry_builder_excludes_future_and_ambiguous_fragments():
    tree = {
        "Title": "ROOT",
        "Anchor": "ROOT",
        "DocumentPart": [
            {"Title": "მუხლი 1. ტექსტი", "Anchor": "part_1"},
            {"Title": "მუხლი 18<sup>1</sup>. ტექსტი", "Anchor": "part_2"},
            {"Title": "მუხლი 207. ამოღებულია", "Anchor": "part_3"},
            {"Title": "მუხლი 208. ამოღებულია", "Anchor": "part_3"},
            {"Title": "მუხლი 300. მომავალი", "Anchor": "part_4", "Future": True},
        ],
    }

    anchors, future_count, ambiguous_count = extract_article_anchors(tree)

    assert anchors == {"1": "part_1", "18-1": "part_2"}
    assert future_count == 1
    assert ambiguous_count == 2


def test_registry_builder_accepts_strict_structured_matsne_anchor():
    tree = {
        "Title": "ROOT",
        "Anchor": "ROOT",
        "DocumentPart": [
            {
                "Title": "მუხლი 208. ინტერესთა კონფლიქტი",
                "Anchor": "DOCUMENT:1;PART:2;CHAPTER:14;ARTICLE:208;",
            }
        ],
    }

    anchors, future_count, ambiguous_count = extract_article_anchors(tree)

    assert anchors == {
        "208": "DOCUMENT:1;PART:2;CHAPTER:14;ARTICLE:208;"
    }
    assert future_count == 0
    assert ambiguous_count == 0


def test_registry_builder_rejects_malformed_structured_matsne_anchor():
    tree = {
        "Title": "ROOT",
        "Anchor": "ROOT",
        "DocumentPart": [
            {
                "Title": "მუხლი 208. ინტერესთა კონფლიქტი",
                "Anchor": "DOCUMENT:1;PART:2;CHAPTER:14;ARTICLE:208;javascript",
            }
        ],
    }

    try:
        extract_article_anchors(tree)
    except ValueError as exc:
        assert "invalid anchor for article 208" in str(exc)
    else:
        raise AssertionError("malformed structured anchor must fail closed")
