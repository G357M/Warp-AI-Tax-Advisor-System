#!/usr/bin/env python
"""Extract structured facts from dispute/court decisions into decision_facts.

For every ``document_type='court_decision'`` document without a decision_facts
row, sends the decision header + operative part to the LLM (strict JSON) and
stores: deciding body, decision number/date, dispute type, contested Tax Code
articles, disputed amount, outcome and prevailing party.

Incremental and resumable: documents already extracted at the current
EXTRACTION_VERSION are skipped. Rows extracted at an older version are
re-extracted and UPDATEd in place (the previous raw payload is preserved
inside the new raw_json as ``raw_json_v1``).

v2 additionally extracts the internal case number and explicit references to
the lower-instance decisions being reviewed (``prior_refs``) — the raw
material for appeal-chain statistics (scripts/link_decision_chains.py).

Usage (inside infohub-backend):
    python scripts/extract_decision_facts.py --limit 50   # sample run
    python scripts/extract_decision_facts.py              # full backfill (incl. v1->v2 upgrade)
    python scripts/extract_decision_facts.py --new-only   # nightly: only documents with no facts row
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
from core.database import SessionLocal, Base, engine
from decision_fact_contract import EXTRACTION_VERSION, normalize
from models.document import Document, DecisionFacts

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logger = logging.getLogger("decision_facts")

# References to the appealed lower-instance decision sit in the narrative
# header, so v2 reads a longer head than v1 did.
HEAD_CHARS = 4000
TAIL_CHARS = 5000
# The v2 schema can legitimately contain several article and prior-decision
# references. 800 tokens truncated real production JSON before it could be
# parsed, so keep an explicit, tested ceiling with enough room for the bounded
# arrays below.
MAX_OUTPUT_TOKENS = 1600

SYSTEM_PROMPT = """You extract structured facts from Georgian tax/customs dispute decisions \
(Revenue Service dispute council, Ministry of Finance dispute council, courts). \
The decision text is in Georgian. Respond with ONLY a JSON object, no prose, with these keys:

- authority_body: one of "revenue_service_council" (შემოსავლების სამსახურის დავების საბჭო), \
"mof_dispute_council" (ფინანსთა სამინისტროს დავების განხილვის საბჭო), "city_court" (საქალაქო სასამართლო), \
"appeals_court" (სააპელაციო სასამართლო), "supreme_court" (უზენაესი სასამართლო), "other"
- decision_number: the decision number as printed (e.g. "26773/2/2026"), or null
- decision_date: ISO date "YYYY-MM-DD" of the decision, or null
- dispute_type: "tax", "customs", "both" or "other"
- contested_articles: array of at most 20 Georgian Tax Code article numbers explicitly at issue \
(as strings, e.g. ["275", "286"]); [] if none stated. Procedural citations that merely \
authorize the ruling (e.g. article 304 as the legal basis of the resolution) do NOT count.
- amount_gel: the disputed amount in GEL as a number, or null if not stated
- outcome: how the complaint (საჩივარი) was resolved in the operative part ("გადაწყვიტა"): \
"satisfied" (დაკმაყოფილდეს), "partially_satisfied" (ნაწილობრივ დაკმაყოფილდეს, or satisfied on some \
points / sent back for re-examination on others), "rejected" (არ დაკმაყოფილდეს), "unclear"
- in_favor: who effectively prevailed: "taxpayer", "authority", "partial", "unclear". \
Note: complaints are filed by taxpayers, so rejected complaint => authority prevailed.

- case_number: the internal case/complaint number if printed and distinct from decision_number \
(e.g. the საჩივარი registration number), or null
- prior_decisions: array of at most 10 {"number": "...", "body": <same enum as authority_body or null>, \
"date": "YYYY-MM-DD" or null} — ONLY decisions/orders of a LOWER instance that THIS decision \
reviews (the contested Revenue Service order, the council decision being appealed). Include only \
explicit numbered references; [] if none. Never include this decision's own number.

