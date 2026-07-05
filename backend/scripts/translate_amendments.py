#!/usr/bin/env python
"""Translate amendment article summaries (Было/Стало) into Georgian and English.

Extraction produces Russian summaries; this fills law_amendments.articles_i18n
with {"ka": [...], "en": [...]} arrays mirroring affected_articles so the
timeline reads natively in every site language. Incremental: only rows with
articles and no translations yet.

Usage (inside infohub-backend):
    python scripts/translate_amendments.py --limit 30   # probe
    python scripts/translate_amendments.py              # full / nightly
"""
import argparse
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import text as sa_text

from core.config import settings
from core.database import SessionLocal, engine
from models.document import LawAmendment

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logger = logging.getLogger("translate_amendments")

SYSTEM_PROMPT = """You translate short Russian legal summaries about Georgian tax-law \
amendments into Georgian and English. Input: a JSON array of items \
{"summary_ru": ..., "old_norm": ..., "new_norm": ...} (fields may be null). \
Respond with ONLY a JSON object:
{"ka": [{"summary": ..., "old_norm": ..., "new_norm": ...}, ...],
 "en": [{"summary": ..., "old_norm": ..., "new_norm": ...}, ...]}
Both arrays must have exactly the same length and order as the input; translate \
null as null. Keep legal terminology natural for each language."""


def ensure_column() -> None:
    with engine.begin() as conn:
        conn.execute(sa_text(
            "ALTER TABLE law_amendments ADD COLUMN IF NOT EXISTS articles_i18n JSON"
        ))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="max rows (0 = all pending)")
    args = parser.parse_args()

    ensure_column()

    llm = ChatOpenAI(
        model=settings.LLM_MODEL,
        temperature=0,
        max_tokens=2500,
        openai_api_key=settings.OPENAI_API_KEY,
        model_kwargs={"response_format": {"type": "json_object"}},
    )

    db = SessionLocal()
    try:
        pending_sql = """
            SELECT id FROM law_amendments
            WHERE articles_i18n IS NULL
              AND affected_articles IS NOT NULL
              AND affected_articles::text NOT IN ('[]', 'null')
            ORDER BY adoption_date DESC NULLS LAST
        """
        if args.limit:
            pending_sql += f" LIMIT {int(args.limit)}"
        pending_ids = [row[0] for row in db.execute(sa_text(pending_sql))]
        logger.info(f"Pending translations: {len(pending_ids)}")

        done = failed = 0
        started = time.time()
        for row_id in pending_ids:
            row = db.get(LawAmendment, row_id)
            if row is None:
                continue
            articles = row.affected_articles or []
            if isinstance(articles, str):
                articles = json.loads(articles)
            payload_in = [
                {
                    "summary_ru": a.get("summary_ru"),
                    "old_norm": a.get("old_norm"),
                    "new_norm": a.get("new_norm"),
                }
                for a in articles
            ]
            try:
                reply = llm.invoke([
                    SystemMessage(content=SYSTEM_PROMPT),
                    HumanMessage(content=json.dumps(payload_in, ensure_ascii=False)),
                ])
                data = json.loads(reply.content)
                ka, en = data.get("ka"), data.get("en")
                if not (isinstance(ka, list) and isinstance(en, list)
                        and len(ka) == len(articles) and len(en) == len(articles)):
                    raise ValueError(f"shape mismatch: ka={len(ka or [])} en={len(en or [])} vs {len(articles)}")
                row.articles_i18n = {"ka": ka, "en": en}
                db.commit()
                done += 1
            except Exception as e:
                db.rollback()
                failed += 1
                logger.error(f"Translation failed for {row_id}: {e}")
                if failed > 50 and failed > done:
                    logger.error("Too many failures — aborting.")
                    break
            if (done + failed) % 50 == 0:
                rate = (done + failed) / max(time.time() - started, 1)
                logger.info(f"Progress: done={done} failed={failed} rate={rate:.2f}/s")

        logger.info(f"Finished. done={done} failed={failed} of {len(pending_ids)} pending")
    finally:
        db.close()


if __name__ == "__main__":
    main()
