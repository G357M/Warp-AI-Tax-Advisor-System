#!/usr/bin/env python
"""Extract structured facts from amendment acts into law_amendments.

For every law document whose title marks it as an amendment
("...ცვლილების შეტანის შესახებ/თაობაზე") and that has no law_amendments row:
- deterministically parse the title: act number, adoption date, amended law name;
- ask the LLM (strict JSON, temperature 0) for the affected articles with short
  old/new norm summaries in Russian and the entry-into-force date;
- resolve the amended law to a corpus document and record the relation in
  document_relations (relation_type='amends').

Incremental and resumable — the same command serves bulk backfill and the
nightly increment.

Usage (inside infohub-backend):
    python scripts/extract_law_amendments.py --limit 30   # validation sample
    python scripts/extract_law_amendments.py              # full backfill / nightly
"""
import argparse
import json
import logging
import re
import sys
import time
from datetime import datetime, date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import text as sa_text

from core.config import settings
from core.database import SessionLocal, Base, engine
from models.document import Document, LawAmendment, DocumentRelation

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logger = logging.getLogger("law_amendments")

EXTRACTION_VERSION = 1
HEAD_CHARS = 9000   # amendment operative text lives at the top; entry-into-force at the end
TAIL_CHARS = 2000

TITLE_DATE_RE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
TITLE_LAW_RE = re.compile(r"[„\"]([^“”\"]+)[“”\"]")
ACTIONS = {"amended", "added", "repealed"}
STATUSES = {"in_force", "not_yet", "unknown"}

SYSTEM_PROMPT = """You extract structured facts from Georgian amendment acts \
(acts titled "...კანონში/კოდექსში ცვლილების შეტანის შესახებ"). The text is in Georgian. \
Respond with ONLY a JSON object:

- target_law: the Georgian name of the law being amended, as printed (e.g. \
"საქართველოს საგადასახადო კოდექსი"), or null
- effective_date: ISO date "YYYY-MM-DD" when the amendment enters into force. It is \
stated near the end ("ეს კანონი ამოქმედდეს ..."). "გამოქვეყნებისთანავე" means upon \
publication — then use the publication/adoption date if printed, else null.
- articles: array of the amended law's articles this act changes, each:
  {"article": "165", "action": "amended" | "added" | "repealed",
   "summary_ru": one short Russian sentence saying what changed,
   "old_norm": short Russian summary of the previous rule or null if new/unstated,
   "new_norm": short Russian summary of the rule after the change or null if repealed}
  Articles of the AMENDED law only — numbers referenced as changes inside it \
(e.g. "კოდექსის მე-165 მუხლის პირველი ნაწილი" -> "165"). NEVER list the amendment \
act's own articles: "მუხლი 1" that introduces the changes and "მუხლი 2" / final \
provisions about entry into force ("ეს კანონი ამოქმედდეს...") are the act's own \
structure and must be excluded — use them only for effective_date. \
Limit to the 15 most substantive articles if there are more.

If something is not stated in the excerpt, use null rather than guessing."""


def parse_title(title: str):
    """Deterministic bits from the standard title format:
    'N 3728-XIIIმს-Xმპ - 16/11/2023 - „...კანონში ცვლილების შეტანის თაობაზე'."""
    number = None
    m = re.match(r"\s*N?\s*([0-9][^\s]*)", title or "")
    if m:
        number = m.group(1).strip(" -")
    adoption = None
    m = TITLE_DATE_RE.search(title or "")
    if m:
        try:
            adoption = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            adoption = None
    law_name = None
    m = TITLE_LAW_RE.search(title or "")
    if m:
        law_name = m.group(1).strip()
        # titles quote either the law itself or a nested amendment act name
        law_name = re.sub(r"\s*საქართველოს კანონში$", "", law_name).strip()
    return number, adoption, law_name


def parse_iso_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def build_excerpt(doc: Document) -> str:
    text = doc.full_text or ""
    if len(text) <= HEAD_CHARS + TAIL_CHARS:
        body = text
    else:
        body = text[:HEAD_CHARS] + "\n\n[...]\n\n" + text[-TAIL_CHARS:]
    return f"TITLE: {doc.title}\n\n{body}"


def normalize(payload: dict) -> dict:
    articles = payload.get("articles")
    if not isinstance(articles, list):
        articles = []
    cleaned = []
    for item in articles[:15]:
        if not isinstance(item, dict):
            continue
        article = str(item.get("article") or "").strip()
        if not article:
            continue
        action = str(item.get("action") or "").strip()
        cleaned.append({
            "article": article,
            "action": action if action in ACTIONS else "amended",
            "summary_ru": (str(item.get("summary_ru") or "").strip() or None),
            "old_norm": (str(item.get("old_norm") or "").strip() or None),
            "new_norm": (str(item.get("new_norm") or "").strip() or None),
        })
    return {
        "target_law_title": (str(payload.get("target_law") or "").strip() or None),
        "effective_date": parse_iso_date(payload.get("effective_date")),
        "affected_articles": cleaned,
    }


# Wrapper words that carry no identity: "საქართველოს კანონი/ორგანული კანონი"
# appears on either side of the actual name in corpus titles.
_WRAPPER_TOKENS = {"საქართველოს", "კანონი", "ორგანული"}

_law_index_cache = None


