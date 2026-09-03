"""Deterministic contracts for the controlled temporal legal backfill.

The legacy ``law_amendments`` rows are discovery hints, not authoritative legal
text.  This module accepts only exact official InfoHub API response bytes,
rebuilds the legacy normalized text to detect source drift and promotes an
operation candidate only when an explicit Georgian operative formula is found
next to the referenced article.  Public answer routing is outside this module.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from bs4 import BeautifulSoup


BUNDLE_SCHEMA_VERSION = 1
BACKFILL_CONTRACT = "legal-temporal-backfill-v1"
# Two official acts in the production inventory currently return JSON payloads
# of roughly 23 MiB and 45 MiB.  Keep the fetch bounded, but leave enough room
# for those observed official responses plus modest upstream growth.
MAX_OFFICIAL_RESPONSE_BYTES = 64 * 1024 * 1024
CANONICAL_ARTICLE_RE = re.compile(r"^[1-9]\d*(?:-[1-9]\d*)?$")
WORKSPACE_PATH_RE = re.compile(
    r"^/(ka|ru|en)/workspace/document/([0-9a-fA-F-]{36})/?$"
)
ALLOWED_LEGACY_ACTIONS = frozenset({"added", "amended", "repealed"})
ACTION_OPERATION_TYPES = {
    "added": "add",
    "amended": "replace",
    "repealed": "repeal",
}
_SUPERSCRIPT_TO_ASCII = str.maketrans("¹²³⁴⁵⁶⁷⁸⁹⁰", "1234567890")
_ASCII_TO_SUPERSCRIPT = str.maketrans("1234567890", "¹²³⁴⁵⁶⁷⁸⁹⁰")
_ZERO_WIDTH = str.maketrans("", "", "\u200b\u200c\u200d\ufeff")
_OPERATION_MARKERS = {
    "add": (
        "დაემატოს",
        "დამატებულ იქნეს",
    ),
    "replace": (
        "ჩამოყალიბდეს შემდეგი რედაქციით",
        "შემდეგი რედაქციით ჩამოყალიბდეს",
    ),
    "repeal": (
        "ამოღებულ იქნეს",
        "ძალადაკარგულად გამოცხადდეს",
        "ძალადაკარგულად ჩაითვალოს",
    ),
}
LEGACY_NORMALIZER_PLAIN = "api-plain-text-v1"
LEGACY_NORMALIZER_NATIVE = "native-api-reparse-all-from-raw-v2"
LEGACY_NORMALIZER_SCRAPLING = "native-api-scrapling-repair-v1"
ALLOWED_LEGACY_NORMALIZERS = frozenset(
    {
        LEGACY_NORMALIZER_PLAIN,
        LEGACY_NORMALIZER_NATIVE,
        LEGACY_NORMALIZER_SCRAPLING,
    }
)
SOURCE_VERIFICATION_EXACT = "exact_legacy_md5"
SOURCE_VERIFICATION_WHITESPACE = "whitespace_equivalent_legacy"
SOURCE_VERIFICATION_DRIFT = "source_content_drift"
ALLOWED_SOURCE_VERIFICATION_MODES = frozenset(
    {
        SOURCE_VERIFICATION_EXACT,
        SOURCE_VERIFICATION_WHITESPACE,
        SOURCE_VERIFICATION_DRIFT,
    }
)
_LEGAL_HEADINGS = ("კარი", "თავი", "მუხლი")


class BackfillValidationError(ValueError):
    """Raised when evidence or a bundle violates the reviewed contract."""


@dataclass(frozen=True)
class OfficialSourceIdentity:
    workspace_url: str
    language: str
    unique_key: str
    api_url: str


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def parse_workspace_source_url(value: str) -> OfficialSourceIdentity:
    parsed = urlsplit(str(value or "").strip())
    match = WORKSPACE_PATH_RE.fullmatch(parsed.path)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "infohub.rs.ge"
        or parsed.username
        or parsed.password
        or parsed.port is not None
        or parsed.query
        or parsed.fragment
        or match is None
    ):
        raise BackfillValidationError("invalid official InfoHub workspace URL")
    language = match.group(1)
    unique_key = match.group(2).lower()
    return OfficialSourceIdentity(
        workspace_url=(
            f"https://infohub.rs.ge/{language}/workspace/document/{unique_key}"
        ),
        language=language,
        unique_key=unique_key,
        api_url=(
            "https://infohubapi.rs.ge/api/documents/"
            f"{unique_key}/details-by-key?openFromSearch=false"
        ),
    )


def _type_name(value: Any) -> str | None:
    if isinstance(value, dict):
        normalized = str(value.get("name") or "").strip()
        return normalized or None
    return None


def normalized_infohub_text(payload: dict[str, Any]) -> str:
    """Reproduce the legacy API scraper's text normalization exactly."""
    parts: list[str] = []
    name = str(payload.get("name") or "").strip()
    if name:
        parts.append(name)
    for key in ("type", "baseType"):
        name_value = _type_name(payload.get(key))
        if name_value:
            parts.append(name_value)
    html = payload.get("description") or payload.get("additionalDescription") or ""
    body = BeautifulSoup(str(html), "html.parser").get_text(separator="\n").strip()
    if body:
        parts.append(body)
    return "\n\n".join(parts).strip()


