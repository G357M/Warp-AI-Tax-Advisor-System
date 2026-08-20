#!/usr/bin/env python
"""Link dispute decisions of the same case into appeal chains (decision_links).

Deterministic and conservative: an edge is created only when a reference match
is unambiguous. Two methods, in priority order:

  1. prior_ref     — decision A explicitly cites decision B's number among its
                     reviewed lower-instance decisions (extraction v2 field
                     ``prior_refs``). Confidence 0.9 (0.95 when the cited date
                     also matches B's decision_date).
  2. case_number   — A and B share a normalized case number (>= 6 chars) and
                     A sits one-or-more ranks above B. Confidence 0.7.

Both methods additionally require rank(A.body) > rank(B.body), B's date not
after A's when both are known, and exactly ONE candidate B — any ambiguity
skips the edge. ``other`` bodies never link.

Rebuilds from scratch: --apply DELETEs all rows and re-inserts. The default
dry run prints the report without touching the table.

Usage (inside infohub-backend):
    python scripts/link_decision_chains.py --summary-only  # aggregate dry-run
    python scripts/link_decision_chains.py                 # dry-run with samples
    python scripts/link_decision_chains.py --apply         # rebuild decision_links
"""
import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text as sa_text

from core.database import SessionLocal, Base, engine
from models.document import DecisionLink

BODY_RANK = {
    "revenue_service_council": 1,
    "mof_dispute_council": 2,
    "city_court": 3,
    "appeals_court": 4,
    "supreme_court": 5,
}

MIN_CASE_NUMBER_LEN = 6


def norm_number(value) -> str:
    """Normalize a decision/case number for matching: strip whitespace and
    number-sign prefixes, keep only digits, slashes and dashes."""
    s = str(value or "").strip()
    s = re.sub(r"^[№N#\s]+", "", s, flags=re.IGNORECASE)
    return re.sub(r"[^0-9/\-]", "", s)


def emit_report(facts, edges, skipped_ambiguous: int, *, summary_only: bool) -> None:
    """Print aggregate link counts and, only when requested, public samples."""
    facts_by_id = {fact["id"]: fact for fact in facts}
    by_method = defaultdict(int)
    by_transition = defaultdict(int)
    for (from_id, to_id), (method, _confidence) in edges.items():
        by_method[method] += 1
        higher, lower = facts_by_id[from_id], facts_by_id[to_id]
        by_transition[(lower["body"], higher["body"])] += 1

    print(f"Facts considered: {len(facts)}")
    print(f"Links found: {len(edges)} (ambiguous skips: {skipped_ambiguous})")
    for method, count in sorted(by_method.items()):
        print(f"  method {method}: {count}")
    for (lower_body, higher_body), count in sorted(
        by_transition.items(), key=lambda item: -item[1]
    ):
        print(f"  {lower_body} -> {higher_body}: {count}")

    if summary_only:
        return
    print("\nSample linked pairs:")
    for (from_id, to_id), (method, confidence) in list(edges.items())[:10]:
        higher, lower = facts_by_id[from_id], facts_by_id[to_id]
        print(
            f"  [{method} {confidence}] {lower['body']} {lower['number']} "
            f"({lower['date']}) -> {higher['body']} {higher['number']} "
            f"({higher['date']}) | {higher['title'][:60]}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="rebuild decision_links (default: dry-run report)")
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="omit decision numbers, dates and titles from the report",
    )
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine, tables=[DecisionLink.__table__])

    db = SessionLocal()
    try:
        rows = db.execute(sa_text("""
            SELECT f.id::text, f.authority_body, f.decision_number, f.decision_date,
                   f.case_number, f.prior_refs, f.in_favor, d.title
            FROM decision_facts f
            JOIN documents d ON d.id = f.document_id
            WHERE f.authority_body IS NOT NULL AND f.authority_body != 'other'
        """)).all()

        facts = []
        by_number = defaultdict(list)   # (body, norm_number) -> facts
        by_case = defaultdict(list)     # norm_case -> facts
        for r in rows:
            rank = BODY_RANK.get(r.authority_body)
            if rank is None:
                continue
            fact = {
                "id": r[0],
                "body": r.authority_body,
                "rank": rank,
                "number": norm_number(r.decision_number),
                "date": r.decision_date,
                "case": norm_number(r.case_number),
                "prior_refs": r.prior_refs or [],
                "in_favor": r.in_favor,
                "title": r.title or "",
            }
            facts.append(fact)
            if fact["number"]:
                by_number[(fact["body"], fact["number"])].append(fact)
            if len(fact["case"]) >= MIN_CASE_NUMBER_LEN:
                by_case[fact["case"]].append(fact)

        edges = {}  # (from_id, to_id) -> (method, confidence)
        skipped_ambiguous = 0

        def candidates_by_number(number: str, ref_body):
            """All facts whose decision_number matches, optionally narrowed to a body."""
            if ref_body:
                return list(by_number.get((ref_body, number), []))
            found = []
            for (body, num), fs in by_number.items():
                if num == number:
                    found.extend(fs)
            return found

        # Method 1: explicit prior references (extraction v2).
        for a in facts:
            for ref in a["prior_refs"]:
                number = norm_number(ref.get("number") if isinstance(ref, dict) else None)
                if not number:
                    continue
                ref_body = ref.get("body") if isinstance(ref, dict) else None
                ref_date = str(ref.get("date") or "") if isinstance(ref, dict) else ""
                cands = [
                    b for b in candidates_by_number(number, ref_body)
                    if b["rank"] < a["rank"]
                    and not (a["date"] and b["date"] and b["date"] > a["date"])
                ]
                if len(cands) != 1:
                    skipped_ambiguous += len(cands) > 1
                    continue
                b = cands[0]
                confidence = 0.95 if (ref_date and b["date"] and ref_date == b["date"].isoformat()) else 0.9
                edges[(a["id"], b["id"])] = ("prior_ref", confidence)

        # Method 2: shared case number, adjacent-or-lower rank, unique candidate.
        for case, group in by_case.items():
            if len(group) < 2:
                continue
            for a in group:
                lower = [
                    b for b in group
                    if b["rank"] < a["rank"]
                    and not (a["date"] and b["date"] and b["date"] > a["date"])
                ]
                if not lower:
                    continue
                # link to the nearest lower instance; skip if that rank is ambiguous
                top_rank = max(b["rank"] for b in lower)
                nearest = [b for b in lower if b["rank"] == top_rank]
                if len(nearest) != 1:
                    skipped_ambiguous += 1
                    continue
                b = nearest[0]
                edges.setdefault((a["id"], b["id"]), ("case_number", 0.7))

        # ---- report ----------------------------------------------------------
        emit_report(
            facts,
            edges,
            skipped_ambiguous,
            summary_only=args.summary_only,
        )

        if not args.apply:
            print("\nDry-run only. Re-run with --apply to rebuild decision_links.")
            return

        db.execute(sa_text("DELETE FROM decision_links"))
        for (from_id, to_id), (method, confidence) in edges.items():
            db.execute(sa_text("""
                INSERT INTO decision_links (id, from_facts_id, to_facts_id, method, confidence, created_at)
                VALUES (gen_random_uuid(), :from_id, :to_id, :method, :confidence, now())
            """), {"from_id": from_id, "to_id": to_id, "method": method, "confidence": confidence})
        db.commit()
        print(f"\nRebuilt decision_links: {len(edges)} rows.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