def _core_tokens(name: str):
    """Normalized identity tokens of a law name.

    Strips quote glyphs (glued to words — replaced with spaces), zero-width/BOM
    characters that occur in corpus titles, punctuation and wrapper words.
    Declension variants ("ულ"/"ული") are folded to one form.
    """
    cleaned = re.sub(r'[„“”"﻿​]', ' ', name or '')
    cleaned = re.sub(r'[.,;:]+', ' ', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip().lower()
    cleaned = re.sub(r'ულ(?= )', 'ული', cleaned)
    return frozenset(t for t in cleaned.split() if t not in _WRAPPER_TOKENS)


def _law_index(db):
    global _law_index_cache
    if _law_index_cache is None:
        rows = db.execute(sa_text("""
            SELECT id, title, length(full_text) FROM documents
            WHERE document_type = 'law' AND title NOT ILIKE '%ცვლილებ%'
        """)).all()
        _law_index_cache = [
            (row[0], _core_tokens(row[1]), row[2] or 0) for row in rows
        ]
    return _law_index_cache


def resolve_target_law(db, law_title: str):
    """Match the amended law's name to its corpus document.

    Exact core-token match wins; otherwise a one-token difference is tolerated
    when at least three tokens agree (corpus titles occasionally drop a word,
    e.g. "სხვა" in the gambling law). Ambiguous fuzzy matches are skipped.
    """
    target = _core_tokens(law_title or "")
    if not target:
        return None
    exact = [(doc_id, size) for doc_id, tokens, size in _law_index(db) if tokens == target]
    if exact:
        return max(exact, key=lambda x: x[1])[0]
    fuzzy = [
        (doc_id, size)
        for doc_id, tokens, size in _law_index(db)
        if len(tokens & target) >= 3 and len(tokens ^ target) <= 1
    ]
    if len(fuzzy) == 1:
        return fuzzy[0][0]
    if len(fuzzy) > 1:
        return max(fuzzy, key=lambda x: x[1])[0] if len({d for d, _ in fuzzy}) == 1 else None
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="max documents to process (0 = all pending)")
    parser.add_argument("--reresolve", action="store_true",
                        help="only retry target-law resolution for rows without one (no LLM)")
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine, tables=[LawAmendment.__table__])

    if args.reresolve:
        db = SessionLocal()
        try:
            rows = db.query(LawAmendment).filter(LawAmendment.target_law_doc_id.is_(None)).all()
            fixed = 0
            for row in rows:
                target_id = resolve_target_law(db, row.target_law_title or "")
                if target_id:
                    row.target_law_doc_id = target_id
                    exists = db.query(DocumentRelation.id).filter_by(
                        source_doc_id=row.amendment_doc_id, target_doc_id=target_id, relation_type="amends"
                    ).first()
                    if not exists:
                        db.add(DocumentRelation(
                            source_doc_id=row.amendment_doc_id, target_doc_id=target_id, relation_type="amends",
                        ))
                    fixed += 1
            db.commit()
            logger.info(f"Re-resolve: fixed {fixed} of {len(rows)} unresolved rows")
        finally:
            db.close()
        return

    llm = ChatOpenAI(
        model=settings.LLM_MODEL,
        temperature=0,
        max_tokens=1500,
        openai_api_key=settings.OPENAI_API_KEY,
        model_kwargs={"response_format": {"type": "json_object"}},
    )

    db = SessionLocal()
    try:
        pending_sql = """
            SELECT d.id FROM documents d
            LEFT JOIN law_amendments a ON a.amendment_doc_id = d.id
            WHERE d.document_type = 'law' AND d.title ILIKE '%ცვლილებ%' AND a.id IS NULL
            ORDER BY d.date_published DESC NULLS LAST
        """
        if args.limit:
            pending_sql += f" LIMIT {int(args.limit)}"
        pending_ids = [row[0] for row in db.execute(sa_text(pending_sql))]
        logger.info(f"Pending amendment acts: {len(pending_ids)}")

        done = failed = resolved = 0
        started = time.time()
        today = date.today()
        for doc_id in pending_ids:
            doc = db.get(Document, doc_id)
            if doc is None or not (doc.full_text or "").strip():
                continue
            try:
                number, adoption, title_law = parse_title(doc.title or "")
                reply = llm.invoke([
                    SystemMessage(content=SYSTEM_PROMPT),
                    HumanMessage(content=build_excerpt(doc)),
                ])
                payload = json.loads(reply.content)
                fields = normalize(payload)
                target_title = fields["target_law_title"] or title_law
                target_id = resolve_target_law(db, target_title)
                effective = fields["effective_date"]
                if effective:
                    status = "in_force" if effective <= today else "not_yet"
                else:
                    status = "unknown"
                db.add(LawAmendment(
                    amendment_doc_id=doc.id,
                    target_law_doc_id=target_id,
                    target_law_title=target_title,
                    adoption_date=adoption or doc.date_published,
                    effective_date=effective,
                    status=status,
                    affected_articles=fields["affected_articles"],
                    raw_json=payload,
                    model=settings.LLM_MODEL,
                    extraction_version=EXTRACTION_VERSION,
                ))
                if target_id:
                    resolved += 1
                    exists = db.query(DocumentRelation.id).filter_by(
                        source_doc_id=doc.id, target_doc_id=target_id, relation_type="amends"
                    ).first()
                    if not exists:
                        db.add(DocumentRelation(
                            source_doc_id=doc.id, target_doc_id=target_id, relation_type="amends",
                        ))
                db.commit()
                done += 1
            except Exception as e:
                db.rollback()
                failed += 1
                logger.error(f"Extraction failed for {doc.id} ({(doc.title or '')[:60]!r}): {e}")
                if failed > 50 and failed > done:
                    logger.error("Too many failures — aborting.")
                    break
            if (done + failed) % 50 == 0:
                rate = (done + failed) / max(time.time() - started, 1)
                logger.info(f"Progress: done={done} failed={failed} resolved={resolved} rate={rate:.2f}/s")

        logger.info(f"Finished. done={done} failed={failed} target_resolved={resolved} of {len(pending_ids)} pending")
    finally:
        db.close()


if __name__ == "__main__":
    main()