def compact_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _clean_native_text(text: str) -> str:
    """Frozen copy of the native-v2 exporter's text cleanup contract."""
    import unicodedata

    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"[\ufeff\u200b\u200c\u200d\u2060]", "", text)
    text = text.replace("\u00a0", " ")
    for token in (
        "ჩამოტვირთვა",
        "გაზიარება",
        "უკუკავშირი",
        "დოკუმენტის სტატისტიკა",
        "საიტი მუშაობს სატესტო რეჟიმში",
    ):
        text = text.replace(token, "")
    text = re.sub(r"\*\*\s*_\s*_\s*\*\*", "", text)
    text = re.sub(r"\*\*\s*\*\*", "", text)
    text = re.sub(r"__\s*_\s*_\s*__", "", text)
    text = re.sub(r"__\s*__", "", text)
    text = re.sub(r"\*\s+\*", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"(\n\s*){2,}", "\n\n", text)
    return "\n".join(line.rstrip() for line in text.splitlines()).strip()


def _legal_heading_level(text: str) -> int | None:
    value = text.strip()
    if value.startswith("კარი"):
        return 2
    if value.startswith("თავი"):
        return 3
    if value.startswith("მუხლი"):
        return 4
    return None


def _html_fragment_to_native_markdown(html: Any) -> str:
    """Frozen native-api-reparse-all-from-raw-v2 HTML conversion."""
    if not html:
        return ""
    soup = BeautifulSoup(str(html), "html.parser")
    for tag in soup(["script", "style", "header", "footer", "nav"]):
        tag.decompose()

    def walk(element: Any) -> str:
        if isinstance(element, str):
            return element
        if element.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(element.name[1])
            return f"\n{'#' * level} {element.get_text(' ', strip=True)}\n"
        if element.name == "p":
            return f"\n{element.get_text(' ', strip=True)}\n"
        if element.name == "li":
            return f"\n- {element.get_text(strip=True)}\n"
        if element.name in ("ul", "ol"):
            ordered = element.name == "ol"
            items: list[str] = []
            count = 1
            for child in element.children:
                if isinstance(child, str):
                    if child.strip():
                        items.append(child.strip())
                elif child.name == "li":
                    content = "".join(walk(item) for item in child.children).strip()
                    prefix = f"{count}." if ordered else "-"
                    items.append(f"{prefix} {content}" if content else prefix)
                    count += 1
                elif child.name in ("ul", "ol"):
                    items.append(walk(child))
                else:
                    content = "".join(walk(item) for item in child.children).strip()
                    if content:
                        items.append(content)
            return "\n" + "\n".join(items) + "\n" if items else ""
        if element.name == "br":
            return "\n"
        if element.name in ("strong", "b"):
            content = "".join(walk(item) for item in element.children)
            level = _legal_heading_level(content)
            if level:
                return f"\n{'#' * level} {content.strip()}\n"
            return f"**{content}**"
        if element.name in ("em", "i"):
            return f"*{''.join(walk(item) for item in element.children)}*"
        if element.name == "a":
            href = (element.get("href") or "").strip()
            content = "".join(walk(item) for item in element.children)
            if href:
                return f"[{content}]({href})" if content.strip() else href
            return content
        if element.name == "img":
            src = (element.get("src") or "").strip()
            alt = (element.get("alt") or "").strip()
            if not src:
                return ""
            if src.startswith("data:"):
                return f"[Image (base64){f': {alt}' if alt else ''}]"
            return f"![{alt}]({src})"
        if element.name == "table":
            rows: list[list[str]] = []
            for tr in element.find_all("tr"):
                if tr.find_parent("table") is not element:
                    continue
                row: list[str] = []
                for cell in tr.find_all(["th", "td"]):
                    if cell.find_parent("tr") is tr:
                        row.append(
                            "".join(walk(item) for item in cell.children).strip()
                        )
                if row:
                    rows.append(row)
            if not rows:
                return ""
            columns = max(len(row) for row in rows)
            simple = columns > 0 and all(len(row) == columns for row in rows)
            if simple and any("\n" in cell for row in rows for cell in row):
                simple = False
            if simple:
                markdown_rows: list[str] = []
                for index, row in enumerate(rows):
                    padded = row + [""] * (columns - len(row))
                    markdown_rows.append("| " + " | ".join(padded) + " |")
                    if index == 0:
                        markdown_rows.append(
                            "| " + " | ".join(["---"] * columns) + " |"
                        )
                return "\n" + "\n".join(markdown_rows) + "\n"
            markdown_rows = []
            for row_index, row in enumerate(rows):
                markdown_rows.append(f"--- Row {row_index + 1} ---")
                for cell_index, cell in enumerate(row):
                    markdown_rows.append(
                        f"  {cell_index + 1}. {cell}" if cell else "  [empty]"
                    )
            return "\n" + "\n".join(markdown_rows) + "\n"
        if element.name == "div":
            classes = element.get("class", [])
            is_ql_block = any(str(value).startswith("ql-") for value in classes)
            block_names = (
                "p",
                "li",
                "h1",
                "h2",
                "h3",
                "h4",
                "h5",
                "h6",
                "div",
                "table",
                "ul",
                "ol",
            )
            has_block_child = element.find(block_names) is not None
            content = "".join(walk(item) for item in element.children)
            if is_ql_block or has_block_child:
                if is_ql_block and not has_block_child and content.strip():
                    return f"\n{content.strip()}\n"
                return content
            content = content.strip()
            return f"\n{content}\n" if content else ""
        return "".join(walk(item) for item in element.children)

    return _clean_native_text(walk(soup))


