#!/usr/bin/env python3
"""InfoHub / tax-advisor.ge RAG evaluation runner.

Sends a battery of Georgian tax/legal questions to the live public query
endpoint and records the answers + sources for manual scoring.

Run ON infohub-production (has localhost:8000 and python3):
    python3 run_eval.py            # hits http://localhost:8000
    API=https://tax-advisor.ge/api/v1python3 run_eval.py   # public path
"""
import json, os, time, urllib.request, urllib.error

API = os.environ.get("API", "http://localhost:8000/api/v1")
ENDPOINT = API.rstrip("/") + "/public/query"

# Each item: id, category, lang, query, expect (note for human scoring — NOT sent)
QUESTIONS = [
    # --- VAT ---
    ("vat_rate_ru", "VAT", "ru", "Какая ставка НДС в Грузии?", "18% standard"),
    ("vat_rate_en", "VAT", "en", "What is the VAT rate in Georgia?", "18% standard"),
    ("vat_threshold_ru", "VAT", "ru", "С какого оборота нужно регистрироваться плательщиком НДС в Грузии?", "100,000 GEL / 12 months"),
    ("vat_touroperator_ru", "VAT", "ru", "Облагается ли НДС организованный въезд иностранных туристов туроператором?", "exempt, Art 172(4); input VAT recoverable"),
    # --- Profit / corporate ---
    ("profit_rate_ru", "Profit", "ru", "Какая ставка налога на прибыль в Грузии?", "15% (Estonian model, on distribution)"),
    ("estonian_ru", "Profit", "ru", "Как работает эстонская модель налогообложения прибыли в Грузии?", "tax only on distributed profit, 15%"),
    ("dividend_ru", "Profit", "ru", "Какой налог на дивиденды для физлица в Грузии?", "5%"),
    # --- Small business / ИП vs ООО (critical) ---
    ("sb_1pct_ru", "SmallBiz", "ru", "Что такое статус малого бизнеса и какая ставка 1%?", "ИП small business: 1% of turnover up to 500k GEL"),
    ("sb_threshold_ru", "SmallBiz", "ru", "До какого оборота действует ставка 1% для малого бизнеса?", "500,000 GEL turnover"),
    ("ooo_1pct_ru", "SmallBiz", "ru", "Может ли ООО (LLC) применять режим 1% малого бизнеса?", "NO — only ИП/individual entrepreneur qualifies (critical)"),
    ("micro_ru", "SmallBiz", "ru", "Что такое микробизнес в Грузии и какой налог?", "0%, turnover up to 30k GEL, no employees"),
    # --- Personal income ---
    ("pit_rate_ru", "PIT", "ru", "Какая ставка подоходного налога с зарплаты в Грузии?", "20%"),
    ("rent_individual_ru", "PIT", "ru", "Какой налог платит физлицо при сдаче квартиры в аренду физлицу?", "5% (residential rental)"),
    ("pension_ru", "PIT", "ru", "Как работают пенсионные взносы в Грузии?", "2%+2%+2% accumulative pension"),
    # --- Property / other ---
    ("property_ru", "Property", "ru", "Какая ставка налога на имущество в Грузии?", "up to 1%"),
    ("import_vat_ru", "Customs", "ru", "Платится ли НДС при импорте товаров в Грузию?", "yes, 18% import VAT"),
    # --- Document lookup / metadata ---
    ("doc_taxcode_ru", "DocLookup", "ru", "Покажи Налоговый кодекс Грузии", "should return Tax Code document with link"),
    ("doc_taxcode_ka", "DocLookup", "ka", "მაჩვენე საქართველოს საგადასახადო კოდექსი", "Tax Code doc"),
    ("art_lookup_ru", "ArticleLookup", "ru", "Что говорит статья 309 Налогового кодекса Грузии?", "specific article content if present"),
    # --- Multilingual consistency ---
    ("vat_rate_ka", "Multilingual", "ka", "რა არის დღგ-ის განაკვეთი საქართველოში?", "18%"),
    ("profit_rate_en", "Multilingual", "en", "What is the corporate profit tax rate in Georgia?", "15%"),
    ("profit_rate_ka", "Multilingual", "ka", "რა არის მოგების გადასახადის განაკვეთი?", "15%"),
    # --- Disputes / court ---
    ("dispute_ru", "Disputes", "ru", "Как обжаловать решение налоговой службы Грузии?", "appeal to Revenue Service dispute board then court"),
    # --- Adversarial / robustness ---
    ("adv_offtopic_ru", "Robustness", "ru", "Какая погода завтра в Тбилиси?", "should refuse / say out of scope, not hallucinate tax"),
    ("adv_fake_article_ru", "Robustness", "ru", "Что написано в статье 9999 Налогового кодекса Грузии?", "should NOT fabricate a non-existent article"),
    ("adv_us_tax_ru", "Robustness", "ru", "Какая ставка налога на прибыль в США?", "out of scope (Georgia only) — should not give confident GE-style answer"),
]


SMOKE_TOKEN = os.environ.get("SMOKE_TOKEN", "")


def ask(query, language):
    body = json.dumps({"query": query, "language": language}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if SMOKE_TOKEN:
        headers["X-Smoke-Token"] = SMOKE_TOKEN  # trusted automation: bypass public rate limit
    req = urllib.request.Request(ENDPOINT, data=body, headers=headers)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
            data["_http"] = 200
            return data
    except urllib.error.HTTPError as e:
        return {"_http": e.code, "_error": e.read().decode("utf-8", "replace")[:500], "response": "", "sources": []}
    except Exception as e:
        return {"_http": None, "_error": str(e), "response": "", "sources": []}
    finally:
        pass


def main():
    out = {"endpoint": ENDPOINT, "started": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()), "results": []}
    for qid, cat, lang, query, expect in QUESTIONS:
        print(f"[{qid}] ({lang}) {query}")
        t0 = time.time()
        res = ask(query, lang)
        elapsed = round(time.time() - t0, 2)
        srcs = [{"title": s.get("metadata", {}).get("title") or s.get("text"),
                 "type": s.get("metadata", {}).get("document_type"),
                 "url": s.get("metadata", {}).get("source_url"),
                 "relevance": s.get("relevance")} for s in res.get("sources", [])]
        out["results"].append({
            "id": qid, "category": cat, "lang": lang, "query": query, "expect": expect,
            "http": res.get("_http"), "error": res.get("_error"),
            "response": res.get("response", ""),
            "retrieved_count": res.get("retrieved_count", len(srcs)),
            "elapsed_s": elapsed, "sources": srcs,
        })
        print(f"   -> http={res.get('_http')} {elapsed}s, {len(srcs)} sources")
    out["finished"] = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
