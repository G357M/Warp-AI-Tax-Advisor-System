"""Offline, evidence-pinned Matsne publication-edition reconstruction.

The module deliberately performs no network or database work.  It accepts exact
browser-captured Matsne HTML and document-tree JSON files, verifies their hashes
and official identities, and emits non-executable provision-version proposals.
An amendment summary or the current consolidated text is never used to invent a
historical edition.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, Iterable
from urllib.parse import parse_qs, urlsplit, urlunsplit

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from scripts.build_official_provision_registry import (
    _ANCHOR,
    _walk,
    canonical_article_ref,
    extract_article_anchors,
)


BUNDLE_CONTRACT = "matsne-publication-editions-v1"
PROPOSAL_CONTRACT = "matsne-provision-version-proposals-v1"
MAX_MANIFEST_BYTES = 8 * 1024 * 1024
MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_PROPOSAL_BYTES = 256 * 1024 * 1024
MAX_EDITIONS = 2000
MAX_ARTICLES_PER_EDITION = 5000
MAX_ARTICLE_TEXT_CHARS = 2_000_000
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DOCUMENT_ID_RE = re.compile(r"^[1-9]\d*$")
ARTICLE_REF_RE = re.compile(r"^[1-9]\d*(?:-[1-9]\d*)?$")
SAFE_FILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,511}$")
_BLOCKED_PAGE_MARKERS = (
    "access denied",
    "human verification",
    "captcha",
    "just a moment",
    "cf-chl-",
)
_IGNORED_PARENTS = frozenset({"script", "style", "noscript", "template"})
_MANIFEST_FIELDS = frozenset({"contract", "act", "editions"})
_ACT_FIELDS = frozenset(
    {"act_key", "document_id", "title_ka", "language", "official_document_url"}
)
_EDITION_FIELDS = frozenset(
    {
        "publication",
        "valid_from",
        "page_url",
        "page_file",
        "page_sha256",
        "tree_url",
        "tree_file",
        "tree_sha256",
        "expected_article_count",
        "effective_date_evidence",
    }
)
_DATE_EVIDENCE_FIELDS = frozenset({"official_url", "file", "sha256", "quote"})
_OUTPUT_DATE_EVIDENCE_FIELDS = frozenset(
    {"official_url", "file", "sha256", "quote", "quote_sha256"}
)
_PROPOSAL_FIELDS = frozenset(
    {
        "contract",
        "kind",
        "source_contract",
        "source_manifest_sha256",
        "act",
        "edition_evidence",
        "same_day_editions_not_materialized",
        "article_timelines",
        "summary",
        "database_writes_allowed",
        "public_answer_routing_changed",
        "authoritative_versions_created",
        "requires_independent_expert_review",
        "current_consolidated_text_used_as_historical_baseline",
        "proposal_sha256",
    }
)
_VERSION_FIELDS = frozenset(
    {
        "version_proposal_id",
        "article_ref",
        "authoritative_text_ka",
        "text_sha256",
        "valid_from",
        "valid_to",
        "publication",
        "observed_through_publication",
        "official_locator",
        "source_page_sha256",
        "source_tree_sha256",
        "observed_through_page_sha256",
        "effective_date_evidence",
        "extraction_contract",
        "review_state",
    }
)
_EDITION_EVIDENCE_OUTPUT_FIELDS = frozenset(
    {
        "publication",
        "valid_from",
        "page_url",
        "page_file",
        "page_sha256",
        "tree_url",
        "tree_file",
        "tree_sha256",
        "effective_date_evidence",
        "excluded_future_article_nodes",
        "excluded_ambiguous_article_nodes",
        "article_count",
    }
)


class PublicationEditionValidationError(ValueError):
    """An edition bundle cannot support trustworthy proposals."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _strict_object(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PublicationEditionValidationError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise PublicationEditionValidationError("non-finite JSON value")