def _selected_native_html(payload: dict[str, Any]) -> str:
    candidates = ("markdown", "description", "additionalDescription")
    legal_markers = ("მუხლი", "თავი", "კარი")
    chrome = (
        "ჩამოტვირთვა",
        "გაზიარება",
        "უკუკავშირი",
        "დოკუმენტის სტატისტიკა",
    )
    scores: dict[str, float] = {}
    for field in candidates:
        raw = payload.get(field)
        if not isinstance(raw, str) or not raw.strip():
            scores[field] = 0.0
            continue
        value = raw.strip()
        score = len(value) * 0.001
        score += sum(value.count(marker) * 5.0 for marker in legal_markers)
        score += len(re.findall(r"<a\s+[^>]*href=|https?://", value)) * 2.0
        if any(tag in value for tag in ("<li", "<ul", "<ol", "<table")):
            score += 5.0
        score -= sum(value.count(token) * 10.0 for token in chrome)
        scores[field] = score
    selected = max(scores, key=scores.get)
    return str(payload.get(selected) or "")


def _document_markdown(
    payload: dict[str, Any],
    source_url: str,
    body_markdown: str,
    *,
    include_title: bool,
    include_species: bool,
) -> str:
    title = str(payload.get("name") or "Untitled document").strip()
    type_name = _type_name(payload.get("type")) or ""
    base_type_name = _type_name(payload.get("baseType")) or ""
    author = payload.get("author") if isinstance(payload.get("author"), dict) else {}
    recipient = (
        payload.get("recipient") if isinstance(payload.get("recipient"), dict) else {}
    )
    status = payload.get("status") if isinstance(payload.get("status"), dict) else {}
    author_name = str(author.get("fullName") or "").strip()
    recipient_name = str(recipient.get("name") or "").strip()
    status_name = str(status.get("name") or "").strip()
    published_at = (
        payload.get("publishDate")
        or payload.get("createDate")
        or payload.get("updateDate")
    )
    parts: list[str] = [title] if include_title else []
    if payload.get("documentNumber"):
        parts.append(f"დოკუმენტის ნომერი: {payload['documentNumber']}")
    if type_name:
        parts.append(f"ტიპი: {type_name}")
    if base_type_name:
        parts.append(f"ბაზური ტიპი: {base_type_name}")
    if recipient_name:
        parts.append(f"მიმღები ორგანო: {recipient_name}")
    elif author_name:
        parts.append(f"ავტორი: {author_name}")
    if published_at:
        parts.append(f"გამოქვეყნების თარიღი: {str(published_at)[:10]}")
    if payload.get("receiptDate"):
        parts.append(f"მიღების თარიღი: {str(payload['receiptDate'])[:10]}")
    if status_name:
        parts.append(f"სტატუსი: {status_name}")
    if include_species and payload.get("species"):
        parts.append(f"species: {payload['species']}")
    parts.append(f"წყარო: {source_url}")
    if body_markdown:
        parts.append(body_markdown)
    return "\n\n".join(str(part) for part in parts if part).strip()


