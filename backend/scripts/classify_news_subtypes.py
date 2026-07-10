#!/usr/bin/env python
"""Classify documents into news subcategories (documents.subtype).

Two stages:

  1. Rules (free, bulk): ``classify_news_subtype`` from scraper/normalize.py
     over every document with ``subtype IS NULL``. Default is a dry-run that
     prints a coverage report; ``--apply`` writes with subtype_source='rule'.
  2. LLM fallback (``--llm``): for still-unclassified documents *within the
     public news scope* (species=LegislativeNews or document_type='news'),
     asks the LLM to pick one of the allowed subtypes from the title +
     original type + text head. Invalid/uncertain answers become 'general'.
     Per-document commit, so the run is resumable.

Re-running the rule stage only touches rows with ``subtype IS NULL`` or
``subtype_source='rule'`` — LLM verdicts are never overwritten by rules.

Usage (inside infohub-backend):
    python scripts/classify_news_subtypes.py                 # dry-run coverage report
    python scripts/classify_news_subtypes.py --apply         # write rule verdicts
    python scripts/classify_news_subtypes.py --llm --limit 30  # sample LLM fallback
    python scripts/classify_news_subtypes.py --llm           # full LLM fallback
"""
import argparse
import json
import logging
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text as sa_text

from core.config import settings
from core.database import SessionLocal
from scraper.normalize import NEWS_SUBTYPES, classify_news_subtype

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logger = logging.getLogger("news_subtypes")

# Documents shown on the public /news page. Deliberately species-based, NOT
# document_type='news' only: infer_document_type() reclassifies many
# LegislativeNews items into guideline/law/regulation for RAG-lane purposes,
# but they still belong on the news feed.
NEWS_SCOPE_SQL = "((metadata->>'species') = 'LegislativeNews' OR document_type = 'news')"

SYSTEM_PROMPT = """You classify publications from the Georgian Revenue Service legal info hub \
(infohub.rs.ge) into exactly one subcategory. The input gives the document title (Georgian), \
its original type label, and the beginning of its text. Respond with ONLY a JSON object \
{"subtype": "<value>"} where <value> is one of:

- "treaty": interstate/intergovernmental agreements, esp. double-taxation avoidance treaties \
(ორმაგი დაბეგვრის თავიდან აცილება, სახელმწიფოთაშორისი/მთავრობათაშორისი შეთანხმება)
- "loss_norms": industry natural-loss norm instructions (დანაკარგების ნორმები, ბუნებრივი დანაკარგები)
- "dispute_decisions": publications of dispute council or court decisions (დავების გადაწყვეტილება, \
საჯარო გადაწყვეტილება)
- "guidance": methodological instructions, situational or procedural guides (მეთოდური მითითება, \
სიტუაციური სახელმძღვანელო)
- "legislation": laws, bills, amendments to laws/codes (კანონი, კანონპროექტი, ცვლილება კანონში)
- "orders_resolutions": minister orders, government resolutions (ბრძანება, დადგენილება)
- "general": announcements, deadlines, service news, anything that fits none of the above

If unsure, answer "general" rather than guessing."""


def rule_stage(db, apply: bool) -> None:
    rows = db.execute(sa_text("""
        SELECT id, title, metadata->>'type' AS orig_type, metadata->>'species' AS species,
               CASE WHEN {scope} THEN 1 ELSE 0 END AS in_scope
        FROM documents
        WHERE subtype IS NULL OR subtype_source = 'rule'
    """.format(scope=NEWS_SCOPE_SQL))).all()

    verdicts = Counter()
    unmatched_in_scope = []
    updates = []
    for r in rows:
        subtype = classify_news_subtype(r.title or "", {"type": r.orig_type, "species": r.species})
        if subtype:
            verdicts[subtype] += 1
            updates.append({"id": r.id, "subtype": subtype})
        else:
            verdicts["(unmatched)"] += 1
            if r.in_scope:
                unmatched_in_scope.append(r.title or "")

    total = len(rows)
    matched = total - verdicts["(unmatched)"]
    print(f"\nRule stage over {total} candidate documents "
          f"(subtype NULL or rule-sourced): matched {matched} "
          f"({matched / total * 100:.1f}%)" if total else "\nNo candidate documents.")
    for subtype, n in verdicts.most_common():
        print(f"  {subtype:20s} {n}")
    print(f"\nUnmatched within news scope: {len(unmatched_in_scope)} — sample titles:")
    for title in unmatched_in_scope[:20]:
        print(f"  - {title[:110]}")

    if not apply:
        print("\nDry-run only. Re-run with --apply to write rule verdicts.")
        return
    for batch_start in range(0, len(updates), 500):
        batch = updates[batch_start:batch_start + 500]
        for u in batch:
            db.execute(sa_text(
                "UPDATE documents SET subtype = :subtype, subtype_source = 'rule' WHERE id = :id"
            ), u)
        db.commit()
    print(f"\nApplied {len(updates)} rule verdicts.")


def llm_stage(db, limit: int) -> None:
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage, SystemMessage

    llm = ChatOpenAI(
        model=settings.LLM_MODEL,
        temperature=0,
        max_tokens=50,
        openai_api_key=settings.OPENAI_API_KEY,
        model_kwargs={"response_format": {"type": "json_object"}},
    )

    pending_sql = f"""
        SELECT id, title, metadata->>'type' AS orig_type, left(full_text, 1500) AS head
        FROM documents
        WHERE subtype IS NULL AND {NEWS_SCOPE_SQL}
        ORDER BY date_published DESC NULLS LAST
    """
    if limit:
        pending_sql += f" LIMIT {int(limit)}"
    rows = db.execute(sa_text(pending_sql)).all()
    logger.info(f"LLM stage: {len(rows)} pending documents in news scope")

    done = failed = 0
    verdicts = Counter()
    started = time.time()
    for r in rows:
        try:
            reply = llm.invoke([
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=(
                    f"TITLE: {r.title}\nORIGINAL TYPE: {r.orig_type or '(none)'}\n\n{r.head or ''}"
                )),
            ])
            subtype = str(json.loads(reply.content).get("subtype") or "").strip()
            if subtype not in NEWS_SUBTYPES:
                subtype = "general"
            db.execute(sa_text(
                "UPDATE documents SET subtype = :subtype, subtype_source = 'llm' WHERE id = :id"
            ), {"id": r.id, "subtype": subtype})
            db.commit()
            verdicts[subtype] += 1
            done += 1
        except Exception as e:
            db.rollback()
            failed += 1
            logger.error(f"LLM classification failed for {r.id} ({(r.title or '')[:60]!r}): {e}")
            if failed > 50 and failed > done:
                logger.error("Too many failures — aborting.")
                break
        if (done + failed) % 50 == 0:
            rate = (done + failed) / max(time.time() - started, 1)
            logger.info(f"Progress: done={done} failed={failed} rate={rate:.2f}/s")

    logger.info(f"LLM stage finished. done={done} failed={failed}")
    for subtype, n in verdicts.most_common():
        print(f"  {subtype:20s} {n}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write rule verdicts (default: dry-run report)")
    parser.add_argument("--llm", action="store_true", help="run the LLM fallback over unclassified news-scope docs")
    parser.add_argument("--limit", type=int, default=0, help="max documents for the LLM stage (0 = all pending)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.llm:
            llm_stage(db, args.limit)
        else:
            rule_stage(db, args.apply)
    finally:
        db.close()


if __name__ == "__main__":
    main()
