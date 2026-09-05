from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from legal_temporal.publication_editions import (
    BUNDLE_CONTRACT,
    PublicationEditionValidationError,
    build_bundle_proposals,
    build_proposals,
    extract_article_sections,
    query_provision,
    read_manifest,
    read_proposals,
    sha256_json,
    summarize,
    validate_and_extract_bundle,
)


def _tree(article_refs):
    return {
        "Title": "ROOT",
        "Anchor": "ROOT",
        "DocumentPart": [
            {
                "Title": f"მუხლი {ref.replace('-', '<sup>', 1) + ('</sup>' if '-' in ref else '')}. სათაური",
                "Anchor": f"part_{index}",
            }
            for index, ref in enumerate(article_refs, 1)
        ],
    }


def _page(publication, valid_from, articles):
    body = []
    for index, (ref, text) in enumerate(articles.items(), 1):
        display = ref.replace("-", "<sup>", 1) + ("</sup>" if "-" in ref else "")
        body.append(
            f'<a id="part_{index}"></a><section><h2>მუხლი {display}. სათაური</h2>'
            f"<p>{text}</p></section>"
        )
    return (
        "<!doctype html><html><body>"
        f"<div class=metadata>რედაქცია {publication}; ძალაშია {valid_from}</div>"
        f'<main><div id="document-content">{"".join(body)}</div></main>'
        "<footer>ეს ტექსტი სტატიაში არ უნდა მოხვდეს</footer>"
        "</body></html>"
    ).encode()


def _write_bundle(tmp_path, edition_specs):
    bundle = tmp_path / "evidence"
    (bundle / "editions").mkdir(parents=True)
    editions = []
    for publication, valid_from, articles in edition_specs:
        page = _page(publication, valid_from, articles)
        tree = json.dumps(_tree(articles), ensure_ascii=False).encode()
        page_file = f"editions/{publication:03d}.html"
        tree_file = f"editions/{publication:03d}.tree.json"
        (bundle / page_file).write_bytes(page)
        (bundle / tree_file).write_bytes(tree)
        page_sha = hashlib.sha256(page).hexdigest()
        editions.append(
            {
                "publication": publication,
                "valid_from": valid_from,
                "page_url": f"https://matsne.gov.ge/ka/document/view/1043717?publication={publication}",
                "page_file": page_file,
                "page_sha256": page_sha,
                "tree_url": f"https://matsne.gov.ge/ka/document/tree/1043717/{publication}",
                "tree_file": tree_file,
                "tree_sha256": hashlib.sha256(tree).hexdigest(),
                "expected_article_count": len(articles),
                "effective_date_evidence": {
                    "official_url": f"https://matsne.gov.ge/ka/document/view/1043717?publication={publication}",
                    "file": page_file,
                    "sha256": page_sha,
                    "quote": f"ძალაშია {valid_from}",
                },
            }
        )
    manifest = {
        "contract": BUNDLE_CONTRACT,
        "act": {
            "act_key": "ge-tax-code",
            "document_id": "1043717",
            "title_ka": "საქართველოს საგადასახადო კოდექსი",
            "language": "ka",
            "official_document_url": "https://matsne.gov.ge/ka/document/view/1043717",
        },
        "editions": editions,
    }
    manifest_path = bundle / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    return bundle, manifest, manifest_sha


@pytest.fixture
def evidence(tmp_path):
    return _write_bundle(
        tmp_path,
        [
            (0, "2020-01-01", {"1": "ძველი ტექსტი", "2": "მეორე მუხლი"}),
            (1, "2021-01-01", {"1": "ძველი ტექსტი"}),
            (2, "2022-01-01", {"1": "ახალი ტექსტი", "2": "მეორე მუხლი დაბრუნდა"}),
        ],
    )


