from __future__ import annotations

import re
from typing import Any, Dict, Tuple

from scrapling.parser import Selector

from export_pipeline.infohub_native_api import (
    build_source_url,
    html_fragment_to_markdown,
    native_detail_to_raw_payload,
    score_candidate_body,
)

LEGAL_HEADINGS = ("კარი", "თავი", "მუხლი")


def clean_lines(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\u00a0", " ")
    text = text.replace("\r", "\n")
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    cleaned = []
    last = None
    for line in lines:
        if line == last:
            continue
        cleaned.append(line)
        last = line
    return "\n".join(cleaned).strip()


def simple_markdown_from_text(text: str) -> str:
    lines = []
    for raw in clean_lines(text).splitlines():
        line = raw.strip()
        if not line:
            continue
        if any(line.startswith(prefix) for prefix in LEGAL_HEADINGS):
            if line.startswith("კარი"):
                lines.append(f"## {line}")
            elif line.startswith("თავი"):
                lines.append(f"### {line}")
            else:
                lines.append(f"#### {line}")
        else:
            lines.append(line)
    return "\n\n".join(lines).strip()


def legal_signal_score(text: str) -> int:
    if not text:
        return 0
    return sum(text.count(marker) for marker in LEGAL_HEADINGS)


def extract_scrapling_text(html: str) -> Dict[str, Any]:
    if not html:
        return {
            "text": "",
            "markdown": "",
            "content_length": 0,
            "container": None,
            "legal_score": 0,
        }

    selector = Selector(
        html,
        adaptive=True,
        huge_tree=True,
        keep_comments=False,
        keep_cdata=False,
    )

    candidates = []
    for css in ["article", "main", ".content", "#content", ".document-content", ".ProseMirror", ".ql-editor", "body", "div"]:
        try:
            nodes = selector.css(css)
        except Exception:
            continue
        for node in list(nodes)[:25]:
            try:
                text = node.get_all_text(ignore_tags=("script", "style", "noscript")) or ""
            except Exception:
                continue
            text = clean_lines(text)
            if len(text) < 200:
                continue
            candidates.append((css, text, legal_signal_score(text)))

    try:
        full_text = selector.get_all_text(ignore_tags=("script", "style", "noscript")) or ""
    except Exception:
        full_text = ""
    full_text = clean_lines(full_text)
    if len(full_text) >= 200:
        candidates.append(("__root__", full_text, legal_signal_score(full_text)))

    if not candidates:
        return {
            "text": "",
            "markdown": "",
            "content_length": 0,
            "container": None,
            "legal_score": 0,
        }

    best_css, best_text, best_legal = max(
        candidates,
        key=lambda item: (item[2], len(item[1])),
    )
    markdown = simple_markdown_from_text(best_text)
    return {
        "text": best_text,
        "markdown": markdown,
        "content_length": len(best_text),
        "container": best_css,
        "legal_score": best_legal,
    }


def compose_document_markdown(detail: Dict[str, Any], source_url: str, description_md: str) -> str:
    title = (detail.get("name") or "Untitled document").strip()
    species = detail.get("species")
    document_number = detail.get("documentNumber")
    type_name = ((detail.get("type") or {}).get("name") or "").strip()
    base_type_name = ((detail.get("baseType") or {}).get("name") or "").strip()
    author_name = ((detail.get("author") or {}).get("fullName") or "").strip()
    recipient_name = ((detail.get("recipient") or {}).get("name") or "").strip()
    status_name = ((detail.get("status") or {}).get("name") or "").strip()
    published_at = detail.get("publishDate") or detail.get("createDate") or detail.get("updateDate")
    receipt_date = detail.get("receiptDate")

    body_parts = [title]
    if document_number:
        body_parts.append(f"დოკუმენტის ნომერი: {document_number}")
    if type_name:
        body_parts.append(f"ტიპი: {type_name}")
    if base_type_name:
        body_parts.append(f"ბაზური ტიპი: {base_type_name}")
    if recipient_name:
        body_parts.append(f"მიმღები ორგანო: {recipient_name}")
    elif author_name:
        body_parts.append(f"ავტორი: {author_name}")
    if published_at:
        body_parts.append(f"გამოქვეყნების თარიღი: {str(published_at)[:10]}")
    if receipt_date:
        body_parts.append(f"მიღების თარიღი: {str(receipt_date)[:10]}")
    if status_name:
        body_parts.append(f"სტატუსი: {status_name}")
    if species:
        body_parts.append(f"species: {species}")
    body_parts.append(f"წყარო: {source_url}")
    if description_md:
        body_parts.append(description_md)
    return "\n\n".join(part for part in body_parts if part).strip()


def build_scrapling_repaired_payload(detail: Dict[str, Any], *, source_url: str | None = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    source_url = source_url or build_source_url(detail)
    base_payload = native_detail_to_raw_payload(detail, source_url=source_url)
    html = ((base_payload.get("data") or {}).get("html") or "")
    base_markdown = ((base_payload.get("data") or {}).get("markdown") or "")
    base_body_md = html_fragment_to_markdown(html)
    scrapling = extract_scrapling_text(html)

    use_scrapling = False
    chosen_body_md = base_body_md
    if scrapling["content_length"] >= max(1500, int(len(base_body_md) * 1.15)):
        use_scrapling = True
        chosen_body_md = scrapling["markdown"]
    elif len(base_body_md) < 800 and scrapling["content_length"] >= max(1200, len(base_body_md) * 2):
        use_scrapling = True
        chosen_body_md = scrapling["markdown"]

    chosen_markdown = compose_document_markdown(detail, source_url, chosen_body_md)
    repaired_payload = base_payload
    repaired_payload.setdefault("data", {})["markdown"] = chosen_markdown
    repaired_payload["data"].setdefault("metadata", {})["scraplingRepair"] = {
        "used": use_scrapling,
        "base_markdown_len": len(base_markdown),
        "base_body_len": len(base_body_md),
        "scrapling_text_len": scrapling["content_length"],
        "scrapling_container": scrapling["container"],
        "scrapling_legal_score": scrapling["legal_score"],
    }

    diagnostics = {
        "source_url": source_url,
        "base_markdown_len": len(base_markdown),
        "base_body_len": len(base_body_md),
        "scrapling_text_len": scrapling["content_length"],
        "scrapling_container": scrapling["container"],
        "scrapling_legal_score": scrapling["legal_score"],
        "used_scrapling": use_scrapling,
        "repaired_markdown_len": len(chosen_markdown),
        "selected_field": (score_candidate_body(detail) or {}).get("selected_field"),
    }
    return repaired_payload, diagnostics


def needs_db_repair(*, db_full_text_len: int, repaired_markdown_len: int, chunk_count: int, classification: str) -> Tuple[bool, str]:
    if classification in {"broken", "suspicious_card", "suspicious_shrink"}:
        if chunk_count <= 1:
            return True, "single_chunk_or_less"
        if repaired_markdown_len >= 2000 and db_full_text_len < repaired_markdown_len * 0.35:
            return True, "db_too_short_vs_repaired"
        if repaired_markdown_len >= 8000 and db_full_text_len < 2000:
            return True, "db_extremely_short"
        if db_full_text_len == 0:
            return True, "db_empty"
    return False, "not_needed"