def _native_v2_markdown(payload: dict[str, Any], source_url: str) -> str:
    body = _html_fragment_to_native_markdown(_selected_native_html(payload))
    return _document_markdown(
        payload,
        source_url,
        body,
        include_title=False,
        include_species=False,
    )


def _scrapling_text(html: str) -> dict[str, Any]:
    try:
        from scrapling.parser import Selector
    except ImportError as exc:
        raise BackfillValidationError(
            "scrapling is required to verify a scrapling-repaired legacy source"
        ) from exc
    if not html:
        return {"text": "", "markdown": "", "content_length": 0}
    selector = Selector(
        html,
        adaptive=True,
        huge_tree=True,
        keep_comments=False,
        keep_cdata=False,
    )

    def clean_lines(text: str) -> str:
        text = str(text or "").replace("\u00a0", " ").replace("\r", "\n")
        lines = [line.strip() for line in text.splitlines()]
        cleaned: list[str] = []
        previous: str | None = None
        for line in (line for line in lines if line):
            if line != previous:
                cleaned.append(line)
            previous = line
        return "\n".join(cleaned).strip()

    def score(text: str) -> int:
        return sum(text.count(marker) for marker in _LEGAL_HEADINGS)

    candidates: list[tuple[str, str, int]] = []
    for css in (
        "article",
        "main",
        ".content",
        "#content",
        ".document-content",
        ".ProseMirror",
        ".ql-editor",
        "body",
        "div",
    ):
        try:
            nodes = selector.css(css)
        except Exception:
            continue
        for node in list(nodes)[:25]:
            try:
                text = node.get_all_text(
                    ignore_tags=("script", "style", "noscript")
                ) or ""
            except Exception:
                continue
            text = clean_lines(text)
            if len(text) >= 200:
                candidates.append((css, text, score(text)))
    try:
        root_text = selector.get_all_text(
            ignore_tags=("script", "style", "noscript")
        ) or ""
    except Exception:
        root_text = ""
    root_text = clean_lines(root_text)
    if len(root_text) >= 200:
        candidates.append(("__root__", root_text, score(root_text)))
    if not candidates:
        return {"text": "", "markdown": "", "content_length": 0}
    _, best_text, _ = max(candidates, key=lambda item: (item[2], len(item[1])))
    markdown_lines: list[str] = []
    for raw_line in clean_lines(best_text).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("კარი"):
            markdown_lines.append(f"## {line}")
        elif line.startswith("თავი"):
            markdown_lines.append(f"### {line}")
        elif line.startswith("მუხლი"):
            markdown_lines.append(f"#### {line}")
        else:
            markdown_lines.append(line)
    return {
        "text": best_text,
        "markdown": "\n\n".join(markdown_lines).strip(),
        "content_length": len(best_text),
    }


def _scrapling_repair_markdown(payload: dict[str, Any], source_url: str) -> str:
    html = _selected_native_html(payload)
    base_body = _html_fragment_to_native_markdown(html)
    scrapling = _scrapling_text(html)
    chosen_body = base_body
    if scrapling["content_length"] >= max(1500, int(len(base_body) * 1.15)):
        chosen_body = scrapling["markdown"]
    elif len(base_body) < 800 and scrapling["content_length"] >= max(
        1200, len(base_body) * 2
    ):
        chosen_body = scrapling["markdown"]
    return _document_markdown(
        payload,
        source_url,
        chosen_body,
        include_title=True,
        include_species=True,
    )


