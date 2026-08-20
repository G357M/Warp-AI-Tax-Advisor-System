#!/usr/bin/env python
"""Repair only deterministic decision-fact normalization defects.

The default is a read-only report. ``--apply`` requires the exact number of
rows printed by the dry run, preventing a stale or unexpectedly broad update.
The original LLM payload in ``raw_json`` is never changed, so every repair
remains auditable and recoverable.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import SessionLocal  # noqa: E402
from decision_fact_contract import (  # noqa: E402
    clean_amount,
    clean_article_refs,
    clean_prior_refs,
)
from models.document import DecisionFacts  # noqa: E402
from sqlalchemy.orm import load_only  # noqa: E402


def normalized_changes(row: Any) -> dict[str, Any]:
    """Return only unambiguous field changes for one existing facts row."""
    changes: dict[str, Any] = {}
    amount = clean_amount(row.amount_gel)
    if amount != row.amount_gel:
        changes["amount_gel"] = amount

    articles = clean_article_refs(row.contested_articles)
    if articles != (row.contested_articles or []):
        changes["contested_articles"] = articles

    prior_refs = clean_prior_refs(
        row.prior_refs, own_decision_number=row.decision_number
    )
    if prior_refs != (row.prior_refs or []):
        changes["prior_refs"] = prior_refs
    prior_body = prior_refs[0]["body"] if prior_refs else None
    if prior_body != row.prior_body:
        changes["prior_body"] = prior_body
    return changes


def scan(db: Any) -> tuple[list[tuple[Any, dict[str, Any]]], dict[str, int]]:
    rows = (
        db.query(DecisionFacts)
        .options(
            load_only(
                DecisionFacts.id,
                DecisionFacts.amount_gel,
                DecisionFacts.contested_articles,
                DecisionFacts.decision_number,
                DecisionFacts.prior_refs,
                DecisionFacts.prior_body,
            )
        )
        .order_by(DecisionFacts.id)
        .all()
    )
    pending: list[tuple[Any, dict[str, Any]]] = []
    field_counts = {
        "amount_gel": 0,
        "contested_articles": 0,
        "prior_refs": 0,
        "prior_body": 0,
    }
    for row in rows:
        changes = normalized_changes(row)
        if not changes:
            continue
        pending.append((row, changes))
        for field in changes:
            field_counts[field] += 1
    return pending, {"rows_scanned": len(rows), "rows_changed": len(pending), **field_counts}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-changed-rows", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.apply and args.expected_changed_rows is None:
        parser.error("--apply requires --expected-changed-rows from a fresh dry run")

    db = SessionLocal()
    try:
        pending, report = scan(db)
        report["mode"] = "apply" if args.apply else "dry_run"
        if args.apply:
            if len(pending) != args.expected_changed_rows:
                raise RuntimeError(
                    "normalization repair scope changed: "
                    f"expected {args.expected_changed_rows}, found {len(pending)}"
                )
            for row, changes in pending:
                for field, value in changes.items():
                    setattr(row, field, value)
            db.flush()
            remaining, _ = scan(db)
            report["remaining_changed_rows"] = len(remaining)
            if remaining:
                db.rollback()
                raise RuntimeError(
                    f"normalization verification failed: {len(remaining)} rows remain"
                )
            db.commit()
        else:
            db.rollback()

        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        print("DECISION_FACT_NORMALIZATION=" + json.dumps(report, sort_keys=True))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
