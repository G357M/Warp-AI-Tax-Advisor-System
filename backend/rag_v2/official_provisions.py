"""Verified official deep links for concrete legal provisions.

The public source URL stored in the corpus remains the Revenue Service
InfoHub document.  For the Georgian Tax Code, Matsne additionally exposes
stable named anchors for individual articles.  This module enriches source
objects with those links without making a network request at answer time.

The registry is evidence, not a legal conclusion.  If an article is absent
from the verified registry, the source remains document-level and the public
evidence contract must not claim that an exact provision link exists.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit


REGISTRY_PATH = Path(__file__).with_name("official_tax_code_provisions.json")
_ARTICLE_TOKEN = re.compile(r"\d+(?:[¹²³⁴⁵⁶⁷⁸⁹⁰]+)?")
_SUPERSCRIPT_TRANSLATION = str.maketrans("¹²³⁴⁵⁶⁷⁸⁹⁰", "1234567890")
_OFFICIAL_HOSTS = {"matsne.gov.ge", "www.matsne.gov.ge"}


@lru_cache(maxsize=1)
def load_tax_code_registry() -> dict[str, Any]:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    if registry.get("schema_version") != 1:
        raise ValueError("unsupported official-provision registry schema")
    if not registry.get("registry_version"):
        raise ValueError("official-provision registry version is required")
    source = urlsplit(str(registry.get("infohub_source_url") or ""))
    matsne = urlsplit(str(registry.get("matsne_document_url") or ""))
    if source.scheme != "https" or source.hostname != "infohub.rs.ge":
        raise ValueError("official-provision InfoHub source is invalid")
    if matsne.scheme != "https" or matsne.hostname not in _OFFICIAL_HOSTS:
        raise ValueError("official-provision Matsne source is invalid")
    anchors = registry.get("article_anchors")
    if not isinstance(anchors, dict) or len(anchors) < 300:
        raise ValueError("official-provision article registry is incomplete")
    for article, anchor in anchors.items():
        if not re.fullmatch(r"\d+", str(article)):
            raise ValueError(f"invalid provision article key: {article}")
        if not re.fullmatch(r"part_\d+", str(anchor)):
            raise ValueError(f"invalid provision anchor: {anchor}")
    return registry


def _is_tax_code_source(source_url: str, registry: dict[str, Any]) -> bool:
    try:
        actual = urlsplit(source_url)
        expected = urlsplit(registry["infohub_source_url"])
    except ValueError:
        return False
    return (
        actual.scheme == "https"
        and actual.hostname == expected.hostname
        and actual.path.rstrip("/").endswith(expected.path.rstrip("/").split("/")[-1])
    )


def _article_key(value: str) -> str:
    return value.translate(_SUPERSCRIPT_TRANSLATION)


def _article_refs(source: dict[str, Any]) -> list[tuple[str, str, str | None]]:
    point_ref = str(source.get("point_ref") or "").strip()
    if point_ref:
        article_part = point_ref.split(".", 1)[0]
        token = _ARTICLE_TOKEN.search(article_part)
        if token:
            display_ref = token.group(0)
            return [(_article_key(display_ref), display_ref, point_ref)]

    article_ref = str(source.get("article_ref") or "").strip()
    refs: list[tuple[str, str, str | None]] = []
    for token in _ARTICLE_TOKEN.findall(article_ref):
        key = _article_key(token)
        if not any(existing[0] == key for existing in refs):
            refs.append((key, token, None))
    return refs


def enrich_source(source: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with verified Matsne provision links when available."""
    enriched = dict(source)
    existing_links = source.get("provision_links") or []
    valid_existing_links = [
        dict(link)
        for link in existing_links
        if isinstance(link, dict) and is_official_provision_link(link)
    ] if isinstance(existing_links, list) else []
    if valid_existing_links:
        enriched["provision_links"] = valid_existing_links
    else:
        enriched.pop("provision_links", None)

    official_act_url = str(source.get("official_act_url") or "").strip()
    try:
        official_act = urlsplit(official_act_url)
        official_act_valid = (
            official_act.scheme == "https"
            and official_act.hostname in _OFFICIAL_HOSTS
            and official_act.path.startswith("/ka/document/view/")
            and not official_act.username
            and not official_act.password
            and official_act.port is None
        )
    except ValueError:
        official_act_valid = False
    if not official_act_valid:
        enriched.pop("official_act_url", None)

    source_url = str(source.get("url") or source.get("source_url") or "").strip()
    registry = load_tax_code_registry()
    if not _is_tax_code_source(source_url, registry):
        return enriched

    links = []
    for article_key, article_ref, point_ref in _article_refs(source):
        anchor = registry["article_anchors"].get(article_key)
        if not anchor:
            continue
        links.append(
            {
                "article_ref": article_ref,
                "point_ref": point_ref,
                "url": f"{registry['matsne_document_url']}#{anchor}",
            }
        )
    if not links:
        return enriched

    enriched.update(
        {
            "official_act_url": registry["matsne_document_url"],
            "provision_links": links,
            "provision_registry_version": registry["registry_version"],
            "provision_registry_verified_at": registry["verified_at_utc"],
            "provision_publication_url": registry["verified_publication_url"],
        }
    )
    return enriched


def enrich_sources(sources: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [enrich_source(source) for source in sources]


def is_official_provision_link(link: dict[str, Any]) -> bool:
    try:
        parsed = urlsplit(str(link.get("url") or ""))
        return (
            parsed.scheme == "https"
            and parsed.hostname in _OFFICIAL_HOSTS
            and not parsed.username
            and not parsed.password
            and parsed.port is None
            and parsed.path.startswith("/ka/document/view/")
            and bool(re.fullmatch(r"part_\d+", parsed.fragment))
            and bool(str(link.get("article_ref") or "").strip())
        )
    except ValueError:
        return False


def has_official_provision_link(source: dict[str, Any]) -> bool:
    links = source.get("provision_links") or []
    return isinstance(links, list) and any(
        isinstance(link, dict) and is_official_provision_link(link) for link in links
    )
