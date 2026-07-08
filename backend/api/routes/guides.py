"""
Public catalog of situational guides (სიტუაციური სახელმძღვანელო) —
the Revenue Service's numbered how-to manuals on specific tax situations.

The landing page is driven by the official registry document
("სიტუაციური სახელმძღვანელოების რეესტრი"), which lists every guide per
topic section together with its status: current edition date or
"ამოღებულია" (withdrawn) + withdrawal date.
"""
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.database import get_db

router = APIRouter(prefix="/guides", tags=["Guides"])

GUIDE_WHERE = r"document_type = 'guideline' AND title ~ 'N ?[0-9]{3,5}\s*$'"
REGISTRY_TITLE = "სიტუაციური სახელმძღვანელოების რეესტრი"

# --- Registry parsing ------------------------------------------------------
# The scraped registry text contains topic sections ("**01 დივიდენდი**", some
# with a footnote after a single trailing "*") and two table renderings:
# "--- Row N ---" blocks with numbered fields, and markdown "|" rows.
# Columns: 1 name, 2 guide number, 3 current edition date OR "ამოღებულია" +
# withdrawal date, 4 old edition date, (5 original adoption date).

_DATE_RE = re.compile(r"(\d{2})\s*\.\s*(\d{2})\s*\.\s*(\d{2}\s*\d{2})")
_SECTION_RE = re.compile(r"(\d{2})\s+([^*]+)")
_FIELD_RE = re.compile(r"^\s*(\d)\.\s?(.*)$")


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("[empty]", " ")).strip()


def _date(s: str) -> Optional[str]:
    m = _DATE_RE.search(s or "")
    if not m:
        return None
    return f"{m.group(1)}.{m.group(2)}.{re.sub(r'[^0-9]', '', m.group(3))}"


def _make_item(cells: List[str]) -> Optional[Dict[str, Any]]:
    name = _clean(cells[0]) if len(cells) > 0 else ""
    number = re.sub(r"\D", "", cells[1] if len(cells) > 1 else "")
    cur = _clean(cells[2]) if len(cells) > 2 else ""
    old = cells[3] if len(cells) > 3 else ""
    if not number or not name or name == "დასახელება":  # table header row
        return None
    withdrawn = "ამოღებულ" in cur
    return {
        "number": number,
        "title": name,
        "status": "withdrawn" if withdrawn else "active",
        "date": _date(cur),  # withdrawal date OR current-edition date
        "old_edition": _date(old),
    }


def parse_registry(full_text: str) -> List[Dict[str, Any]]:
    sections: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    row_cells: Optional[List[str]] = None
    field_idx: Optional[int] = None

    def flush_row() -> None:
        nonlocal row_cells, field_idx
        if row_cells and current is not None:
            item = _make_item(row_cells)
            if item:
                current["items"].append(item)
        row_cells, field_idx = None, None

    for line in full_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("**"):
            flush_row()
            m = _SECTION_RE.search(stripped.strip("*"))
            if m:
                current = {"code": m.group(1), "name": _clean(m.group(2)), "items": []}
                sections.append(current)
            continue
        if current is None:
            continue
        if stripped.startswith("--- Row"):
            flush_row()
            row_cells = []
            continue
        if stripped.startswith("|"):
            flush_row()
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if len(cells) >= 2 and cells[1] not in ("№", "---") and cells[0] != "---":
                item = _make_item(cells)
                if item:
                    current["items"].append(item)
            continue
        if row_cells is not None:
            m = _FIELD_RE.match(line)
            if m and int(m.group(1)) == len(row_cells) + 1:
                row_cells.append(m.group(2))
                field_idx = len(row_cells) - 1
            elif field_idx is not None and stripped:
                row_cells[field_idx] += " " + stripped
    flush_row()
    return [s for s in sections if s["items"]]


# Parsed registry cached per (doc id, updated_at) — reparsed only when the
# nightly scraper refreshes the registry document.
_cache: Dict[str, Any] = {"key": None, "payload": None}


@router.get("/registry")
def guides_registry(db: Session = Depends(get_db)):
    row = db.execute(text("""
        SELECT id::text, full_text, source_url, date_published, updated_at
        FROM documents WHERE title = :t
        ORDER BY date_published DESC NULLS LAST LIMIT 1
    """), {"t": REGISTRY_TITLE}).first()
    if not row or not row[1]:
        raise HTTPException(status_code=404, detail="Registry document not found")

    key = (row[0], str(row[4]))
    if _cache["key"] != key:
        sections = parse_registry(row[1])

        # Link registry rows to the guide documents in our corpus, and append
        # guides published after the registry snapshot (e.g. N 2703+).
        docs = db.execute(text(f"""
            SELECT substring(title FROM 'N ?([0-9]+)\\s*$') AS num,
                   title, source_url, date_published
            FROM documents WHERE {GUIDE_WHERE}
        """)).all()
        by_num = {d[0]: d for d in docs}
        seen = set()
        for section in sections:
            for item in section["items"]:
                seen.add(item["number"])
                doc = by_num.get(item["number"])
                item["doc_url"] = doc[2] if doc else None
        by_code = {s["code"]: s for s in sections}
        for num, doc in sorted(by_num.items()):
            if num in seen:
                continue
            section = by_code.get(num[:2])
            if not section:
                continue
            section["items"].append({
                "number": num,
                "title": re.sub(r"\s*N ?[0-9]+\s*$", "", doc[1]).strip(),
                "status": "active",
                "date": doc[3].strftime("%d.%m.%Y") if doc[3] else None,
                "old_edition": None,
                "doc_url": doc[2],
            })
            section["items"].sort(key=lambda i: i["number"])

        items = [i for s in sections for i in s["items"]]
        _cache["key"] = key
        _cache["payload"] = {
            "published": row[3].isoformat() if row[3] else None,
            "source_url": row[2],
            "total": len(items),
            "active": sum(1 for i in items if i["status"] == "active"),
            "withdrawn": sum(1 for i in items if i["status"] == "withdrawn"),
            "sections": sections,
        }
    return _cache["payload"]
