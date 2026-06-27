from __future__ import annotations

import json
import re
import unicodedata
from bs4 import BeautifulSoup
from html import unescape
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests


class InfohubNativeApiClient:
    def __init__(
        self,
        *,
        api_root: str = "https://infohubapi.rs.ge/api",
        site_root: str = "https://infohub.rs.ge/ka",
        language_code: str = "ka",
        user_agent: str = "Mozilla/5.0",
    ):
        self.api_root = api_root.rstrip("/")
        self.site_root = site_root.rstrip("/")
        self.language_code = language_code
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json, text/plain, */*",
                "Origin": "https://infohub.rs.ge",
                "Referer": f"{self.site_root}",
                "User-Agent": user_agent,
                "languageCode": language_code,
            }
        )

    def get_listing(self, *, species: str, skip: int = 0, take: int = 10) -> Dict[str, Any]:
        response = self.session.get(
            f"{self.api_root}/documents",
            params={"skip": skip, "take": take, "species": species},
            timeout=60,
        )
        response.raise_for_status()
        return response.json()

    def get_document_details(self, document_id: int | str) -> Dict[str, Any]:
        response = self.session.get(f"{self.api_root}/documents/{document_id}/details", timeout=60)
        response.raise_for_status()
        return response.json()


def extract_listing_items(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return data
        for value in payload.values():
            if isinstance(value, list):
                return value
    if isinstance(payload, list):
        return payload
    return []


def build_source_url(detail: Dict[str, Any], *, site_root: str = "https://infohub.rs.ge/ka") -> str:
    key = detail.get("uniqueKey") or detail.get("key") or detail.get("nameLink") or detail.get("id")
    return f"{site_root.rstrip('/')}/workspace/document/{key}"


def _clean_text_content(text: str) -> str:
    """
    Clean unicode noise, UI chrome, and empty markdown artifacts.
    """
    if not text:
        return ""

    # 1. Unicode Normalization & Noise Removal
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r'[\ufeff\u200b\u200c\u200d\u2060]', '', text)
    text = text.replace("\u00a0", " ")

    # 2. Remove UI Chrome tokens
    chrome_tokens = [
        "ჩამოტვირთვა",
        "გაზიარება",
        "უკუკავშირი",
        "დოკუმენტის სტატისტიკა",
        "საიტი მუშაობს სატესტო რეჟიმში"
    ]
    for token in chrome_tokens:
        text = text.replace(token, "")

    # 3. Remove empty markdown-like artifacts
    text = re.sub(r'\*\*\s*_\s*_\s*\*\*', '', text)
    text = re.sub(r'\*\*\s*\*\*', '', text)
    text = re.sub(r'__\s*_\s*_\s*__', '', text)
    text = re.sub(r'__\s*__', '', text)
    text = re.sub(r'\*\s+\*', '', text)

    # 4. Spacing/Whitespace Cleanup
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'(\n\s*){2,}', '\n\n', text)
    text = "\n".join([line.rstrip() for line in text.splitlines()])
    
    return text.strip()


def _get_legal_heading_level(text: str) -> Optional[int]:
    """
    Recognizes legal heading patterns and returns the markdown heading level.
    """
    t = text.strip()
    if t.startswith("კარი"):
        return 2
    if t.startswith("თავი"):
        return 3
    if t.startswith("მუხლი"):
        return 4
    return None


def _safe_plain_text(node: Any) -> str:
    if node is None:
        return ""
    if isinstance(node, str):
        return _clean_text_content(node)
    return _clean_text_content(node.get_text(" ", strip=True))


def _table_rows_from_tag(table_tag: Any) -> List[List[str]]:
    rows: List[List[str]] = []
    for tr in table_tag.find_all('tr'):
        if tr.find_parent('table') is not table_tag:
            continue
        row_cells: List[str] = []
        for cell in tr.find_all(['th', 'td']):
            if cell.find_parent('tr') is not tr:
                continue
            row_cells.append(_safe_plain_text(cell))
        if row_cells:
            rows.append(row_cells)
    return rows


def summarize_structure(elements: List[Dict[str, Any]], *, html_len: int, markdown_len: int) -> Dict[str, Any]:
    table_rows_total = 0
    max_table_cols = 0
    table_count = 0
    heading_count = 0
    list_item_count = 0
    paragraph_count = 0
    image_count = 0
    for element in elements:
        etype = element.get("type")
        if etype == "table":
            table_count += 1
            row_count = int(element.get("row_count") or 0)
            col_count = int(element.get("col_count") or 0)
            table_rows_total += row_count
            max_table_cols = max(max_table_cols, col_count)
        elif etype == "heading":
            heading_count += 1
        elif etype == "list_item":
            list_item_count += 1
        elif etype == "paragraph":
            paragraph_count += 1
        elif etype == "image":
            image_count += 1

    signals: List[str] = []
    if table_count:
        signals.append("has_tables")
    if table_rows_total >= 20:
        signals.append("table_heavy")
    if table_rows_total >= 150:
        signals.append("table_extreme")
    if heading_count >= 8:
        signals.append("section_heavy")
    if list_item_count >= 20:
        signals.append("list_heavy")
    if html_len >= 50000:
        signals.append("long_html")
    if html_len >= 250000:
        signals.append("very_long_html")
    if markdown_len >= 50000:
        signals.append("long_markdown")

    score = 0
    score += min(table_count, 3)
    score += 2 if table_rows_total >= 20 else 0
    score += 2 if table_rows_total >= 150 else 0
    score += 1 if heading_count >= 8 else 0
    score += 1 if list_item_count >= 20 else 0
    score += 1 if html_len >= 50000 else 0
    score += 2 if html_len >= 250000 else 0

    if score >= 6:
        level = "extreme"
    elif score >= 3:
        level = "complex"
    else:
        level = "simple"

    return {
        "level": level,
        "signals": signals,
        "stats": {
            "element_count": len(elements),
            "heading_count": heading_count,
            "paragraph_count": paragraph_count,
            "list_item_count": list_item_count,
            "table_count": table_count,
            "table_rows_total": table_rows_total,
            "max_table_cols": max_table_cols,
            "image_count": image_count,
            "html_len": html_len,
            "markdown_len": markdown_len,
        },
    }


def extract_structured_content(html: Optional[str]) -> Dict[str, Any]:
    if not html:
        return {
            "elements": [],
            "complexity": summarize_structure([], html_len=0, markdown_len=0),
        }

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "header", "footer", "nav"]):
        tag.decompose()

    elements: List[Dict[str, Any]] = []

    def push(element: Dict[str, Any]) -> None:
        markdown = _clean_text_content(str(element.get("markdown") or ""))
        text = _clean_text_content(str(element.get("text") or ""))
        if not markdown and not text:
            return
        payload = dict(element)
        if markdown:
            payload["markdown"] = markdown
        if text:
            payload["text"] = text
        elements.append(payload)

    def visit(node: Any) -> None:
        if isinstance(node, str):
            return

        name = getattr(node, "name", None)
        if not name:
            return

        if name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            text = _safe_plain_text(node)
            push({
                "type": "heading",
                "level": int(name[1]),
                "text": text,
                "markdown": html_fragment_to_markdown(str(node)),
            })
            return

        if name == 'table':
            rows = _table_rows_from_tag(node)
            push({
                "type": "table",
                "text": "\n".join(" | ".join(row) for row in rows),
                "markdown": html_fragment_to_markdown(str(node)),
                "row_count": len(rows),
                "col_count": max((len(row) for row in rows), default=0),
                "rows_preview": rows[:10],
            })
            return

        if name == 'img':
            push({
                "type": "image",
                "text": (node.get('alt') or '').strip(),
                "markdown": html_fragment_to_markdown(str(node)),
                "src": (node.get('src') or '').strip(),
            })
            return

        if name == 'li':
            push({
                "type": "list_item",
                "text": _safe_plain_text(node),
                "markdown": html_fragment_to_markdown(str(node)),
            })
            return

        if name in ['p']:
            push({
                "type": "paragraph",
                "text": _safe_plain_text(node),
                "markdown": html_fragment_to_markdown(str(node)),
            })
            return

        if name in ['strong', 'b']:
            text = _safe_plain_text(node)
            heading_level = _get_legal_heading_level(text)
            if heading_level:
                push({
                    "type": "heading",
                    "level": heading_level,
                    "text": text,
                    "markdown": html_fragment_to_markdown(str(node)),
                })
                return

        if name == 'div':
            classes = node.get('class', [])
            is_ql_block = any(str(cls).startswith('ql-') for cls in classes)
            legal_heading_children = [
                child for child in node.children
                if getattr(child, 'name', None) in ['strong', 'b'] and _get_legal_heading_level(_safe_plain_text(child))
            ]
            if legal_heading_children and _safe_plain_text(node) == _safe_plain_text(legal_heading_children[0]):
                visit(legal_heading_children[0])
                return
            block_children = [
                child for child in node.children
                if getattr(child, 'name', None) in ['p', 'div', 'table', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']
            ]
            if block_children:
                for child in node.children:
                    visit(child)
                return
            text = _safe_plain_text(node)
            if text or is_ql_block:
                push({
                    "type": "paragraph",
                    "text": text,
                    "markdown": html_fragment_to_markdown(str(node)),
                })
            return

        for child in getattr(node, 'children', []):
            visit(child)

    for child in soup.children:
        visit(child)

    deduped: List[Dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for element in elements:
        key = (str(element.get('type')), str(element.get('markdown') or element.get('text') or ''))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(element)

    combined_markdown = "\n\n".join(e.get("markdown", "") for e in deduped if e.get("markdown"))
    complexity = summarize_structure(deduped, html_len=len(html), markdown_len=len(combined_markdown))
    return {
        "elements": deduped,
        "complexity": complexity,
    }


def html_fragment_to_markdown(html: Optional[str]) -> str:
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")

    # Remove noise
    for tag in soup(["script", "style", "header", "footer", "nav"]):
        tag.decompose()

    def walk(element) -> str:
        if isinstance(element, str):
            return element
        
        if element.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            level = int(element.name[1])
            return f"\n{'#' * level} {element.get_text(' ', strip=True)}\n"
        
        if element.name == 'p':
            return f"\n{element.get_text(' ', strip=True)}\n"
            
        if element.name == 'li':
            return f"\n- {element.get_text(strip=True)}\n"

        if element.name in ['ul', 'ol']:
            is_ordered = element.name == 'ol'
            items = []
            count = 1
            for child in element.children:
                if isinstance(child, str):
                    if child.strip():
                        items.append(child.strip())
                elif child.name == 'li':
                    content = "".join(walk(c) for c in child.children).strip()
                    prefix = f"{count}." if is_ordered else "-"
                    if content:
                        items.append(f"{prefix} {content}")
                    else:
                        items.append(f"{prefix}")
                    count += 1
                elif child.name in ['ul', 'ol']:
                    items.append(walk(child))
                else:
                    content = "".join(walk(c) for c in child.children).strip()
                    if content:
                        items.append(content)
            if not items:
                return ""
            return "\n" + "\n".join(items) + "\n"
            
        if element.name == 'br':
            return "\n"
            
        if element.name in ['strong', 'b']:
            content = ''.join(walk(c) for c in element.children)
            level = _get_legal_heading_level(content)
            if level:
                return f"\n{'#' * level} {content.strip()}\n"
            return f"**{content}**"
            
        if element.name in ['em', 'i']:
            return f"*{''.join(walk(c) for c in element.children)}*"

        if element.name == 'a':
            href = (element.get('href') or '').strip()
            content = "".join(walk(c) for c in element.children)
            if href:
                return f"[{content}]({href})" if content.strip() else href
            return content

        if element.name == 'img':
            src = (element.get('src') or '').strip()
            alt = (element.get('alt') or '').strip()
            if not src:
                return ""
            if src.startswith('data:'):
                return f"[Image (base64){f': {alt}' if alt else ''}]"
            return f"![{alt}]({src})"

        if element.name == 'table':
            rows = []
            for tr in element.find_all('tr'):
                if tr.find_parent('table') is not element:
                    continue
                row_cells = []
                for cell in tr.find_all(['th', 'td']):
                    if cell.find_parent('tr') is not tr:
                        continue
                    cell_content = "".join(walk(c) for c in cell.children).strip()
                    row_cells.append(cell_content)
                if row_cells:
                    rows.append(row_cells)

            if not rows:
                return ""

            num_cols = max(len(r) for r in rows)
            is_simple = all(len(r) == num_cols for r in rows) and num_cols > 0
            
            if is_simple:
                for row in rows:
                    if any("\n" in cell for cell in row):
                        is_simple = False
                        break

            if is_simple:
                md_rows = []
                for i, row in enumerate(rows):
                    padded_row = row + [""] * (num_cols - len(row))
                    md_rows.append("| " + " | ".join(padded_row) + " |")
                    if i == 0:
                        md_rows.append("| " + " | ".join(["---"] * num_cols) + " |")
                return "\n" + "\n".join(md_rows) + "\n"
            else:
                md_rows = []
                for i, row in enumerate(rows):
                    md_rows.append(f"--- Row {i+1} ---")
                    for j, cell in enumerate(row):
                        md_rows.append(f"  {j+1}. {cell}" if cell else "  [empty]")
                return "\n" + "\n".join(md_rows) + "\n"

        if element.name == 'div':
            # Recognize Quill-ish signals and block-level containers
            classes = element.get('class', [])
            is_ql_block = any(str(cls).startswith('ql-') for cls in classes)
            
            # Expanded list of block-level elements to prevent container collapse
            block_elements = ['p', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'div', 'table', 'ul', 'ol']
            has_block_child = element.find(block_elements) is not None
            
            if is_ql_block or has_block_child:
                content = "".join(walk(c) for c in element.children)
                # If it's a Quill block containing only text/inline, ensure it's treated as a block
                if is_ql_block and not has_block_child and content.strip():
                    return f"\n{content.strip()}\n"
                return content
            else:
                # Leaf div or inline wrapper: walk children to preserve links/images/etc.
                content = "".join(walk(c) for c in element.children).strip()
                if content:
                    return f"\n{content}\n"
                return ""

        return "".join(walk(c) for c in element.children)

    md = walk(soup)
    return _clean_text_content(md)



def score_candidate_body(detail: Dict[str, Any]) -> Dict[str, Any]:
    candidates = ["markdown", "description", "additionalDescription"]
    scores = {}
    legal_markers = ["მუხლი", "თავი", "კარი"]
    ui_chrome = ["ჩამოტვირთვა", "გაზიარება", "უკუკავშირი", "დოკუმენტის სტატისტიკა"]
    for field in candidates:
        val = detail.get(field)
        if not isinstance(val, str):
            scores[field] = 0.0
            continue
        text = val.strip()
        if not text:
            scores[field] = 0.0
            continue
        score = len(text) * 0.001
        for marker in legal_markers:
            score += text.count(marker) * 5.0
        links = len(re.findall(r'<a\s+[^>]*href=|https?://', text))
        score += links * 2.0
        if any(tag in text for tag in ["<li", "<ul", "<ol", "<table"]):
            score += 5.0
        for token in ui_chrome:
            score -= text.count(token) * 10.0
        scores[field] = score
    selected_field = max(scores, key=scores.get)
    return {
        "sourceSelection": {
            "candidate_fields": candidates,
            "selection_scores": scores,
            "selected_field": selected_field,
            "selection_reason": f"Score: {scores[selected_field]:.2f}",
        },
        "selected_field": selected_field,
        "selected_value": detail.get(selected_field, ""),
    }


def native_detail_to_raw_payload(
    detail: Dict[str, Any],
    *,
    site_root: str = "https://infohub.rs.ge/ka",
    source_url: Optional[str] = None,
) -> Dict[str, Any]:
    source_url = source_url or build_source_url(detail, site_root=site_root)
    selection = score_candidate_body(detail)
    description_html = selection["selected_value"]
    structured_content = extract_structured_content(description_html)
    description_md = html_fragment_to_markdown(description_html)

    title = (detail.get("name") or "Untitled document").strip()
    species = detail.get("species")
    document_number = detail.get("documentNumber")
    type_name = ((detail.get("type") or {}).get("name") or "").strip()
    base_type_name = ((detail.get("baseType") or {}).get("name") or "").strip()
    author_name = ((detail.get("author") or {}).get("fullName") or "").strip()
    recipient_name = ((detail.get("recipient") or {}).get("name") or "").strip()
    status_name = ((detail.get("status") or {}).get("name") or "").strip()
    status_type = ((detail.get("status") or {}).get("type") or "").strip()
    published_at = detail.get("publishDate") or detail.get("createDate") or detail.get("updateDate")
    receipt_date = detail.get("receiptDate")
    tags = [part for part in [type_name, base_type_name, species] if part]

    body_parts: List[str] = []
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
    body_parts.append(f"წყარო: {source_url}")
    if description_md:
        body_parts.append(description_md)
    markdown = "\n\n".join(part for part in body_parts if part).strip()

    metadata = {
        "title": title,
        "siteName": recipient_name or author_name or "შემოსავლების სამსახური",
        "description": " | ".join(tags),
        "publishedTime": str(published_at)[:10] if published_at else None,
        "receiptDate": str(receipt_date)[:10] if receipt_date else None,
        "species": species,
        "type": type_name,
        "baseType": base_type_name,
        "documentNumber": document_number,
        "apiDocumentId": detail.get("id"),
        "apiDocumentKey": detail.get("key"),
        "apiDocumentUniqueKey": detail.get("uniqueKey"),
        "apiAuthorName": author_name,
        "recipientName": recipient_name,
        "statusName": status_name,
        "statusType": status_type,
        "sourceUrl": source_url,
        "sourceSelection": selection["sourceSelection"],
        "complexity": structured_content["complexity"],
        "structureStats": structured_content["complexity"].get("stats", {}),
    }

    return {
        "data": {
            "markdown": markdown,
            "html": description_html,
            "links": [source_url],
            "metadata": metadata,
            "content": structured_content,
        },
        "native_detail": detail,
    }


def save_listing_snapshot(output_root: Path, *, species: str, page: int, payload: Dict[str, Any]) -> Path:
    listings_dir = output_root / "raw" / "listings" / species
    listings_dir.mkdir(parents=True, exist_ok=True)
    path = listings_dir / f"page-{page:04d}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