If the operative part is missing from the excerpt, use "unclear" rather than guessing."""


def build_excerpt(doc: Document) -> str:
    text = doc.full_text or ""
    if len(text) <= HEAD_CHARS + TAIL_CHARS:
        body = text
    else:
        body = text[:HEAD_CHARS] + "\n\n[...]\n\n" + text[-TAIL_CHARS:]
    return f"TITLE: {doc.title}\n\n{body}"


def extract_one(llm: ChatOpenAI, doc: Document) -> dict:
    reply = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=build_excerpt(doc)),
    ])
    payload = json.loads(reply.content)
    return payload


def build_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.LLM_MODEL,
        temperature=0,
        max_tokens=MAX_OUTPUT_TOKENS,
        openai_api_key=settings.OPENAI_API_KEY,
        model_kwargs={"response_format": {"type": "json_object"}},
    )


def pending_document_ids(db, *, new_only: bool, limit: int) -> list:
    if new_only:
        facts_condition = "f.id IS NULL"
    else:
        facts_condition = (
            f"(f.id IS NULL OR f.extraction_version < {int(EXTRACTION_VERSION)})"
        )
    pending_sql = f"""
        SELECT d.id FROM documents d
        LEFT JOIN decision_facts f ON f.document_id = d.id
        WHERE d.document_type = 'court_decision' AND {facts_condition}
          AND (d.metadata->>'kind') IS DISTINCT FROM 'digest'
        ORDER BY d.date_published DESC NULLS LAST
    """
    if limit:
        pending_sql += f" LIMIT {int(limit)}"
    return [row[0] for row in db.execute(sa_text(pending_sql))]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="max documents to process (0 = all pending)")
    parser.add_argument("--new-only", action="store_true",
                        help="only documents without a facts row (nightly cron; skips the v1->v2 upgrade backlog)")
    parser.add_argument(
        "--check-pending",
        action="store_true",
        help="report pending count without table creation, LLM initialization or writes",
    )
    parser.add_argument(
        "--max-llm-calls",
        type=int,
        default=0,
        help="optional hard ceiling for this run (0 keeps the existing nightly behavior)",
    )
    args = parser.parse_args()
    if args.limit < 0 or args.max_llm_calls < 0:
        parser.error("--limit and --max-llm-calls cannot be negative")
    if not args.check_pending:
        Base.metadata.create_all(bind=engine, tables=[DecisionFacts.__table__])

    db = SessionLocal()
    try:
        pending_ids = pending_document_ids(
            db, new_only=args.new_only, limit=args.limit
        )
        logger.info(f"Pending decisions: {len(pending_ids)}")
        if args.check_pending:
            print(
                "DECISION_FACTS_PENDING="
                + json.dumps(
                    {
                        "pending": len(pending_ids),
                        "new_only": args.new_only,
                        "limit": args.limit,
                        "llm_calls": 0,
                        "writes": False,
                    },
                    sort_keys=True,
                )
            )
            return
        if args.max_llm_calls and len(pending_ids) > args.max_llm_calls:
            raise RuntimeError(
                f"pending scope {len(pending_ids)} exceeds --max-llm-calls "
                f"{args.max_llm_calls}"
            )
        if not pending_ids:
            return

        llm = build_llm()

        done = failed = llm_calls = 0
        started = time.time()
        for doc_id in pending_ids:
            doc = db.get(Document, doc_id)
            if doc is None or not (doc.full_text or "").strip():
                continue
            try:
                if args.max_llm_calls and llm_calls >= args.max_llm_calls:
                    raise RuntimeError("LLM call ceiling reached before extraction")
                llm_calls += 1
                payload = extract_one(llm, doc)
                fields = normalize(payload)
                existing = db.query(DecisionFacts).filter_by(document_id=doc.id).one_or_none()
                if existing is not None:
                    # v1 -> v2 upgrade: keep the previous payload recoverable.
                    if existing.extraction_version < EXTRACTION_VERSION and existing.raw_json:
                        payload["raw_json_v1"] = existing.raw_json
                    for key, value in fields.items():
                        setattr(existing, key, value)
                    existing.raw_json = payload
                    existing.model = settings.LLM_MODEL
                    existing.extraction_version = EXTRACTION_VERSION
                else:
                    db.add(DecisionFacts(
                        document_id=doc.id,
                        raw_json=payload,
                        model=settings.LLM_MODEL,
                        extraction_version=EXTRACTION_VERSION,
                        **fields,
                    ))
                db.commit()
                done += 1
            except Exception as e:
                db.rollback()
                failed += 1
                logger.error(f"Extraction failed for {doc.id} ({doc.title[:60]!r}): {e}")
                if failed > 50 and failed > done:
                    logger.error("Too many failures — aborting.")
                    break
            if (done + failed) % 50 == 0:
                rate = (done + failed) / max(time.time() - started, 1)
                logger.info(f"Progress: done={done} failed={failed} rate={rate:.2f}/s")

        logger.info(
            f"Finished. done={done} failed={failed} llm_calls={llm_calls} "
            f"of {len(pending_ids)} pending"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