def _read_bounded(path: Path, limit: int, *, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise PublicationEditionValidationError(f"{label} must be a regular file")
    with path.open("rb") as handle:
        raw = handle.read(limit + 1)
    if not raw or len(raw) > limit:
        raise PublicationEditionValidationError(
            f"{label} must contain 1..{limit} bytes"
        )
    return raw


def _load_json_bytes(raw: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8-sig"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except PublicationEditionValidationError:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise PublicationEditionValidationError(
            f"{label} is not strict UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise PublicationEditionValidationError(f"{label} root must be an object")
    return value


def read_manifest(path: Path) -> tuple[dict[str, Any], str]:
    raw = _read_bounded(path, MAX_MANIFEST_BYTES, label="manifest")
    return _load_json_bytes(raw, label="manifest"), hashlib.sha256(raw).hexdigest()


def _text(value: Any, field: str, minimum: int, maximum: int) -> str:
    if not isinstance(value, str):
        raise PublicationEditionValidationError(f"{field} must be text")
    cleaned = value.strip()
    if not minimum <= len(cleaned) <= maximum:
        raise PublicationEditionValidationError(
            f"{field} must contain {minimum}..{maximum} characters"
        )
    return cleaned


def _integer(value: Any, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PublicationEditionValidationError(f"{field} must be an integer")
    if not minimum <= value <= maximum:
        raise PublicationEditionValidationError(
            f"{field} must be between {minimum} and {maximum}"
        )
    return value


def _iso_date(value: Any, field: str) -> date:
    raw = _text(value, field, 10, 10)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        raise PublicationEditionValidationError(f"{field} must use YYYY-MM-DD")
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise PublicationEditionValidationError(f"{field} is not a valid date") from exc


def _sha256(value: Any, field: str) -> str:
    raw = _text(value, field, 64, 64)
    if not SHA256_RE.fullmatch(raw):
        raise PublicationEditionValidationError(f"{field} must be lowercase SHA-256")
    return raw


def _official_matsne_url(value: Any, *, field: str) -> str:
    raw = _text(value, field, 1, 4096)
    parsed = urlsplit(raw)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in {"matsne.gov.ge", "new.matsne.gov.ge"}
        or parsed.username
        or parsed.password
        or parsed.port is not None
        or parsed.fragment
        or not parsed.path.startswith("/")
    ):
        raise PublicationEditionValidationError(
            f"{field} must be an official Matsne HTTPS URL without credentials or fragment"
        )
    return urlunsplit(("https", parsed.hostname, parsed.path, parsed.query, ""))


def _edition_page_url(value: Any, document_id: str, publication: int) -> str:
    raw = _official_matsne_url(value, field="page_url")
    parsed = urlsplit(raw)
    if parsed.hostname != "matsne.gov.ge":
        raise PublicationEditionValidationError("page_url must use matsne.gov.ge")
    if parsed.path.rstrip("/") != f"/ka/document/view/{document_id}":
        raise PublicationEditionValidationError("page_url document identity mismatch")
    query = parse_qs(parsed.query, keep_blank_values=True)
    if query != {"publication": [str(publication)]}:
        raise PublicationEditionValidationError("page_url publication identity mismatch")
    return raw


def _tree_url(value: Any, document_id: str, publication: int) -> str:
    raw = _official_matsne_url(value, field="tree_url")
    parsed = urlsplit(raw)
    if parsed.hostname != "matsne.gov.ge" or parsed.query:
        raise PublicationEditionValidationError("tree_url must use matsne.gov.ge without query")
    if parsed.path.rstrip("/") != f"/ka/document/tree/{document_id}/{publication}":
        raise PublicationEditionValidationError("tree_url publication identity mismatch")
    return raw


def _bundle_file(bundle: Path, value: Any, *, field: str) -> Path:
    raw = _text(value, field, 1, 512).replace("\\", "/")
    if not SAFE_FILE_RE.fullmatch(raw):
        raise PublicationEditionValidationError(f"{field} is not a safe relative path")
    pure = PurePosixPath(raw)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise PublicationEditionValidationError(f"{field} must stay inside the bundle")
    candidate = bundle.joinpath(*pure.parts)
    try:
        candidate.resolve(strict=False).relative_to(bundle.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise PublicationEditionValidationError(f"{field} escapes the bundle") from exc
    return candidate


def _verified_source(
    bundle: Path,
    *,
    file_value: Any,
    sha_value: Any,
    file_field: str,
    sha_field: str,
    label: str,
) -> tuple[Path, bytes, str]:
    path = _bundle_file(bundle, file_value, field=file_field)
    expected = _sha256(sha_value, sha_field)
    raw = _read_bounded(path, MAX_SOURCE_BYTES, label=label)
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected:
        raise PublicationEditionValidationError(f"{label} SHA-256 mismatch")
    return path, raw, actual


def _tree_anchors_in_order(tree: dict[str, Any]) -> tuple[list[tuple[str, str]], int, int]:
    accepted, excluded_future, excluded_ambiguous = extract_article_anchors(tree)
    ordered: list[tuple[str, str]] = []
    seen: set[str] = set()
    for node in _walk(tree):
        ref = canonical_article_ref(str(node.get("Title") or ""))
        anchor = str(node.get("Anchor") or "")
        if ref in accepted and accepted[ref] == anchor and ref not in seen:
            ordered.append((ref, anchor))
            seen.add(ref)
    if len(ordered) != len(accepted):
        raise PublicationEditionValidationError("tree article order is incomplete")
    return ordered, excluded_future, excluded_ambiguous


def _contains_block_page(html_text: str) -> bool:
    prefix = html_text[:200_000].casefold()
    return any(marker in prefix for marker in _BLOCKED_PAGE_MARKERS)


def _matching_anchor_tags(soup: BeautifulSoup, anchor: str) -> list[Tag]:
    return [
        tag
        for tag in soup.find_all(True)
        if tag.get("id") == anchor or tag.get("name") == anchor
    ]


def _article_anchor_marker(soup: BeautifulSoup, article_ref: str, anchor: str) -> Tag:
    """Choose the one Matsne anchor that carries this article heading.

    Old-style Matsne editions may repeat a ``name=part_N`` marker: first as an
    empty range boundary and then as the linked article heading.  The heading
    proves the pair when exactly one duplicate decodes to the tree's
    article reference.  Extraction starts at the preceding empty boundary so
    the heading and body remain inside the article range.  A genuinely unique
    marker remains supported for newer and synthetic editions.
    """
    matches = _matching_anchor_tags(soup, anchor)
    semantic = [
        tag
        for tag in matches
        if canonical_article_ref(tag.get_text(" ", strip=True)) == article_ref
    ]
    if len(matches) == 1:
        return matches[0]
    if len(semantic) == 1:
        heading = semantic[0]
        boundaries = [
            tag
            for tag in matches
            if tag is not heading and not tag.get_text(" ", strip=True)
        ]
        if (
            len(boundaries) == 1
            and matches.index(boundaries[0]) < matches.index(heading)
        ):
            return boundaries[0]
    raise PublicationEditionValidationError(
        f"article {article_ref} anchor must occur exactly once or as one "
        "verified old-style boundary/heading pair in page HTML"
    )


def _common_ancestor(tags: list[Tag]) -> Tag:
    if not tags:
        raise PublicationEditionValidationError("edition has no article anchors")
    first_chain = [first for first in tags[0].parents if isinstance(first, Tag)]
    other_sets = [set(tag.parents) for tag in tags[1:]]
    for candidate in first_chain:
        if all(candidate in parents for parents in other_sets):
            if candidate.name in {"html", "body"}:
                raise PublicationEditionValidationError(
                    "article anchors do not share a bounded document-content container"
                )
            return candidate
    raise PublicationEditionValidationError(
        "article anchors do not share a document-content container"
    )


def _is_within(element: Any, container: Tag) -> bool:
    return element is container or container in getattr(element, "parents", [])


def _normalized_article_text(parts: list[str]) -> str:
    text = " ".join(parts)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"(?<=\d)\s+([¹²³⁴⁵⁶⁷⁸⁹⁰]+)", r"\1", text)
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)
    return text


def extract_article_sections(
    page_bytes: bytes,
    tree: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    """Extract every unambiguous article between exact Matsne DOM anchors.

    The nearest common non-body ancestor is a hard boundary, so navigation and
    footer text cannot silently become part of the last article.  Text is a
    deterministic semantic normalization; exact page bytes remain the primary
    evidence and are separately hashed.
    """
    try:
        html_text = page_bytes.decode("utf-8-sig")
    except UnicodeError as exc:
        raise PublicationEditionValidationError("page is not UTF-8 HTML") from exc
    if _contains_block_page(html_text):
        raise PublicationEditionValidationError(
            "page is an access/challenge response, not an official legal edition"
        )
    ordered, excluded_future, excluded_ambiguous = _tree_anchors_in_order(tree)
    if not ordered:
        raise PublicationEditionValidationError("tree contains no extractable articles")
    soup = BeautifulSoup(html_text, "html.parser")
    superscript = str.maketrans("1234567890", "¹²³⁴⁵⁶⁷⁸⁹⁰")
    for node in soup.find_all("sup"):
        value = re.sub(r"\s+", "", node.get_text()).strip()
        if value.isdigit():
            node.string = value.translate(superscript)
    markers: list[tuple[str, str, Tag]] = []
    for ref, anchor in ordered:
        markers.append((ref, anchor, _article_anchor_marker(soup, ref, anchor)))
    container = _common_ancestor([marker for _, _, marker in markers])
    marker_identity = {id(marker): ref for ref, _, marker in markers}
    extracted: dict[str, dict[str, Any]] = {}
    for ref, anchor, marker in markers:
        parts: list[str] = []
        started = False
        for element in marker.next_elements:
            if element is marker:
                started = True
                continue
            if not _is_within(element, container):
                break
            if isinstance(element, Tag) and id(element) in marker_identity:
                break
            if isinstance(element, Comment):
                continue
            if isinstance(element, NavigableString):
                parent = element.parent
                if parent and parent.name not in _IGNORED_PARENTS:
                    cleaned = re.sub(r"\s+", " ", str(element)).strip()
                    if cleaned:
                        parts.append(cleaned)
            started = True
        if not started:
            raise PublicationEditionValidationError(f"article {ref} has no DOM range")
        text = _normalized_article_text(parts)
        if not 5 <= len(text) <= MAX_ARTICLE_TEXT_CHARS:
            raise PublicationEditionValidationError(
                f"article {ref} text is empty or exceeds the article limit"
            )
        extracted[ref] = {
            "article_ref": ref,
            "anchor": anchor,
            "authoritative_text_ka": text,
            "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "extraction_contract": "bounded-dom-anchor-range-v1",
        }
    return extracted, {
        "excluded_future_article_nodes": excluded_future,
        "excluded_ambiguous_article_nodes": excluded_ambiguous,
    }


def _validate_tree(raw: bytes) -> dict[str, Any]:
    tree = _load_json_bytes(raw, label="Matsne tree")
    if not any(True for _ in _walk(tree)):
        raise PublicationEditionValidationError("Matsne tree is empty")
    return tree


def _validate_date_evidence(
    bundle: Path,
    value: Any,
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _DATE_EVIDENCE_FIELDS:
        raise PublicationEditionValidationError(
            "effective_date_evidence has unexpected or missing fields"
        )
    official_url = _official_matsne_url(
        value["official_url"], field="effective_date_evidence.official_url"
    )
    path, raw, actual_sha = _verified_source(
        bundle,
        file_value=value["file"],
        sha_value=value["sha256"],
        file_field="effective_date_evidence.file",
        sha_field="effective_date_evidence.sha256",
        label="effective-date evidence",
    )
    quote = _text(value["quote"], "effective_date_evidence.quote", 8, 4000)
    try:
        decoded = raw.decode("utf-8-sig")
    except UnicodeError as exc:
        raise PublicationEditionValidationError(
            "effective-date evidence is not UTF-8"
        ) from exc
    if quote not in decoded:
        raise PublicationEditionValidationError(
            "effective-date evidence quote is not verbatim in its captured source"
        )
    return {
        "official_url": official_url,
        "file": path.relative_to(bundle).as_posix(),
        "sha256": actual_sha,
        "quote": quote,
        "quote_sha256": hashlib.sha256(quote.encode("utf-8")).hexdigest(),
    }


def _validate_act(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != _ACT_FIELDS:
        raise PublicationEditionValidationError("act has unexpected or missing fields")
    document_id = _text(value["document_id"], "act.document_id", 1, 32)
    if not DOCUMENT_ID_RE.fullmatch(document_id):
        raise PublicationEditionValidationError("act.document_id must contain digits")
    language = _text(value["language"], "act.language", 2, 2)
    if language != "ka":
        raise PublicationEditionValidationError(
            "only authoritative Georgian publication editions are supported"
        )
    official_url = _official_matsne_url(
        value["official_document_url"], field="act.official_document_url"
    )
    parsed = urlsplit(official_url)
    if (
        parsed.hostname != "matsne.gov.ge"
        or parsed.path.rstrip("/") != f"/ka/document/view/{document_id}"
        or parsed.query
    ):
        raise PublicationEditionValidationError(
            "act.official_document_url identity mismatch"
        )
    return {
        "act_key": _text(value["act_key"], "act.act_key", 3, 120),
        "document_id": document_id,
        "title_ka": _text(value["title_ka"], "act.title_ka", 3, 1000),
        "language": language,
        "official_document_url": official_url,
    }


def validate_and_extract_bundle(
    bundle: Path,
    *,
    expected_manifest_sha256: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Verify all evidence before returning any extracted edition."""
    if not SHA256_RE.fullmatch(str(expected_manifest_sha256 or "")):
        raise PublicationEditionValidationError("a lowercase manifest SHA-256 pin is required")
    manifest_path = bundle / "manifest.json"
    manifest, manifest_sha = read_manifest(manifest_path)
    if manifest_sha != expected_manifest_sha256:
        raise PublicationEditionValidationError("manifest SHA-256 pin mismatch")
    if set(manifest) != _MANIFEST_FIELDS or manifest.get("contract") != BUNDLE_CONTRACT:
        raise PublicationEditionValidationError("manifest contract or fields mismatch")
    act = _validate_act(manifest["act"])
    editions = manifest["editions"]
    if not isinstance(editions, list) or not 1 <= len(editions) <= MAX_EDITIONS:
        raise PublicationEditionValidationError("manifest must contain 1..2000 editions")

    seen_publications: set[int] = set()
    seen_files: set[str] = set()
    previous_publication = -1
    previous_date: date | None = None
    extracted_editions: list[dict[str, Any]] = []
    for index, edition in enumerate(editions):
        if not isinstance(edition, dict) or set(edition) != _EDITION_FIELDS:
            raise PublicationEditionValidationError(
                f"edition {index} has unexpected or missing fields"
            )
        publication = _integer(
            edition["publication"], f"editions[{index}].publication", 0, 1_000_000
        )
        valid_from = _iso_date(
            edition["valid_from"], f"editions[{index}].valid_from"
        )
        if publication in seen_publications or publication <= previous_publication:
            raise PublicationEditionValidationError(
                "edition publications must be unique and strictly increasing"
            )
        if previous_date is not None and valid_from < previous_date:
            raise PublicationEditionValidationError(
                "edition valid_from dates must be non-decreasing"
            )
        seen_publications.add(publication)
        previous_publication = publication
        previous_date = valid_from
        page_url = _edition_page_url(edition["page_url"], act["document_id"], publication)
        tree_url = _tree_url(edition["tree_url"], act["document_id"], publication)
        page_path, page_raw, page_sha = _verified_source(
            bundle,
            file_value=edition["page_file"],
            sha_value=edition["page_sha256"],
            file_field=f"editions[{index}].page_file",
            sha_field=f"editions[{index}].page_sha256",
            label=f"edition {publication} page",
        )
        tree_path, tree_raw, tree_sha = _verified_source(
            bundle,
            file_value=edition["tree_file"],
            sha_value=edition["tree_sha256"],
            file_field=f"editions[{index}].tree_file",
            sha_field=f"editions[{index}].tree_sha256",
            label=f"edition {publication} tree",
        )
        for path in (page_path, tree_path):
            relative = path.relative_to(bundle).as_posix()
            if relative in seen_files:
                raise PublicationEditionValidationError(
                    "page and tree evidence files must be unique per edition"
                )
            seen_files.add(relative)
        tree = _validate_tree(tree_raw)
        articles, exclusions = extract_article_sections(page_raw, tree)
        expected_count = _integer(
            edition["expected_article_count"],
            f"editions[{index}].expected_article_count",
            1,
            MAX_ARTICLES_PER_EDITION,
        )
        if len(articles) != expected_count:
            raise PublicationEditionValidationError(
                f"edition {publication} article count mismatch: "
                f"expected {expected_count}, got {len(articles)}"
            )
        date_evidence = _validate_date_evidence(
            bundle, edition["effective_date_evidence"]
        )
        extracted_editions.append(
            {
                "publication": publication,
                "valid_from": valid_from.isoformat(),
                "page_url": page_url,
                "page_file": page_path.relative_to(bundle).as_posix(),
                "page_sha256": page_sha,
                "tree_url": tree_url,
                "tree_file": tree_path.relative_to(bundle).as_posix(),
                "tree_sha256": tree_sha,
                "effective_date_evidence": date_evidence,
                "articles": articles,
                **exclusions,
            }
        )
    return {"contract": BUNDLE_CONTRACT, "act": act, "manifest_sha256": manifest_sha}, extracted_editions


def _effective_editions(editions: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Use the final consolidated publication when several start the same day."""
    selected: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    for edition in editions:
        if selected and selected[-1]["valid_from"] == edition["valid_from"]:
            prior = selected.pop()
            suppressed.append(
                {
                    "publication": prior["publication"],
                    "valid_from": prior["valid_from"],
                    "superseded_by_publication": edition["publication"],
                    "reason": "later_consolidated_publication_on_same_valid_date",
                }
            )
        selected.append(edition)
    return selected, suppressed


def build_proposals(
    manifest_identity: dict[str, Any],
    editions: list[dict[str, Any]],
) -> dict[str, Any]:
    effective, suppressed = _effective_editions(editions)
    all_refs = sorted(
        {ref for edition in effective for ref in edition["articles"]},
        key=lambda ref: tuple(int(part) for part in ref.split("-")),
    )
    timelines: list[dict[str, Any]] = []
    total_versions = 0
    gap_count = 0
    for ref in all_refs:
        versions: list[dict[str, Any]] = []
        gaps: list[dict[str, Any]] = []
        active: dict[str, Any] | None = None
        first_present = next(
            (index for index, edition in enumerate(effective) if ref in edition["articles"]),
            None,
        )
        last_present = max(
            index for index, edition in enumerate(effective) if ref in edition["articles"]
        )
        for index, edition in enumerate(effective):
            article = edition["articles"].get(ref)
            if article is None:
                if active is not None:
                    active["valid_to"] = edition["valid_from"]
                    versions.append(active)
                    active = None
                if first_present is not None and first_present < index <= last_present:
                    next_date = (
                        effective[index + 1]["valid_from"]
                        if index + 1 < len(effective)
                        else None
                    )
                    gaps.append(
                        {
                            "valid_from": edition["valid_from"],
                            "valid_to": next_date,
                            "publication": edition["publication"],
                            "reason": "article_missing_between_observed_editions",
                        }
                    )
                continue
            if active and active["text_sha256"] == article["text_sha256"]:
                active["observed_through_publication"] = edition["publication"]
                active["observed_through_page_sha256"] = edition["page_sha256"]
                continue
            if active is not None:
                active["valid_to"] = edition["valid_from"]
                versions.append(active)
            active = {
                "version_proposal_id": "MPV-" + sha256_json(
                    {
                        "contract": PROPOSAL_CONTRACT,
                        "manifest_sha256": manifest_identity["manifest_sha256"],
                        "article_ref": ref,
                        "valid_from": edition["valid_from"],
                        "text_sha256": article["text_sha256"],
                    }
                ),
                "article_ref": ref,
                "authoritative_text_ka": article["authoritative_text_ka"],
                "text_sha256": article["text_sha256"],
                "valid_from": edition["valid_from"],
                "valid_to": None,
                "publication": edition["publication"],
                "observed_through_publication": edition["publication"],
                "official_locator": edition["page_url"] + "#" + article["anchor"],
                "source_page_sha256": edition["page_sha256"],
                "source_tree_sha256": edition["tree_sha256"],
                "observed_through_page_sha256": edition["page_sha256"],
                "effective_date_evidence": edition["effective_date_evidence"],
                "extraction_contract": article["extraction_contract"],
                "review_state": "needs_independent_expert_review",
            }
        if active is not None:
            versions.append(active)
        timeline = {
            "article_ref": ref,
            "versions": versions,
            "coverage_gaps": gaps,
            "coverage_complete_between_first_and_last_observation": not gaps,
        }
        total_versions += len(versions)
        gap_count += len(gaps)
        timelines.append(timeline)

    edition_evidence = [
        {
            key: edition[key]
            for key in (
                "publication",
                "valid_from",
                "page_url",
                "page_file",
                "page_sha256",
                "tree_url",
                "tree_file",
                "tree_sha256",
                "effective_date_evidence",
                "excluded_future_article_nodes",
                "excluded_ambiguous_article_nodes",
            )
        }
        | {"article_count": len(edition["articles"])}
        for edition in editions
    ]
    result = {
        "contract": PROPOSAL_CONTRACT,
        "kind": "non_executable_official_publication_version_proposals",
        "source_contract": BUNDLE_CONTRACT,
        "source_manifest_sha256": manifest_identity["manifest_sha256"],
        "act": manifest_identity["act"],
        "edition_evidence": edition_evidence,
        "same_day_editions_not_materialized": suppressed,
        "article_timelines": timelines,
        "summary": {
            "captured_editions": len(editions),
            "effective_dates": len(effective),
            "same_day_editions_not_materialized": len(suppressed),
            "distinct_articles": len(all_refs),
            "version_proposals": total_versions,
            "coverage_gaps": gap_count,
            "future_article_nodes_excluded": sum(
                edition["excluded_future_article_nodes"] for edition in editions
            ),
            "ambiguous_article_nodes_excluded": sum(
                edition["excluded_ambiguous_article_nodes"] for edition in editions
            ),
        },
        "database_writes_allowed": False,
        "public_answer_routing_changed": False,
        "authoritative_versions_created": 0,
        "requires_independent_expert_review": True,
        "current_consolidated_text_used_as_historical_baseline": False,
    }
    result["proposal_sha256"] = sha256_json(result)
    return result


def _write_new(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        raise PublicationEditionValidationError("output already exists")
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    try:
        path.chmod(0o600)
    except OSError:
        pass


def build_bundle_proposals(
    bundle: Path,
    output: Path,
    *,
    expected_manifest_sha256: str,
) -> dict[str, Any]:
    if bundle.is_symlink() or not bundle.is_dir():
        raise PublicationEditionValidationError("bundle must be a regular directory")
    try:
        output.resolve(strict=False).relative_to(bundle.resolve(strict=True))
    except ValueError:
        pass
    else:
        raise PublicationEditionValidationError("output must be outside the evidence bundle")
    manifest, editions = validate_and_extract_bundle(
        bundle, expected_manifest_sha256=expected_manifest_sha256
    )
    result = build_proposals(manifest, editions)
    _write_new(output, result)
    return result


def read_proposals(
    path: Path,
    *,
    expected_proposal_sha256: str | None = None,
) -> dict[str, Any]:
    raw = _read_bounded(path, MAX_PROPOSAL_BYTES, label="proposal report")
    report = _load_json_bytes(raw, label="proposal report")
    if report.get("contract") != PROPOSAL_CONTRACT:
        raise PublicationEditionValidationError("proposal contract mismatch")
    embedded = report.get("proposal_sha256")
    if not isinstance(embedded, str) or not SHA256_RE.fullmatch(embedded):
        raise PublicationEditionValidationError("proposal report has no valid identity")
    unsigned = dict(report)
    unsigned.pop("proposal_sha256")
    actual = sha256_json(unsigned)
    if actual != embedded:
        raise PublicationEditionValidationError("proposal report content hash mismatch")
    if expected_proposal_sha256 is not None and embedded != expected_proposal_sha256:
        raise PublicationEditionValidationError("proposal report pin mismatch")
    if (
        report.get("database_writes_allowed") is not False
        or report.get("public_answer_routing_changed") is not False
        or report.get("authoritative_versions_created") != 0
    ):
        raise PublicationEditionValidationError("proposal safety boundary was changed")
    _validate_proposal_report(report)
    return report


def _validate_output_date_evidence(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != _OUTPUT_DATE_EVIDENCE_FIELDS:
        raise PublicationEditionValidationError("proposal date evidence is malformed")
    _official_matsne_url(value["official_url"], field="proposal date evidence URL")
    _text(value["file"], "proposal date evidence file", 1, 512)
    _sha256(value["sha256"], "proposal date evidence SHA-256")
    quote = _text(value["quote"], "proposal date evidence quote", 8, 4000)
    if hashlib.sha256(quote.encode("utf-8")).hexdigest() != value["quote_sha256"]:
        raise PublicationEditionValidationError("proposal date evidence quote hash mismatch")


def _validate_proposal_report(report: dict[str, Any]) -> None:
    if set(report) != _PROPOSAL_FIELDS:
        raise PublicationEditionValidationError("proposal report fields mismatch")
    if (
        report["kind"] != "non_executable_official_publication_version_proposals"
        or report["source_contract"] != BUNDLE_CONTRACT
        or report["requires_independent_expert_review"] is not True
        or report["current_consolidated_text_used_as_historical_baseline"] is not False
    ):
        raise PublicationEditionValidationError("proposal report semantics mismatch")
    _sha256(report["source_manifest_sha256"], "source manifest SHA-256")
    _validate_act(report["act"])
    evidence = report["edition_evidence"]
    timelines = report["article_timelines"]
    suppressed = report["same_day_editions_not_materialized"]
    summary = report["summary"]
    if not isinstance(evidence, list) or not 1 <= len(evidence) <= MAX_EDITIONS:
        raise PublicationEditionValidationError("proposal edition evidence is malformed")
    if not isinstance(timelines, list) or len(timelines) > MAX_ARTICLES_PER_EDITION:
        raise PublicationEditionValidationError("proposal timelines are malformed")
    if not isinstance(suppressed, list) or len(suppressed) > len(evidence):
        raise PublicationEditionValidationError("same-day edition evidence is malformed")
    if not isinstance(summary, dict):
        raise PublicationEditionValidationError("proposal summary is malformed")

    publication_evidence: dict[int, dict[str, Any]] = {}
    prior_publication = -1
    prior_date: date | None = None
    counted_future = 0
    counted_ambiguous = 0
    for item in evidence:
        if not isinstance(item, dict) or set(item) != _EDITION_EVIDENCE_OUTPUT_FIELDS:
            raise PublicationEditionValidationError("edition evidence fields mismatch")
        publication = _integer(
            item["publication"], "edition evidence publication", 0, 1_000_000
        )
        valid_from = _iso_date(item["valid_from"], "edition evidence valid_from")
        if publication <= prior_publication or (
            prior_date is not None and valid_from < prior_date
        ):
            raise PublicationEditionValidationError("edition evidence order is invalid")
        prior_publication = publication
        prior_date = valid_from
        page_url = _edition_page_url(
            item["page_url"], report["act"]["document_id"], publication
        )
        _tree_url(item["tree_url"], report["act"]["document_id"], publication)
        for field in ("page_file", "tree_file"):
            raw_file = _text(item[field], f"edition evidence {field}", 1, 512)
            pure = PurePosixPath(raw_file.replace("\\", "/"))
            if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
                raise PublicationEditionValidationError("edition evidence file is unsafe")
        _sha256(item["page_sha256"], "edition evidence page SHA-256")
        _sha256(item["tree_sha256"], "edition evidence tree SHA-256")
        _integer(item["article_count"], "edition evidence article count", 1, MAX_ARTICLES_PER_EDITION)
        counted_future += _integer(
            item["excluded_future_article_nodes"],
            "excluded future article nodes",
            0,
            MAX_ARTICLES_PER_EDITION,
        )
        counted_ambiguous += _integer(
            item["excluded_ambiguous_article_nodes"],
            "excluded ambiguous article nodes",
            0,
            MAX_ARTICLES_PER_EDITION,
        )
        _validate_output_date_evidence(item["effective_date_evidence"])
        publication_evidence[publication] = item | {"page_url": page_url}

    suppressed_publications: set[int] = set()
    for item in suppressed:
        if not isinstance(item, dict) or set(item) != {
            "publication",
            "valid_from",
            "superseded_by_publication",
            "reason",
        }:
            raise PublicationEditionValidationError("same-day edition fields mismatch")
        publication = _integer(item["publication"], "suppressed publication", 0, 1_000_000)
        successor = _integer(
            item["superseded_by_publication"], "same-day successor", 0, 1_000_000
        )
        if (
            publication in suppressed_publications
            or publication not in publication_evidence
            or successor not in publication_evidence
            or successor <= publication
            or item["valid_from"] != publication_evidence[publication]["valid_from"]
            or item["valid_from"] != publication_evidence[successor]["valid_from"]
            or item["reason"] != "later_consolidated_publication_on_same_valid_date"
        ):
            raise PublicationEditionValidationError("same-day edition evidence mismatch")
        suppressed_publications.add(publication)

    seen_refs: set[str] = set()
    counted_versions = 0
    counted_gaps = 0
    for timeline in timelines:
        if not isinstance(timeline, dict) or set(timeline) != {
            "article_ref",
            "versions",
            "coverage_gaps",
            "coverage_complete_between_first_and_last_observation",
        }:
            raise PublicationEditionValidationError("proposal timeline fields mismatch")
        ref = timeline["article_ref"]
        if not isinstance(ref, str) or not ARTICLE_REF_RE.fullmatch(ref) or ref in seen_refs:
            raise PublicationEditionValidationError("proposal article identity is invalid")
        seen_refs.add(ref)
        versions = timeline["versions"]
        gaps = timeline["coverage_gaps"]
        if not isinstance(versions, list) or not versions:
            raise PublicationEditionValidationError("proposal timeline has no versions")
        if not isinstance(gaps, list):
            raise PublicationEditionValidationError("proposal gaps are malformed")
        if timeline["coverage_complete_between_first_and_last_observation"] is not (not gaps):
            raise PublicationEditionValidationError("proposal coverage flag mismatch")
        prior_end: date | None = None
        for version_index, version in enumerate(versions):
            if not isinstance(version, dict) or set(version) != _VERSION_FIELDS:
                raise PublicationEditionValidationError("proposal version fields mismatch")
            if version["article_ref"] != ref:
                raise PublicationEditionValidationError("proposal version article mismatch")
            text_value = _text(
                version["authoritative_text_ka"], "proposal article text", 5, MAX_ARTICLE_TEXT_CHARS
            )
            if hashlib.sha256(text_value.encode("utf-8")).hexdigest() != version["text_sha256"]:
                raise PublicationEditionValidationError("proposal article text hash mismatch")
            start = _iso_date(version["valid_from"], "proposal valid_from")
            end = (
                _iso_date(version["valid_to"], "proposal valid_to")
                if version["valid_to"] is not None
                else None
            )
            if end is not None and end <= start:
                raise PublicationEditionValidationError("proposal interval is invalid")
            if end is None and version_index != len(versions) - 1:
                raise PublicationEditionValidationError(
                    "only the final proposal interval may be open-ended"
                )
            if prior_end is not None and start < prior_end:
                raise PublicationEditionValidationError("proposal intervals overlap")
            prior_end = end
            _integer(version["publication"], "proposal publication", 0, 1_000_000)
            _integer(
                version["observed_through_publication"],
                "proposal observed publication",
                version["publication"],
                1_000_000,
            )
            _sha256(version["source_page_sha256"], "proposal page SHA-256")
            _sha256(version["source_tree_sha256"], "proposal tree SHA-256")
            _sha256(
                version["observed_through_page_sha256"],
                "proposal observed page SHA-256",
            )
            publication = version["publication"]
            source = publication_evidence.get(publication)
            observed_publication = version["observed_through_publication"]
            observed_source = publication_evidence.get(observed_publication)
            locator_prefix = source["page_url"] + "#" if source else ""
            locator_fragment = (
                version["official_locator"][len(locator_prefix):]
                if isinstance(version["official_locator"], str)
                and locator_prefix
                and version["official_locator"].startswith(locator_prefix)
                else ""
            )
            if (
                source is None
                or publication in suppressed_publications
                or version["source_page_sha256"] != source["page_sha256"]
                or version["source_tree_sha256"] != source["tree_sha256"]
                or version["effective_date_evidence"] != source["effective_date_evidence"]
                or not _ANCHOR.fullmatch(locator_fragment)
                or observed_source is None
                or observed_publication < publication
                or version["observed_through_page_sha256"]
                != observed_source["page_sha256"]
            ):
                raise PublicationEditionValidationError("proposal source binding mismatch")
            expected_id = "MPV-" + sha256_json(
                {
                    "contract": PROPOSAL_CONTRACT,
                    "manifest_sha256": report["source_manifest_sha256"],
                    "article_ref": ref,
                    "valid_from": version["valid_from"],
                    "text_sha256": version["text_sha256"],
                }
            )
            if (
                version["extraction_contract"] != "bounded-dom-anchor-range-v1"
                or version["review_state"] != "needs_independent_expert_review"
                or version["version_proposal_id"] != expected_id
            ):
                raise PublicationEditionValidationError("proposal version semantics mismatch")
            _validate_output_date_evidence(version["effective_date_evidence"])
            counted_versions += 1
        for gap in gaps:
            if not isinstance(gap, dict) or set(gap) != {
                "valid_from",
                "valid_to",
                "publication",
                "reason",
            }:
                raise PublicationEditionValidationError("proposal gap fields mismatch")
            start = _iso_date(gap["valid_from"], "gap valid_from")
            end = _iso_date(gap["valid_to"], "gap valid_to") if gap["valid_to"] else None
            if end is not None and end <= start:
                raise PublicationEditionValidationError("proposal gap interval is invalid")
            if gap["reason"] != "article_missing_between_observed_editions":
                raise PublicationEditionValidationError("proposal gap reason is invalid")
            if gap["publication"] not in publication_evidence:
                raise PublicationEditionValidationError("proposal gap source is unknown")
            counted_gaps += 1
    expected_summary = {
        "captured_editions": len(evidence),
        "effective_dates": len(evidence) - len(suppressed),
        "same_day_editions_not_materialized": len(suppressed),
        "distinct_articles": len(timelines),
        "version_proposals": counted_versions,
        "coverage_gaps": counted_gaps,
    }
    if any(summary.get(key) != value for key, value in expected_summary.items()):
        raise PublicationEditionValidationError("proposal summary counts mismatch")
    if (
        summary.get("future_article_nodes_excluded") != counted_future
        or summary.get("ambiguous_article_nodes_excluded") != counted_ambiguous
        or set(summary) != {
            "captured_editions",
            "effective_dates",
            "same_day_editions_not_materialized",
            "distinct_articles",
            "version_proposals",
            "coverage_gaps",
            "future_article_nodes_excluded",
            "ambiguous_article_nodes_excluded",
        }
    ):
        raise PublicationEditionValidationError("proposal exclusion summary mismatch")


def query_provision(
    report: dict[str, Any],
    *,
    article_ref: str,
    as_of: str,
) -> dict[str, Any]:
    ref = _text(article_ref, "article_ref", 1, 32)
    if not ARTICLE_REF_RE.fullmatch(ref):
        raise PublicationEditionValidationError("article_ref must be canonical")
    query_date = _iso_date(as_of, "as_of")
    timelines = report.get("article_timelines")
    if not isinstance(timelines, list):
        raise PublicationEditionValidationError("proposal timelines are malformed")
    matches = [timeline for timeline in timelines if timeline.get("article_ref") == ref]
    if len(matches) != 1:
        return {
            "status": "unknown_article",
            "article_ref": ref,
            "as_of": query_date.isoformat(),
            "source_manifest_sha256": report.get("source_manifest_sha256"),
        }
    timeline = matches[0]
    for gap in timeline.get("coverage_gaps", []):
        start = date.fromisoformat(gap["valid_from"])
        end = date.fromisoformat(gap["valid_to"]) if gap["valid_to"] else None
        if query_date >= start and (end is None or query_date < end):
            return {
                "status": "coverage_gap",
                "article_ref": ref,
                "as_of": query_date.isoformat(),
                "gap": gap,
                "source_manifest_sha256": report["source_manifest_sha256"],
            }
    for version in timeline.get("versions", []):
        start = date.fromisoformat(version["valid_from"])
        end = date.fromisoformat(version["valid_to"]) if version["valid_to"] else None
        if query_date >= start and (end is None or query_date < end):
            return {
                "status": "exact_version_proposal",
                "article_ref": ref,
                "as_of": query_date.isoformat(),
                "version": version,
                "source_manifest_sha256": report["source_manifest_sha256"],
                "proposal_sha256": report["proposal_sha256"],
                "authoritative_for_public_answers": False,
            }
    return {
        "status": "not_in_observed_force",
        "article_ref": ref,
        "as_of": query_date.isoformat(),
        "source_manifest_sha256": report["source_manifest_sha256"],
    }


def summarize(result: dict[str, Any]) -> dict[str, Any]:
    summary = dict(result["summary"])
    summary.update(
        {
            "contract": result["contract"],
            "source_manifest_sha256": result["source_manifest_sha256"],
            "proposal_sha256": result["proposal_sha256"],
            "database_writes_allowed": result["database_writes_allowed"],
            "public_answer_routing_changed": result["public_answer_routing_changed"],
        }
    )
    return summary
