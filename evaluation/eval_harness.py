#!/usr/bin/env python3
"""InfoHub RAG regression harness (Phase 0 of the grounding plan).

Runs IN the backend container so it can replicate the public route exactly
(v2 rollout -> v1 fallback) AND inspect the chunks retrieval actually returns,
which the public API does not expose. For every question it records three
independent signals:

  correct  - the answer contains the expected facts (and none of the forbidden ones)
  sourced  - the answer carries at least one source
  grounded - the expected fact is present in the text of a retrieved law chunk
             (i.e. the answer COULD be supported by the corpus, not just by the LLM)

Usage (inside infohub-backend):
    python /tmp/eval_harness.py            # full run -> JSON on stdout + summary on stderr
    python /tmp/eval_harness.py --quiet    # summary only
"""
from __future__ import annotations

import json
import re
import sys
import time

sys.path.insert(0, "/app")

from rag.pipeline import rag_pipeline          # noqa: E402
from rag_v2.live_runtime import maybe_run_live_rollout  # noqa: E402


def norm(text: str) -> str:
    """Lowercase, drop separators inside numbers and collapse whitespace for matching."""
    t = (text or "").lower()
    t = re.sub(r"(?<=\d)[\s,  ]+(?=\d)", "", t)   # "100 000" / "30,000" -> digits
    return re.sub(r"\s+", " ", t).strip()
    t = (text or "").lower().replace(" ", " ")
    t = re.sub(r"(?<=\d)[  ](?=\d)", "", t)   # "100 000" -> "100000"
    t = re.sub(r"\s+", " ", t)
    return t


