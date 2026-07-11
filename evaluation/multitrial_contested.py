#!/usr/bin/env python3
"""Multi-trial pass-rate test for the contested questions (П0.3).

Single eval runs are not a reliable go/no-go signal (Phase B, 2026-07-03:
the full eval varies 37-40/40 on unchanged code). This runs each contested
question N times through the REAL entry point (maybe_run_live_rollout with
v1 fallback — never a hand-built prompt) and reports per-question pass rates.

With the persistent translation cache (П0.1) an in-process loop now matches
prod behavior. For the old fresh-process rigor (cold caches each trial), run
this with --trials 1 in a shell loop of separate `docker exec` calls instead.

Usage (inside infohub-backend, file copied next to eval_harness.py):
    python /tmp/multitrial_contested.py                 # contested set, 10 trials each
    python /tmp/multitrial_contested.py --trials 5
    python /tmp/multitrial_contested.py --qid pit_rate,micro
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, str(Path(__file__).parent))

from eval_harness import QUESTIONS, answer, norm  # noqa: E402

# The questions that historically flip between runs + Phase B regression victims.
CONTESTED = [
    "pit_rate", "pit_rate_en", "profit_rate_en", "vat_rate_more",
    "dividend", "sb_threshold", "art_lookup", "micro",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=10)
    parser.add_argument("--qid", default=",".join(CONTESTED),
                        help="comma-separated question ids from eval_harness.QUESTIONS")
    args = parser.parse_args()

    wanted = [q.strip() for q in args.qid.split(",") if q.strip()]
    questions = [q for q in QUESTIONS if q[0] in wanted]
    missing = set(wanted) - {q[0] for q in questions}
    if missing:
        print(f"Unknown qids: {sorted(missing)}", file=sys.stderr)
        sys.exit(2)

    out = {"started": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
           "trials": args.trials, "results": {}}
    worst = 1.0
    for qid, _cat, lang, query, kind, must, must_not, _ground in questions:
        passes = 0
        failures = []
        for trial in range(args.trials):
            res = answer(query, lang)
            nresp = norm(res.get("response", ""))
            ok = all(norm(m) in nresp for m in must) and not any(norm(x) in nresp for x in must_not)
            passes += ok
            if not ok and len(failures) < 3:
                failures.append(res.get("response", "")[:200])
        rate = passes / args.trials
        worst = min(worst, rate)
        out["results"][qid] = {"passes": passes, "trials": args.trials,
                               "rate": rate, "sample_failures": failures}
        print(f"[{qid}] {passes}/{args.trials}", file=sys.stderr)

    print(json.dumps(out, ensure_ascii=False))
    print(f"WORST: {worst:.0%}", file=sys.stderr)


if __name__ == "__main__":
    main()