def legacy_normalized_text(
    payload: dict[str, Any],
    *,
    source: OfficialSourceIdentity,
    normalizer: str,
) -> str:
    method = str(normalizer or "")
    if method == LEGACY_NORMALIZER_PLAIN:
        return normalized_infohub_text(payload)
    if method == LEGACY_NORMALIZER_NATIVE:
        return _native_v2_markdown(payload, source.workspace_url)
    if method == LEGACY_NORMALIZER_SCRAPLING:
        return _scrapling_repair_markdown(payload, source.workspace_url)
    raise BackfillValidationError("unsupported legacy source normalizer")


def validate_official_api_bytes(
    raw: bytes,
    *,
    source: OfficialSourceIdentity,
    expected_legacy_md5: str,
    expected_legacy_full_text_md5: str | None = None,
    expected_legacy_compact_md5: str | None = None,
    legacy_normalizer: str = LEGACY_NORMALIZER_PLAIN,
    allow_content_drift: bool = False,
) -> tuple[dict[str, Any], str, str]:
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_OFFICIAL_RESPONSE_BYTES:
        raise BackfillValidationError("official API response has an invalid size")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BackfillValidationError("official API response is not UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise BackfillValidationError("official API response is not an object")
    if str(payload.get("uniqueKey") or "").lower() != source.unique_key:
        raise BackfillValidationError("official API uniqueKey does not match the URL")
    expected_md5 = str(expected_legacy_md5 or "").lower()
    if not re.fullmatch(r"[0-9a-f]{32}", expected_md5):
        raise BackfillValidationError("legacy document MD5 is missing or invalid")
    normalized_text = legacy_normalized_text(
        payload,
        source=source,
        normalizer=legacy_normalizer,
    )
    actual_md5 = hashlib.md5(normalized_text.encode("utf-8")).hexdigest()
    if actual_md5 == expected_md5:
        return payload, normalized_text, SOURCE_VERIFICATION_EXACT
    compact_expected = str(expected_legacy_compact_md5 or "").lower()
    if not re.fullmatch(r"[0-9a-f]{32}", compact_expected):
        raise BackfillValidationError(
            "legacy compact document MD5 is missing or invalid"
        )
    compact_actual = hashlib.md5(
        compact_whitespace(normalized_text).encode("utf-8")
    ).hexdigest()
    full_text_expected = str(expected_legacy_full_text_md5 or "").lower()
    if (
        compact_actual == compact_expected
        and full_text_expected == expected_md5
    ):
        return payload, normalized_text, SOURCE_VERIFICATION_WHITESPACE
    if allow_content_drift:
        return payload, normalized_text, SOURCE_VERIFICATION_DRIFT
    raise BackfillValidationError("official source text drifted from the legacy row")


def canonical_article_ref(value: Any) -> str | None:
    raw = str(value or "").strip().translate(_ZERO_WIDTH)
    raw = raw.translate(_SUPERSCRIPT_TO_ASCII)
    raw = re.sub(r"\s*-\s*", "-", raw)
    return raw if CANONICAL_ARTICLE_RE.fullmatch(raw) else None


def _article_pattern(article_ref: str) -> re.Pattern[str]:
    base, separator, suffix = article_ref.partition("-")
    if separator:
        superscript = suffix.translate(_ASCII_TO_SUPERSCRIPT)
        number = rf"{re.escape(base)}(?:-{re.escape(suffix)}|{re.escape(superscript)})"
    else:
        number = re.escape(base)
    return re.compile(
        rf"(?<!\d)(?:მე[-\s]?)?{number}(?:[-\s]?ე)?\s*მუხლ[ა-ჰ]*",
        re.IGNORECASE,
    )


def classify_deterministic_operation(
    official_text: str,
    *,
    article_ref: str,
    legacy_action: str,
    window_chars: int = 700,
) -> dict[str, Any]:
    """Fail-closed correlation of one legacy hint to an official legal clause."""
    canonical_ref = canonical_article_ref(article_ref)
    action = str(legacy_action or "").strip().lower()
    if canonical_ref is None:
        return {"state": "needs_review", "reason": "invalid_article_ref"}
    if action not in ALLOWED_LEGACY_ACTIONS:
        return {"state": "needs_review", "reason": "unsupported_legacy_action"}
    text_value = str(official_text or "").translate(_ZERO_WIDTH)
    matches = list(_article_pattern(canonical_ref).finditer(text_value))
    if not matches:
        return {"state": "needs_review", "reason": "article_not_found_in_official_text"}

    detected: set[str] = set()
    marker_names: set[str] = set()
    for match in matches:
        start = max(0, match.start() - window_chars)
        end = min(len(text_value), match.end() + window_chars)
        window = text_value[start:end].lower()
        for operation_type, markers in _OPERATION_MARKERS.items():
            for marker in markers:
                if marker in window:
                    detected.add(operation_type)
                    marker_names.add(f"{operation_type}:{marker}")

    expected_operation = ACTION_OPERATION_TYPES[action]
    if not detected:
        return {"state": "needs_review", "reason": "operative_formula_not_found"}
    if detected != {expected_operation}:
        return {
            "state": "needs_review",
            "reason": "operative_formula_conflict",
            "detected_operation_types": sorted(detected),
        }
    return {
        "state": "operation_candidate",
        "reason": "explicit_official_formula",
        "article_ref": canonical_ref,
        "operation_type": expected_operation,
        "article_mention_count": len(matches),
        "marker_codes": sorted(
            hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
            for value in marker_names
        ),
    }


def candidate_fingerprint(candidate: dict[str, Any]) -> str:
    material = {
        "legacy_law_amendment_id": candidate["legacy_law_amendment_id"],
        "item_index": candidate["item_index"],
        "target_legacy_document_id": candidate.get("target_legacy_document_id"),
        "article_ref": candidate.get("article_ref"),
        "legacy_action": candidate.get("legacy_action"),
        "effective_date": candidate.get("effective_date"),
    }
    return sha256_json(material)


def operation_key(candidate: dict[str, Any], source_sha256: str) -> str:
    return sha256_json(
        {
            "contract": BACKFILL_CONTRACT,
            "candidate_fingerprint": candidate_fingerprint(candidate),
            "operation_type": candidate["classification"]["operation_type"],
            "source_sha256": source_sha256,
        }
    )


def manifest_sha256(manifest_without_hash: dict[str, Any]) -> str:
    material = dict(manifest_without_hash)
    material.pop("manifest_sha256", None)
    return sha256_json(material)


def safe_bundle_file(bundle_dir: Path, relative_value: str) -> Path:
    relative = Path(str(relative_value or ""))
    if relative.is_absolute() or ".." in relative.parts:
        raise BackfillValidationError("bundle file path escapes the bundle")
    root = bundle_dir.resolve()
    unresolved = root
    for part in relative.parts:
        unresolved = unresolved / part
        if unresolved.is_symlink():
            raise BackfillValidationError("bundle source must not use symlinks")
    path = unresolved.resolve()
    if root not in path.parents:
        raise BackfillValidationError("bundle file path escapes the bundle")
    if not path.is_file():
        raise BackfillValidationError("bundle source must be a regular file")
    return path


def validate_bundle(
    bundle_dir: Path,
    *,
    expected_manifest_sha256: str | None = None,
    normalized_texts: dict[str, str] | None = None,
) -> dict[str, Any]:
    # Optional offline-review output, populated only after the entire bundle
    # passes. Reuse text from the very bytes just verified; never parse a second
    # potentially replaced file, or make callers normalize the whole corpus twice.
    if normalized_texts:
        raise BackfillValidationError("normalized text output must be empty")
    verified_texts: dict[str, str] = {}
    if bundle_dir.is_symlink():
        raise BackfillValidationError("bundle must not be a symlink")
    root = bundle_dir.resolve()
    manifest_path = root / "manifest.json"
    if not root.is_dir():
        raise BackfillValidationError("bundle must be a regular directory")
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise BackfillValidationError("bundle manifest must be a regular file")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise BackfillValidationError("bundle manifest must be an object")
    if manifest.get("schema_version") != BUNDLE_SCHEMA_VERSION:
        raise BackfillValidationError("unsupported temporal backfill bundle schema")
    if manifest.get("backfill_contract") != BACKFILL_CONTRACT:
        raise BackfillValidationError("unexpected temporal backfill contract")
    actual_manifest_sha = manifest_sha256(manifest)
    if manifest.get("manifest_sha256") != actual_manifest_sha:
        raise BackfillValidationError("bundle manifest SHA-256 mismatch")
    if expected_manifest_sha256 and expected_manifest_sha256 != actual_manifest_sha:
        raise BackfillValidationError("bundle does not match the reviewed manifest SHA-256")

    sources = manifest.get("sources")
    amendments = manifest.get("amendments")
    if not isinstance(sources, list) or not isinstance(amendments, list):
        raise BackfillValidationError("bundle sources and amendments must be arrays")
    source_urls: set[str] = set()
    source_by_document: dict[str, dict[str, Any]] = {}
    for source in sources:
        if not isinstance(source, dict):
            raise BackfillValidationError("invalid bundle source entry")
        legacy_id = str(source.get("legacy_document_id") or "")
        try:
            UUID(legacy_id)
        except ValueError as exc:
            raise BackfillValidationError("invalid legacy source UUID") from exc
        identity = parse_workspace_source_url(str(source.get("workspace_url") or ""))
        if identity.api_url != source.get("api_url"):
            raise BackfillValidationError("bundle API URL mismatch")
        if identity.workspace_url != source.get("workspace_url"):
            raise BackfillValidationError("bundle workspace URL is not canonical")
        if identity.unique_key != source.get("unique_key"):
            raise BackfillValidationError("bundle source uniqueKey mismatch")
        if identity.language != source.get("language"):
            raise BackfillValidationError("bundle source language mismatch")
        roles = source.get("roles")
        if (
            not isinstance(roles, list)
            or not roles
            or any(role not in {"amendment", "target"} for role in roles)
            or len(roles) != len(set(roles))
        ):
            raise BackfillValidationError("bundle source roles are invalid")
        extraction_method = source.get("legacy_extraction_method")
        expected_normalizer = (
            LEGACY_NORMALIZER_PLAIN
            if extraction_method is None
            else str(extraction_method)
        )
        if (
            expected_normalizer not in ALLOWED_LEGACY_NORMALIZERS
            or source.get("legacy_normalizer") != expected_normalizer
        ):
            raise BackfillValidationError("legacy source normalizer contract mismatch")
        if legacy_id in source_by_document or identity.workspace_url in source_urls:
            raise BackfillValidationError("duplicate source identity in bundle")
        source_path = safe_bundle_file(root, str(source.get("file") or ""))
        raw = source_path.read_bytes()
        actual_sha = hashlib.sha256(raw).hexdigest()
        if actual_sha != source.get("content_sha256"):
            raise BackfillValidationError("bundle source SHA-256 mismatch")
        if len(raw) != source.get("byte_length"):
            raise BackfillValidationError("bundle source byte length mismatch")
        if not re.fullmatch(
            r"[0-9a-f]{32}", str(source.get("legacy_compact_md5") or "")
        ):
            raise BackfillValidationError("legacy compact source MD5 is invalid")
        if not re.fullmatch(
            r"[0-9a-f]{32}", str(source.get("legacy_full_text_md5") or "")
        ):
            raise BackfillValidationError("legacy full-text source MD5 is invalid")
        if source.get("media_type") != "application/json":
            raise BackfillValidationError("bundle source media type mismatch")
        if source.get("http_status") != 200:
            raise BackfillValidationError("bundle source HTTP status mismatch")
        parse_iso_datetime(str(source.get("captured_at_utc") or ""))
        _, normalized_text, verification_mode = validate_official_api_bytes(
            raw,
            source=identity,
            expected_legacy_md5=str(source.get("legacy_md5") or ""),
            expected_legacy_full_text_md5=str(
                source.get("legacy_full_text_md5") or ""
            ),
            expected_legacy_compact_md5=str(
                source.get("legacy_compact_md5") or ""
            ),
            legacy_normalizer=str(source.get("legacy_normalizer") or ""),
            allow_content_drift=True,
        )
        recorded_verification_mode = source.get("verification_mode")
        if recorded_verification_mode not in ALLOWED_SOURCE_VERIFICATION_MODES:
            raise BackfillValidationError("invalid source verification mode")
        if verification_mode != recorded_verification_mode:
            raise BackfillValidationError("source verification mode mismatch")
        if normalized_texts is not None:
            verified_texts[legacy_id] = normalized_text
        source_urls.add(identity.workspace_url)
        source_by_document[legacy_id] = source

    amendment_ids: set[str] = set()
    for amendment in amendments:
        if not isinstance(amendment, dict):
            raise BackfillValidationError("invalid bundle amendment entry")
        amendment_id = str(amendment.get("legacy_law_amendment_id") or "")
        try:
            UUID(amendment_id)
        except ValueError as exc:
            raise BackfillValidationError("invalid legacy amendment UUID") from exc
        if not amendment_id or amendment_id in amendment_ids:
            raise BackfillValidationError("duplicate amendment identity in bundle")
        amendment_ids.add(amendment_id)
        amendment_doc = str(amendment.get("amendment_legacy_document_id") or "")
        target_doc = str(amendment.get("target_legacy_document_id") or "")
        if amendment_doc not in source_by_document:
            raise BackfillValidationError("amendment source is absent from bundle")
        if target_doc and target_doc not in source_by_document:
            raise BackfillValidationError("target source is absent from bundle")
        parse_iso_date(amendment.get("adoption_date"))
        parse_iso_date(amendment.get("effective_date"))
        candidates = amendment.get("candidates")
        if not isinstance(candidates, list):
            raise BackfillValidationError("amendment candidates must be an array")
        for index, candidate in enumerate(candidates):
            if not isinstance(candidate, dict) or candidate.get("item_index") != index:
                raise BackfillValidationError("candidate indexes are not deterministic")
            if candidate.get("candidate_fingerprint") != candidate_fingerprint(candidate):
                raise BackfillValidationError("candidate fingerprint mismatch")
            classification = candidate.get("classification") or {}
            state = classification.get("state")
            if state not in {"operation_candidate", "needs_review"}:
                raise BackfillValidationError("invalid candidate classification state")
            if candidate.get("target_legacy_document_id") != (
                target_doc or None
            ):
                raise BackfillValidationError("candidate target identity mismatch")
            parse_iso_date(candidate.get("effective_date"))
            if state == "operation_candidate":
                if (
                    source_by_document[amendment_doc].get("verification_mode")
                    == SOURCE_VERIFICATION_DRIFT
                ):
                    raise BackfillValidationError(
                        "drifted amendment source promoted an operation"
                    )
                operation_type = classification.get("operation_type")
                if operation_type not in {"add", "replace", "repeal"}:
                    raise BackfillValidationError("invalid promoted operation type")
                if operation_type != ACTION_OPERATION_TYPES.get(
                    candidate.get("legacy_action")
                ):
                    raise BackfillValidationError("operation conflicts with legacy action")
                if classification.get("article_ref") != canonical_article_ref(
                    candidate.get("article_ref")
                ):
                    raise BackfillValidationError("operation article reference mismatch")
                mention_count = classification.get("article_mention_count")
                if not isinstance(mention_count, int) or mention_count <= 0:
                    raise BackfillValidationError("invalid article mention count")
                marker_codes = classification.get("marker_codes")
                if (
                    not isinstance(marker_codes, list)
                    or not marker_codes
                    or any(
                        not re.fullmatch(r"[0-9a-f]{16}", str(code))
                        for code in marker_codes
                    )
                ):
                    raise BackfillValidationError("invalid operative marker codes")

    summary = manifest.get("summary") or {}
    if summary.get("sources") != len(sources):
        raise BackfillValidationError("bundle source summary mismatch")
    if summary.get("amendments") != len(amendments):
        raise BackfillValidationError("bundle amendment summary mismatch")
    candidates = [
        candidate
        for amendment in amendments
        for candidate in amendment["candidates"]
    ]
    operation_candidates = sum(
        candidate["classification"]["state"] == "operation_candidate"
        for candidate in candidates
    )
    expected_summary = {
        "candidate_items": len(candidates),
        "operation_candidates": operation_candidates,
        "candidate_items_needing_review": len(candidates) - operation_candidates,
        "amendment_rows_with_issues": sum(
            bool(amendment.get("row_issues")) for amendment in amendments
        ),
        "expert_review_rows": sum(
            max(1, len(amendment["candidates"])) for amendment in amendments
        ),
        "legacy_normalizers": dict(
            sorted(
                Counter(
                    source["legacy_normalizer"] for source in sources
                ).items()
            )
        ),
        "source_verification_modes": dict(
            sorted(
                Counter(source["verification_mode"] for source in sources).items()
            )
        ),
        "postgresql_writes_allowed": False,
        "public_answer_routing_changed": False,
    }
    for field, expected in expected_summary.items():
        if summary.get(field) != expected:
            raise BackfillValidationError(f"bundle {field} summary mismatch")
    if normalized_texts is not None:
        normalized_texts.update(verified_texts)
    return manifest


def parse_iso_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise BackfillValidationError("bundle timestamp must contain a timezone")
    return parsed.astimezone(UTC).replace(tzinfo=None)


def parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise BackfillValidationError("bundle date is invalid") from exc
