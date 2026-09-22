"""Three synthetic requests through the runtime adapter; no DB or visitor data."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rag_v2.jev_router import JevOptions, JevRouter, MODEL
from rag_v2.query_classifier import classify_query
from rag_v2.query_parser import parse_query


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    key = os.environ.get("TYPESAFE_API_KEY", "")
    if not key.strip():
        print(json.dumps({"status": "missing_key"}))
        return 2
    if args.output and args.output.exists():
        parser.error("Refusing to overwrite existing evidence; choose a new output path.")
    samples = {
        "ru": "Найди судебную практику: по каким причинам суды отменяли доначисление НДС?",
        "en": "Find court precedents where judges overturned an additional VAT assessment and explain their reasoning.",
        "ka": "მომიძებნე სასამართლო პრაქტიკა, სადაც სასამართლომ დღგ-ის დამატებითი დარიცხვა გააუქმა.",
    }
    router = JevRouter()
    options = JevOptions(mode="assist", api_key=key, timeout=2)
    rows = []
    for language, query in samples.items():
        parsed = parse_query(query, language)
        baseline = classify_query(parsed)
        start = time.monotonic()
        decision = router.decide(parsed, baseline, options)
        rows.append({"language": language, "status": decision.status,
                     "baseline": baseline.question_class, "selected": decision.classification.question_class,
                     "confidence": decision.classification.confidence,
                     "elapsed_seconds": round(time.monotonic() - start, 3),
                     "passed": decision.status == "applied" and decision.classification.question_class == "dispute_practice"})
        if decision.status in {"provider_error", "cooldown", "missing_key"}:
            break
    evidence = {"model": MODEL, "synthetic_only": True, "live_rag_answer_tested": False,
                "passed": len(rows) == 3 and all(row["passed"] for row in rows), "results": rows}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if evidence["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