# Each question:
#   id, cat, lang, query
#   kind: "fact" (expects a sourced+grounded answer) or "refusal" (scope/no-fabrication)
#   must:      substrings the answer MUST contain (normalized)
#   must_not:  substrings the answer must NOT contain
#   ground:    Georgian law terms; answer is "grounded" if one appears in a retrieved chunk
QUESTIONS = [
    # ---- VAT ----
    ("vat_rate", "VAT", "ru", "Какая ставка НДС в Грузии?", "fact", ["18"], [], ["18 პროცენტი", "მუხლი 166"]),
    ("vat_rate_en", "VAT", "en", "What is the VAT rate in Georgia?", "fact", ["18"], [], ["18 პროცენტი", "მუხლი 166"]),
    ("vat_rate_ka", "VAT", "ka", "რა არის დღგ-ის განაკვეთი?", "fact", ["18"], [], ["18 პროცენტი", "მუხლი 166"]),
    ("vat_threshold", "VAT", "ru", "С какого оборота нужно регистрироваться плательщиком НДС?", "fact", ["100000"], [], ["100 000"]),
    ("vat_threshold_en", "VAT", "en", "What turnover triggers mandatory VAT registration in Georgia?", "fact", ["100000"], [], ["100 000"]),
    ("vat_import", "VAT", "ru", "Платится ли НДС при импорте товаров в Грузию?", "fact", ["да"], [], ["იმპორ"]),
    ("vat_touroperator", "VAT", "ru", "Облагается ли НДС организованный въезд иностранных туристов туроператором?", "fact", ["освобожд"], ["18%"], ["ტურის", "172"]),
    # ---- Profit ----
    ("profit_rate", "Profit", "ru", "Какая ставка налога на прибыль в Грузии?", "fact", ["15"], [], ["15 პროცენტი", "მუხლი 98"]),
    ("profit_rate_en", "Profit", "en", "What is the corporate profit tax rate in Georgia?", "fact", ["15"], [], ["15 პროცენტი", "მუხლი 98"]),
    ("estonian", "Profit", "ru", "Как работает эстонская модель налога на прибыль в Грузии?", "fact", ["распредел"], [], ["განაწილ", "მოგებ"]),
    ("dividend", "Profit", "ru", "Какой налог на дивиденды для физлица в Грузии?", "fact", ["5"], [], ["დივიდენდ", "მუხლი 130"]),
    # ---- Small business / forms ----
    ("sb_rate", "SmallBiz", "ru", "Какая ставка налога для ИП со статусом малого бизнеса?", "fact", ["1"], [], ["მცირე ბიზნეს", "1 პროცენტი"]),
    ("sb_threshold", "SmallBiz", "ru", "До какого оборота действует ставка 1% для малого бизнеса?", "fact", ["500000"], [], ["500 000"]),
    ("ooo_1pct", "SmallBiz", "ru", "Может ли ООО применять режим 1% малого бизнеса?", "fact", ["нет"], ["да, ооо может"], ["მცირე ბიზნეს", "ფიზიკურ"]),
    ("micro", "SmallBiz", "ru", "Что такое микробизнес в Грузии и какой налог?", "fact", ["0", "30000"], [], ["მიკრო ბიზნეს", "30 000"]),
    # ---- Personal income ----
    ("pit_rate", "PIT", "ru", "Какая ставка подоходного налога с зарплаты в Грузии?", "fact", ["20"], [], ["20 პროცენტი", "მუხლი 81"]),
    ("rent", "PIT", "ru", "Какой налог платит физлицо при сдаче квартиры в аренду физлицу?", "fact", ["5"], [], ["5 პროცენტი", "ქირავ"]),
    ("pension", "PIT", "ru", "Как работают пенсионные взносы в Грузии?", "fact", ["2"], [], ["საპენსიო", "2 პროცენტი"]),
    # ---- Property ----
    ("property", "Property", "ru", "Какая ставка налога на имущество в Грузии?", "fact", ["1"], [], ["ქონების გადასახად"]),
    # ---- Disputes / lookup ----
    ("dispute", "Disputes", "ru", "Как обжаловать решение налоговой службы Грузии?", "fact", ["обжал"], [], ["საჩივ", "დავა"]),
    ("art_lookup", "ArticleLookup", "ru", "Что говорит статья 309 Налогового кодекса Грузии?", "fact", ["309"], [], ["მუხლი 309"]),
    ("doc_taxcode", "DocLookup", "ru", "Покажи Налоговый кодекс Грузии", "fact", ["кодекс"], [], ["საგადასახადო კოდექს"]),
    # ---- Cross-lingual variants (the core of the project) ----
    ("vat_threshold_ka", "VAT", "ka", "რა ბრუნვიდან არის სავალდებულო დღგ-ის რეგისტრაცია?", "fact", ["100000"], [], ["100 000"]),
    ("profit_rate_ka", "Profit", "ka", "რა არის მოგების გადასახადის განაკვეთი?", "fact", ["15"], [], ["15 პროცენტი", "მუხლი 98"]),
    ("dividend_en", "Profit", "en", "What is the dividend tax rate for an individual in Georgia?", "fact", ["5"], [], ["დივიდენდ", "მუხლი 130"]),
    ("dividend_ka", "Profit", "ka", "რა არის დივიდენდის გადასახადი ფიზიკური პირისთვის?", "fact", ["5"], [], ["დივიდენდ", "მუხლი 130"]),
    ("estonian_en", "Profit", "en", "How does the Estonian profit tax model work in Georgia?", "fact", ["distribut"], [], ["განაწილ", "მოგებ"]),
    ("sb_rate_en", "SmallBiz", "en", "What is the tax rate for a small business individual entrepreneur in Georgia?", "fact", ["1"], [], ["მცირე ბიზნეს"]),
    ("ooo_1pct_en", "SmallBiz", "en", "Can an LLC use the 1% small business regime in Georgia?", "fact", ["no"], ["yes, an llc can"], ["მცირე ბიზნეს", "ფიზიკურ"]),
    ("ooo_1pct_ka", "SmallBiz", "ka", "შეუძლია შპს-ს გამოიყენოს მცირე ბიზნესის 1%-იანი რეჟიმი?", "fact", ["არა"], [], ["მცირე ბიზნეს", "ფიზიკურ"]),
    ("micro_en", "SmallBiz", "en", "What is micro business status in Georgia and its tax?", "fact", ["0", "30000"], [], ["მიკრო ბიზნეს", "30 000"]),
    ("pit_rate_en", "PIT", "en", "What is the personal income tax rate on salary in Georgia?", "fact", ["20"], [], ["20 პროცენტი", "მუხლი 81"]),
    ("pit_rate_ka", "PIT", "ka", "რა არის ხელფასზე საშემოსავლო გადასახადის განაკვეთი?", "fact", ["20"], [], ["20 პროცენტი", "მუხლი 81"]),
    ("rent_en", "PIT", "en", "What tax does an individual pay on residential rent income in Georgia?", "fact", ["5"], [], ["5 პროცენტი", "ქირავ"]),
    ("pension_en", "PIT", "en", "How do pension contributions work in Georgia?", "fact", ["2"], [], ["საპენსიო", "2 პროცენტი"]),
    ("property_en", "Property", "en", "What is the property tax rate in Georgia?", "fact", ["1"], [], ["ქონების გადასახად"]),
    ("property_ka", "Property", "ka", "რა არის ქონების გადასახადის განაკვეთი?", "fact", ["1"], [], ["ქონების გადასახად"]),
    ("touroperator_en", "VAT", "en", "Is organized inbound tourism by a tour operator VAT exempt in Georgia?", "fact", ["exempt"], [], ["ტურის", "172"]),
    ("vat_rate_more", "VAT", "ru", "Сколько процентов НДС в Грузии?", "fact", ["18"], [], ["18 პროცენტი", "მუხლი 166"]),
    ("import_vat_rate", "VAT", "ru", "Какая ставка НДС при импорте в Грузию?", "fact", ["18"], [], ["18 პროცენტი"]),
    # ---- Robustness (refusals) ----
    ("offtopic", "Robustness", "ru", "Какая погода завтра в Тбилиси?", "refusal", [], ["18", "20 %", "градус"], []),
    ("fake_article", "Robustness", "ru", "Что написано в статье 9999 Налогового кодекса Грузии?", "refusal", [], ["9999 устанавливает"], []),
    ("us_tax", "Robustness", "ru", "Какая ставка налога на прибыль в США?", "refusal", ["груз"], ["15%"], []),
]