def test_exact_editions_build_coalesced_versions_gaps_and_pins(evidence, tmp_path):
    bundle, _, manifest_sha = evidence
    identity, editions = validate_and_extract_bundle(
        bundle, expected_manifest_sha256=manifest_sha
    )
    assert identity["manifest_sha256"] == manifest_sha
    assert editions[0]["articles"]["1"]["authoritative_text_ka"] == (
        "მუხლი 1. სათაური ძველი ტექსტი"
    )
    assert "footer" not in editions[-1]["articles"]["2"]["authoritative_text_ka"]
    report = build_proposals(identity, editions)
    one = next(t for t in report["article_timelines"] if t["article_ref"] == "1")
    assert [(v["valid_from"], v["valid_to"]) for v in one["versions"]] == [
        ("2020-01-01", "2022-01-01"),
        ("2022-01-01", None),
    ]
    two = next(t for t in report["article_timelines"] if t["article_ref"] == "2")
    assert two["coverage_gaps"] == [
        {
            "valid_from": "2021-01-01",
            "valid_to": "2022-01-01",
            "publication": 1,
            "reason": "article_missing_between_observed_editions",
        }
    ]
    assert report["summary"] == {
        "captured_editions": 3,
        "effective_dates": 3,
        "same_day_editions_not_materialized": 0,
        "distinct_articles": 2,
        "version_proposals": 4,
        "coverage_gaps": 1,
        "future_article_nodes_excluded": 0,
        "ambiguous_article_nodes_excluded": 0,
    }
    assert not report["database_writes_allowed"]
    assert not report["public_answer_routing_changed"]
    assert report["authoritative_versions_created"] == 0

    output = tmp_path / "proposals.json"
    written = build_bundle_proposals(
        bundle, output, expected_manifest_sha256=manifest_sha
    )
    loaded = read_proposals(
        output, expected_proposal_sha256=written["proposal_sha256"]
    )
    assert loaded == written
    assert summarize(loaded)["coverage_gaps"] == 1
    if os.name != "nt":
        assert output.stat().st_mode & 0o077 == 0
    with pytest.raises(PublicationEditionValidationError, match="already exists"):
        build_bundle_proposals(bundle, output, expected_manifest_sha256=manifest_sha)
    with pytest.raises(PublicationEditionValidationError, match="outside"):
        build_bundle_proposals(
            bundle, bundle / "proposals.json", expected_manifest_sha256=manifest_sha
        )


def test_query_uses_half_open_intervals_and_refuses_gaps(evidence, tmp_path):
    bundle, _, manifest_sha = evidence
    output = tmp_path / "proposals.json"
    report = build_bundle_proposals(
        bundle, output, expected_manifest_sha256=manifest_sha
    )
    assert query_provision(report, article_ref="1", as_of="2021-12-31")["version"][
        "publication"
    ] == 0
    assert query_provision(report, article_ref="1", as_of="2022-01-01")["version"][
        "publication"
    ] == 2
    assert query_provision(report, article_ref="2", as_of="2021-06-01")["status"] == (
        "coverage_gap"
    )
    assert query_provision(report, article_ref="2", as_of="2019-12-31")["status"] == (
        "not_in_observed_force"
    )
    assert query_provision(report, article_ref="999", as_of="2022-01-01")["status"] == (
        "unknown_article"
    )
    assert query_provision(report, article_ref="1", as_of="2022-01-01")[
        "authoritative_for_public_answers"
    ] is False
    with pytest.raises(PublicationEditionValidationError, match="canonical"):
        query_provision(report, article_ref="01", as_of="2022-01-01")
    with pytest.raises(PublicationEditionValidationError, match="valid date"):
        query_provision(report, article_ref="1", as_of="2022-02-30")


def test_same_day_publications_select_final_consolidated_state(tmp_path):
    bundle, _, manifest_sha = _write_bundle(
        tmp_path,
        [
            (0, "2020-01-01", {"1": "საწყისი"}),
            (1, "2021-01-01", {"1": "შუალედური"}),
            (2, "2021-01-01", {"1": "საბოლოო იმავე დღეს"}),
        ],
    )
    identity, editions = validate_and_extract_bundle(
        bundle, expected_manifest_sha256=manifest_sha
    )
    report = build_proposals(identity, editions)
    assert report["summary"]["effective_dates"] == 2
    assert report["same_day_editions_not_materialized"] == [
        {
            "publication": 1,
            "valid_from": "2021-01-01",
            "superseded_by_publication": 2,
            "reason": "later_consolidated_publication_on_same_valid_date",
        }
    ]
    answer = query_provision(report, article_ref="1", as_of="2021-01-01")
    assert answer["version"]["publication"] == 2


