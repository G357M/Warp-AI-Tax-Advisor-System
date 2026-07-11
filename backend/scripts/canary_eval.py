#!/usr/bin/env python
"""Nightly RAG canary (П0.4): 10 known-answer questions through the real pipeline.

Catches silent RAG regressions between working sessions: corpus drift after the
nightly scrape, dependency updates, accidental config changes. The set covers
the historically flaky questions plus one per authoritative guard topic.

Prints one machine-parsable line: ``CANARY: <passed>/<total> failed=<ids>``
and exits 0 when passed, 1 when below threshold (total - allowed_failures).
A single failure is tolerated by default — generation still samples at
temperature 0.3, one flake a night is noise, two is a signal.

Usage (inside infohub-backend):
    python /app/scripts/canary_eval.py
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

ALLOWED_FAILURES = 1

# (id, lang, query, must, must_not) — kept in sync with evaluation/eval_harness.py.
QUESTIONS = [
    # historically flaky
    ("pit_rate", "ru", "Какая ставка подоходного налога с зарплаты в Грузии?", ["20"], []),
    ("vat_rate_more", "ru", "Сколько процентов НДС в Грузии?", ["18"], []),
    ("dividend", "ru", "Какой налог на дивиденды для физлица в Грузии?", ["5"], []),
    ("sb_threshold", "ru", "До какого оборота действует ставка 1% для малого бизнеса?", ["500000"], []),
    ("micro", "ru", "Что такое микробизнес в Грузии и какой налог?", ["0", "30000"], []),
    # one per authoritative guard topic
    ("vat_threshold", "ru", "С какого оборота нужно регистрироваться плательщиком НДС?", ["100000"], []),
    ("estonian", "ru", "Как работает эстонская модель налога на прибыль в Грузии?", ["распредел"], []),
    ("pension", "ru", "Как работают пенсионные взносы в Грузии?", ["2"], []),
    ("property", "ru", "Какая ставка налога на имущество в Грузии?", ["1"], []),
    ("vat_touroperator", "ru", "Облагается ли НДС организованный въезд иностранных туристов туроператором?", ["освобожд"], ["18%"]),
]


def norm(text: str) -> str:
    t = (text or "").lower()
    t = re.sub(r"(?<=\d)[\s,  ]+(?=\d)", "", t)
    return re.sub(r"\s+", " ", t).strip()


def main() -> None:
    from rag.pipeline import rag_pipeline
    from rag_v2.live_runtime import maybe_run_live_rollout

    failed = []
    for qid, lang, query, must, must_not in QUESTIONS:
        try:
            res = maybe_run_live_rollout(query=query, language=lang)
            if res is None:
                res = rag_pipeline.process_query(query=query, conversation_history=None, language=lang)
            nresp = norm(res.get("response", ""))
            ok = all(norm(m) in nresp for m in must) and not any(norm(x) in nresp for x in must_not)
        except Exception as e:
            print(f"[{qid}] ERROR: {e}", file=sys.stderr)
            ok = False
        if not ok:
            failed.append(qid)
        print(f"[{qid}] {'ok' if ok else 'FAIL'}", file=sys.stderr)

    passed = len(QUESTIONS) - len(failed)
    print(f"CANARY: {passed}/{len(QUESTIONS)} failed={','.join(failed) or '-'}")
    sys.exit(0 if len(failed) <= ALLOWED_FAILURES else 1)


if __name__ == "__main__":
    main()
