#!/usr/bin/env python3
"""Build a verified article-anchor registry from a Matsne document tree.

The input must be the JSON returned by Matsne's public
``/ka/document/tree/<document>/<publication>`` endpoint.  The builder keeps
only concrete, currently displayed article nodes.  Future provisions rendered
in square brackets are intentionally excluded, and duplicate article refs or
anchors fail closed.
"""

from __future__ import annotations

import argparse
import html
import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


_ARTICLE_START = re.compile(
    r"^მუხლი\s*(\d+)\s*(?:-(\d+)|([¹²³⁴⁵⁶⁷⁸⁹⁰]+))?",
    re.IGNORECASE,
)
_SUP_TAG = re.compile(r"<sup\b[^>]*>(.*?)</sup>", re.IGNORECASE | re.DOTALL)
_TAG = re.compile(r"<[^>]+>")
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_ANCHOR = re.compile(
    r"(?:part_\d+|DOCUMENT:\d+;PART:\d+;CHAPTER:\d+;ARTICLE:\d+(?:_\d+)?;)"
)
_ZERO_WIDTH = str.maketrans("", "", "\u200b\u200c\u200d\ufeff")
_SUPERSCRIPT_TRANSLATION = str.maketrans("¹²³⁴⁵⁶⁷⁸⁹⁰", "1234567890")


def _walk(node: Any) -> Iterator[dict[str, Any]]:
    if not isinstance(node, dict):
        return
    yield node
    for child in node.get("DocumentPart") or []:
        yield from _walk(child)


def canonical_article_ref(title: str) -> str | None:
    """Return ``base`` or ``base-suffix`` for one Matsne article heading."""
    markup = _COMMENT.sub("", str(title or ""))

    def replace_sup(match: re.Match[str]) -> str:
        inner = html.unescape(_TAG.sub("", match.group(1))).translate(_ZERO_WIDTH)
        digits = re.search(r"\d+", inner)
        if not digits:
            return ""
        return f"-{digits.group(0)}"

    markup = _SUP_TAG.sub(replace_sup, markup)
    plain = html.unescape(_TAG.sub("", markup)).translate(_ZERO_WIDTH)
    plain = re.sub(r"\s+", " ", plain).strip()
    if plain.startswith("["):
        return None

    match = _ARTICLE_START.match(plain)
    if not match:
        return None

    base = match.group(1)
    suffix = match.group(2)
    if not suffix and match.group(3):
        suffix = match.group(3).translate(_SUPERSCRIPT_TRANSLATION)

    return f"{base}-{suffix}" if suffix else base


def extract_article_anchors(
    tree: dict[str, Any],
) -> tuple[dict[str, str], int, int]:
    candidates: dict[str, str] = {}
    anchor_refs: dict[str, set[str]] = {}
    excluded_future = 0

    for node in _walk(tree):
        title = str(node.get("Title") or "")
        decoded = html.unescape(title).translate(_ZERO_WIDTH).lstrip()
        if node.get("Future") is True or (
            decoded.startswith("[") and "მუხლი" in decoded
        ):
            excluded_future += 1
            continue

        article_ref = canonical_article_ref(title)
        if not article_ref:
            continue

        anchor = str(node.get("Anchor") or "")
        if not _ANCHOR.fullmatch(anchor):
            raise ValueError(f"invalid anchor for article {article_ref}: {anchor!r}")
        if article_ref in candidates and candidates[article_ref] != anchor:
            raise ValueError(
                f"duplicate article {article_ref}: {candidates[article_ref]} and {anchor}"
            )
        candidates[article_ref] = anchor
        anchor_refs.setdefault(anchor, set()).add(article_ref)

    # Matsne sometimes assigns one fragment to a consecutive block of removed
    # articles.  Such a fragment opens the block, not the requested article,
    # so it is not an exact-provision link.  Exclude every ref in the ambiguous
    # block instead of silently pointing several articles at the first one.
    ambiguous_refs = {
        article_ref
        for refs in anchor_refs.values()
        if len(refs) > 1
        for article_ref in refs
    }
    anchors = {
        article_ref: anchor
        for article_ref, anchor in candidates.items()
        if article_ref not in ambiguous_refs
    }

    def sort_key(item: tuple[str, str]) -> tuple[int, int]:
        base, separator, suffix = item[0].partition("-")
        return int(base), int(suffix) if separator else -1

    return (
        dict(sorted(anchors.items(), key=sort_key)),
        excluded_future,
        len(ambiguous_refs),
    )


def _official_https_url(value: str, expected_host: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != expected_host
        or parsed.username
        or parsed.password
        or parsed.port is not None
    ):
        raise ValueError(f"invalid official URL: {value}")
    return value


def build_registry(args: argparse.Namespace) -> dict[str, Any]:
    tree = json.loads(args.tree.read_text(encoding="utf-8"))
    if not isinstance(tree, dict):
        raise ValueError("Matsne tree root must be a JSON object")
    anchors, excluded_future, excluded_ambiguous = extract_article_anchors(tree)
    if len(anchors) != args.expected_count:
        raise ValueError(
            f"article count mismatch: expected {args.expected_count}, got {len(anchors)}"
        )

    registry = {
        "schema_version": 1,
        "registry_id": args.registry_id,
        "registry_version": args.registry_version,
        "minimum_article_anchor_count": args.minimum_count,
        "act_title": args.act_title,
        "infohub_source_url": _official_https_url(args.infohub_source_url, "infohub.rs.ge"),
        "matsne_document_url": _official_https_url(args.matsne_document_url, "matsne.gov.ge"),
        "verified_publication_url": _official_https_url(
            args.verified_publication_url, "matsne.gov.ge"
        ),
        "verified_at_utc": args.verified_at_utc,
        "article_anchors": anchors,
    }
    args.output.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "OFFICIAL_PROVISION_REGISTRY_BUILD="
        + json.dumps(
            {
                "registry_id": args.registry_id,
                "article_anchor_count": len(anchors),
                "excluded_future_article_nodes": excluded_future,
                "excluded_ambiguous_article_nodes": excluded_ambiguous,
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )
    return registry


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tree", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--registry-id", required=True)
    parser.add_argument("--registry-version", required=True)
    parser.add_argument("--minimum-count", type=int, required=True)
    parser.add_argument("--expected-count", type=int, required=True)
    parser.add_argument("--act-title", required=True)
    parser.add_argument("--infohub-source-url", required=True)
    parser.add_argument("--matsne-document-url", required=True)
    parser.add_argument("--verified-publication-url", required=True)
    parser.add_argument("--verified-at-utc", required=True)
    return parser.parse_args()


def main() -> int:
    build_registry(parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