def test_superscript_and_tree_exclusions_are_deterministic():
    tree = {
        "Title": "ROOT",
        "Anchor": "ROOT",
        "DocumentPart": [
            {"Title": "მუხლი 18<sup>1</sup>. აქტიური", "Anchor": "part_1"},
            {"Title": "[მუხლი 19. მომავალი]", "Anchor": "part_2", "Future": True},
            {"Title": "მუხლი 20. ამოღებულია", "Anchor": "part_3"},
            {"Title": "მუხლი 21. ამოღებულია", "Anchor": "part_3"},
        ],
    }
    page = (
        '<html><body><div id="document-content"><a id="part_1"></a>'
        "<h2>მუხლი 18<sup>1</sup>. აქტიური</h2><p>ზუსტი ტექსტი</p>"
        "</div></body></html>"
    ).encode()
    articles, excluded = extract_article_sections(page, tree)
    assert list(articles) == ["18-1"]
    assert "18¹" in articles["18-1"]["authoritative_text_ka"]
    assert excluded == {
        "excluded_future_article_nodes": 1,
        "excluded_ambiguous_article_nodes": 2,
    }


def test_old_style_nbsp_heading_duplicate_name_and_singleton_tree_node_are_supported():
    tree = {
        "Title": "ROOT",
        "Anchor": "ROOT",
        "DocumentPart": {
            "Title": "თავი I",
            "Anchor": "part_1",
            "DocumentPart": {
                "Title": "&nbsp;&nbsp;&nbsp; მუხლი 1. სათაური",
                "Anchor": "part_2",
            },
        },
    }
    page = (
        '<html><body><div id="document-content">'
        '<a class="oldStyleDocumentPart" name="part_2"></a>'
        '<section><h2><a class="oldStyleDocumentPart" name="part_2">'
        '<span>&nbsp;&nbsp;&nbsp; მუხლი 1. სათაური</span></a></h2>'
        '<p>ოფიციალური ტექსტი</p></section></div></body></html>'
    ).encode()

    articles, excluded = extract_article_sections(page, tree)

    assert list(articles) == ["1"]
    assert articles["1"]["anchor"] == "part_2"
    assert articles["1"]["authoritative_text_ka"] == (
        "მუხლი 1. სათაური ოფიციალური ტექსტი"
    )
    assert excluded == {
        "excluded_future_article_nodes": 0,
        "excluded_ambiguous_article_nodes": 0,
    }


@pytest.mark.parametrize(
    "mutate,error",
    [
        (lambda manifest: manifest["act"].update(language="ru"), "Georgian"),
        (lambda manifest: manifest["editions"][0].update(publication=True), "integer"),
        (lambda manifest: manifest["editions"][0].update(page_url="https://evil.test/x"), "official Matsne"),
        (lambda manifest: manifest["editions"][0].update(page_file="../outside"), "safe relative"),
        (lambda manifest: manifest["editions"][0].update(page_sha256="0" * 64), "SHA-256 mismatch"),
        (lambda manifest: manifest["editions"][0].update(expected_article_count=99), "article count mismatch"),
        (lambda manifest: manifest["editions"][0]["effective_date_evidence"].update(quote="invented quote"), "not verbatim"),
    ],
)
def test_manifest_identity_hash_path_count_and_quote_fail_closed(
    tmp_path, mutate, error
):
    bundle, manifest, _ = _write_bundle(
        tmp_path, [(0, "2020-01-01", {"1": "ტექსტი"})]
    )
    mutate(manifest)
    path = bundle / "manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    pin = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(PublicationEditionValidationError, match=error):
        validate_and_extract_bundle(bundle, expected_manifest_sha256=pin)