def answer(query: str, lang: str):
    """Replicate the public route: v2 rollout, then v1 fallback."""
    res = maybe_run_live_rollout(query=query, language=lang)
    if res is None:
        res = rag_pipeline.process_query(query=query, conversation_history=None, language=lang)
    return res


def retrieved_chunk_texts(query: str, lang: str, k: int = 8):
    rq = rag_pipeline._retrieval_query(query, lang)
    emb = rag_pipeline.embeddings.encode_query(rq)
    res = rag_pipeline.vector_store.search(query_embedding=emb, n_results=k)
    return res.get("documents", [[]])[0]


def main():
    quiet = "--quiet" in sys.argv
    out = {"started": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()), "results": []}
    for qid, cat, lang, query, kind, must, must_not, ground in QUESTIONS:
        t0 = time.time()
        res = answer(query, lang)
        resp = res.get("response", "")
        sources = res.get("sources", [])
        nresp = norm(resp)
        correct = all(norm(m) in nresp for m in must) and not any(norm(x) in nresp for x in must_not)
        sourced = len(sources) > 0
        grounded = None
        retrieval_correct = None  # answer from the pure-law path (v1, no guards/canned) — Phase 4 readiness
        if kind == "fact":
            used = (res.get("_rag_v2") or {}).get("used_chunks")
            chunk_texts = used if used else retrieved_chunk_texts(query, lang)
            nchunks = norm(" ".join(chunk_texts))
            grounded = any(norm(g) in nchunks for g in ground) if ground else None
            try:
                rr = rag_pipeline.process_query(query=query, conversation_history=None, language=lang)
                nrr = norm(rr.get("response", ""))
                retrieval_correct = all(norm(m) in nrr for m in must) and not any(norm(x) in nrr for x in must_not)
            except Exception as exc:
                print(f"[{qid}] retrieval-only error: {exc}", file=sys.stderr)
        out["results"].append({
            "id": qid, "cat": cat, "lang": lang, "kind": kind, "query": query,
            "correct": correct, "sourced": sourced, "grounded": grounded,
            "retrieval_correct": retrieval_correct,
            "elapsed_s": round(time.time() - t0, 2),
            "response": resp, "n_sources": len(sources),
        })
        if not quiet:
            print(f"[{qid}] correct={correct} sourced={sourced} grounded={grounded}", file=sys.stderr)

    facts = [r for r in out["results"] if r["kind"] == "fact"]
    refus = [r for r in out["results"] if r["kind"] == "refusal"]
    summ = {
        "total": len(out["results"]),
        "fact_correct": sum(r["correct"] for r in facts),
        "fact_total": len(facts),
        "fact_sourced": sum(r["sourced"] for r in facts),
        "fact_grounded": sum(bool(r["grounded"]) for r in facts),
        "fact_retrieval_correct": sum(bool(r["retrieval_correct"]) for r in facts),
        "refusal_correct": sum(r["correct"] for r in refus),
        "refusal_total": len(refus),
    }
    out["summary"] = summ
    print("SUMMARY:", json.dumps(summ), file=sys.stderr)
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
