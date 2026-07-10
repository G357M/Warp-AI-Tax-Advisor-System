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
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import text as sa_text

from core.config import settings
from core.database import SessionLocal, Base, engine
from models.document import Document, DecisionFacts

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logger = logging.getLogger("decision_facts")

EXTRACTION_VERSION = 2
# References to the appealed lower-instance decision sit in the narrative
# header, so v2 reads a longer head than v1 did.
HEAD_CHARS = 4000
TAIL_CHARS = 5000

AUTHORITY_BODIES = {"revenue_service_council", "mof_dispute_council", "city_court", "appeals_court", "supreme_court", "other"}
DISPUTE_TYPES = {"tax", "customs", "both", "other"}
OUTCOMES = {"satisfied", "partially_satisfied", "rejected", "unclear"}
IN_FAVOR = {"taxpayer", "authority", "partial", "unclear"}

SYSTEM_PROMPT = """You extract structured facts from Georgian tax/customs dispute decisions \
(Revenue Service dispute council, Ministry of Finance dispute council, courts). \
The decision text is in Georgian. Respond with ONLY a JSON object, no prose, with these keys:

- authority_body: one of "revenue_service_council" (შემოსავლების სამსახურის დავების საბჭო), \
"mof_dispute_council" (ფინანსთა სამინისტროს დავების განხილვის საბჭო), "city_court" (საქალაქო სასამართლო), \
"appeals_court" (სააპელაციო სასამართლო), "supreme_court" (უზენაესი სასამართლო), "other"
- decision_number: the decision number as printed (e.g. "26773/2/2026"), or null
- decision_date: ISO date "YYYY-MM-DD" of the decision, or null
- dispute_type: "tax", "customs", "both" or "other"
- contested_articles: array of Georgian Tax Code article numbers explicitly at issue \
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
- prior_decisions: array of {"number": "...", "body": <same enum as authority_body or null>, \
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


def parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def normalize(payload: dict) -> dict:
    def pick(value, allowed, default="unclear"):
        value = str(value or "").strip()
        return value if value in allowed else default

    articles = payload.get("contested_articles")
    if not isinstance(articles, list):
        articles = []
    articles = [str(a).strip() for a in articles if str(a).strip()][:20]

    amount = payload.get("amount_gel")
    try:
        amount = float(amount) if amount is not None else None
    except (TypeError, ValueError):
        amount = None

    prior_refs = []
    raw_priors = payload.get("prior_decisions")
    if isinstance(raw_priors, list):
        for ref in raw_priors[:10]:
            if not isinstance(ref, dict):
                continue
            number = str(ref.get("number") or "").strip()
            if not number:
                continue
            ref_body = str(ref.get("body") or "").strip()
            ref_date = parse_date(ref.get("date"))
            prior_refs.append({
                "number": number,
                "body": ref_body if ref_body in AUTHORITY_BODIES else None,
                "date": ref_date.isoformat() if ref_date else None,
            })

    return {
        "case_number": (str(payload.get("case_number") or "").strip() or None),
        "prior_refs": prior_refs,
        "prior_body": prior_refs[0]["body"] if prior_refs else None,
        "authority_body": pick(payload.get("authority_body"), AUTHORITY_BODIES, "other"),
        "decision_number": (str(payload.get("decision_number") or "").strip() or None),
        "decision_date": parse_date(payload.get("decision_date")),
        "dispute_type": pick(payload.get("dispute_type"), DISPUTE_TYPES, "other"),
        "contested_articles": articles,
        "amount_gel": amount,
        "outcome": pick(payload.get("outcome"), OUTCOMES),
        "in_favor": pick(payload.get("in_favor"), IN_FAVOR),
    }


def extract_one(llm: ChatOpenAI, doc: Document) -> dict:
    reply = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=build_excerpt(doc)),
    ])
    payload = json.loads(reply.content)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="max documents to process (0 = all pending)")
    parser.add_argument("--new-only", action="store_true",
                        help="only documents without a facts row (nightly cron; skips the v1->v2 upgrade backlog)")
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine, tables=[DecisionFacts.__table__])

    llm = ChatOpenAI(
        model=settings.LLM_MODEL,
        temperature=0,
        max_tokens=800,
        openai_api_key=settings.OPENAI_API_KEY,
        model_kwargs={"response_format": {"type": "json_object"}},
    )

    db = SessionLocal()
    try:
        if args.new_only:
            facts_condition = "f.id IS NULL"
        else:
            facts_condition = f"(f.id IS NULL OR f.extraction_version < {int(EXTRACTION_VERSION)})"
        pending_sql = f"""
            SELECT d.id FROM documents d
            LEFT JOIN decision_facts f ON f.document_id = d.id
            WHERE d.document_type = 'court_decision' AND {facts_condition}
              AND (d.metadata->>'kind') IS DISTINCT FROM 'digest'
            ORDER BY d.date_published DESC NULLS LAST
        """
        if args.limit:
            pending_sql += f" LIMIT {int(args.limit)}"
        pending_ids = [row[0] for row in db.execute(sa_text(pending_sql))]
        logger.info(f"Pending decisions: {len(pending_ids)}")

        done = failed = 0
        started = time.time()
        for doc_id in pending_ids:
            doc = db.get(Document, doc_id)
            if doc is None or not (doc.full_text or "").strip():
                continue
            try:
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

        logger.info(f"Finished. done={done} failed={failed} of {len(pending_ids)} pending")
    finally:
        db.close()


if __name__ == "__main__":
    main()