def test_manifest_pin_order_and_duplicate_files_fail_closed(tmp_path):
    bundle, manifest, pin = _write_bundle(
        tmp_path,
        [(0, "2020-01-01", {"1": "ა"}), (1, "2021-01-01", {"1": "ბ"})],
    )
    with pytest.raises(PublicationEditionValidationError, match="pin mismatch"):
        validate_and_extract_bundle(bundle, expected_manifest_sha256="0" * 64)
    manifest["editions"].reverse()
    path = bundle / "manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    pin = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(PublicationEditionValidationError, match="strictly increasing"):
        validate_and_extract_bundle(bundle, expected_manifest_sha256=pin)

    manifest["editions"].reverse()
    manifest["editions"][1]["page_file"] = manifest["editions"][0]["page_file"]
    manifest["editions"][1]["page_sha256"] = manifest["editions"][0]["page_sha256"]
    path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    pin = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(PublicationEditionValidationError, match="unique"):
        validate_and_extract_bundle(bundle, expected_manifest_sha256=pin)


@pytest.mark.parametrize(
    "html,error",
    [
        (b"<html><title>Access Denied</title></html>", "challenge response"),
        (
            b'<html><body><a id="part_1"></a><p>x</p></body></html>',
            "bounded document-content container",
        ),
        (
            b'<html><body><div><a id="part_1"></a><a id="part_1"></a></div></body></html>',
            "exactly once",
        ),
    ],
)
def test_html_challenges_unbounded_ranges_and_duplicate_anchors_are_rejected(html, error):
    with pytest.raises(PublicationEditionValidationError, match=error):
        extract_article_sections(html, _tree(["1"]))


@pytest.mark.parametrize(
    "raw",
    [b'{"contract":"x","contract":"y"}', b'{"x":NaN}', b"[]", b"broken", b"\xff"],
)
def test_manifest_json_is_strict(tmp_path, raw):
    path = tmp_path / "manifest.json"
    path.write_bytes(raw)
    with pytest.raises(PublicationEditionValidationError):
        read_manifest(path)


def test_proposal_report_tampering_and_wrong_pin_are_rejected(evidence, tmp_path):
    bundle, _, manifest_sha = evidence
    output = tmp_path / "proposals.json"
    report = build_bundle_proposals(
        bundle, output, expected_manifest_sha256=manifest_sha
    )
    with pytest.raises(PublicationEditionValidationError, match="pin mismatch"):
        read_proposals(output, expected_proposal_sha256="0" * 64)
    altered = deepcopy(report)
    altered["database_writes_allowed"] = True
    output.unlink()
    output.write_text(json.dumps(altered, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(PublicationEditionValidationError, match="content hash"):
        read_proposals(output)
    altered["proposal_sha256"] = sha256_json(
        {key: value for key, value in altered.items() if key != "proposal_sha256"}
    )
    output.write_text(json.dumps(altered, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(PublicationEditionValidationError, match="safety boundary"):
        read_proposals(output)

    altered = deepcopy(report)
    altered["article_timelines"][0]["versions"][0]["authoritative_text_ka"] += " შეცვლილი"
    altered["proposal_sha256"] = sha256_json(
        {key: value for key, value in altered.items() if key != "proposal_sha256"}
    )
    output.write_text(json.dumps(altered, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(PublicationEditionValidationError, match="text hash mismatch"):
        read_proposals(output)


def test_offline_tools_do_not_import_database_or_network_runtime(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    code = (
        "import sys; import legal_temporal.publication_editions as p; "
        "assert 'sqlalchemy' not in sys.modules; "
        "assert 'requests' not in sys.modules; "
        "assert p.BUNDLE_CONTRACT == 'matsne-publication-editions-v1'"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(backend)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(os.name == "nt", reason="Windows symlinks require OS privileges")
def test_symlink_source_is_rejected(tmp_path):
    bundle, manifest, _ = _write_bundle(
        tmp_path, [(0, "2020-01-01", {"1": "ტექსტი"})]
    )
    source = bundle / manifest["editions"][0]["page_file"]
    original = source.with_suffix(".original")
    source.rename(original)
    source.symlink_to(original)
    path = bundle / "manifest.json"
    pin = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(PublicationEditionValidationError, match="regular file"):
        validate_and_extract_bundle(bundle, expected_manifest_sha256=pin)
