# Оценка проекта InfoHub / tax-advisor.ge

> Актуальный CI-контур: `rag_v2_golden_set.json` содержит независимый
> multilingual fixture, а `rag_v2_contract_gate.py` детерминированно измеряет
> classification accuracy, top-1 locator recall, source-audit accuracy и exact
> citation rate. Gate не использует LLM или production-БД и дополняет, но не
> заменяет live-corpus harness. Отдельный набор
> `backend/evaluation/rag_v2_live_corpus_set.json` содержит 21 сбалансированный
> RU/EN/KA контракт для реальной БД, а
> `backend/scripts/evaluate_rag_v2_live_corpus.py` сохраняет commit, fingerprint
> корпуса, общие и поязыковые метрики. В этом профиле `semantic_search`
> принудительно отключён, поэтому прогон не вызывает LLM и ничего не пишет в БД.

Папка с материалами проверки RAG-системы: как работает и насколько корректно
отвечает на вопросы по налоговому праву Грузии.

Дата прогона: **2026-06-28**. Стенд: infohub-production (46.224.145.5), `localhost:8000`.

## Файлы
| Файл | Что внутри |
|---|---|
| `architecture.md` | Как устроена система: стек, данные, RAG v1/v2, пайплайн ответа |
| `findings.md` | **Главный отчёт**: оценки, сильные стороны, дефекты, корневая гипотеза, рекомендации |
| `run_eval.py` | Прогонщик батча вопросов (воспроизводимо) |
| `results_raw.json` | Сырые ответы системы на все 26 вопросов + источники |
| `rag_v2_golden_set.json` | Версионируемые RU/EN/KA routing/citation ожидания для offline CI |
| `rag_v2_contract_gate.py` | Машинный quality gate без сети, LLM и production-БД |
| `../backend/evaluation/rag_v2_live_corpus_set.json` | 21 RU/EN/KA ожидание для подключённого боевого корпуса |
| `../backend/scripts/evaluate_rag_v2_live_corpus.py` | Read-only live evaluator с corpus fingerprint и историческим JSON-отчётом |
| `baselines/` | Безопасные агрегированные снимки метрик, привязанные к production commit и состоянию корпуса; query/document rows не сохраняются в Git |

## TL;DR
Система **живая, быстрая (~1.5 с), мультиязычная (ka/ru/en)** и хорошо отвечает на
базовые ставки с цитированием статей. Главные проблемы:
- ✗ **Критично:** на вопрос «может ли ООО применять 1%» отвечает «да» — это неверно
  (только ИП). См. `findings.md` §1.
- ✗ Профильный туроператорский вычет НДС (ст. 172) подменяется общим ответом.
- ✗ Не распознаёт вопросы вне юрисдикции Грузии.
- ○ Ряд реально существующих норм (порог НДС 100k, микробизнес, пенсия, налог на
  имущество) не достаётся ретривером — отвечает «нет данных».

Корневая причина большинства дефектов: фактические вопросы идут через **RAG v1** с
почти одинаковым generic-источником, ответ во многом из знаний LLM. Продвинутый
**RAG v2** включён лишь для 4 классов document-lookup. Подробно — `findings.md`.

## Поабзацные оценки (26 вопросов)
| id | категория | язык | вердикт |
|---|---|---|---|
| vat_rate_ru / _en / _ka | НДС ставка | ru/en/ka | ✅ |
| vat_threshold_ru | порог НДС 100k | ru | ○ нет данных |
| vat_touroperator_ru | туроператор ст.172 | ru | ✗ неверно |
| profit_rate_ru / _en / _ka | прибыль 15% | ru/en/ka | ✅ |
| estonian_ru | эстонская модель | ru | ○ нет данных |
| dividend_ru | дивиденды 5% | ru | ✅ |
| sb_1pct_ru | МБ 1% | ru | ✅ |
| sb_threshold_ru | порог МБ 500k | ru | ◐ без суммы |
| ooo_1pct_ru | ООО и 1% | ru | ✗ **критично неверно** |
| micro_ru | микробизнес | ru | ○ нет данных |
| pit_rate_ru | подоходный 20% | ru | ✅ |
| rent_individual_ru | аренда 5% | ru | ✅ |
| pension_ru | пенсия 2+2+2 | ru | ○ нет данных |
| property_ru | налог на имущество | ru | ○ нет данных |
| import_vat_ru | НДС при импорте | ru | ◐ верно, но размыто |
| doc_taxcode_ru / _ka | показать кодекс | ru/ka | ◐ пересказ, не карточка |
| art_lookup_ru | ст. 309 | ru | ✅ |
| dispute_ru | обжалование | ru | ◐ сыровато |
| adv_offtopic_ru | погода (robustness) | ru | ✅ корректный отказ |
| adv_fake_article_ru | ст. 9999 (robustness) | ru | ✅ не выдумал |
| adv_us_tax_ru | налог в США (robustness) | ru | ✗ ответил «Грузия 15%» |

## Боевой публичный путь — проверен
`https://tax-advisor.ge/api/v1/public/query` (Cloudflare → nginx → backend:8000)
отвечает **идентично бэкенду** (та же «18%, ст. 166»). Прод-routing исправен.

⚠️ Методический нюанс: при тесте из **Windows-shell** кириллицу в `curl -d '...'`
инлайн мангалит → бэкенд получает мусор → «нет данных, 0 источников» (ложная тревога).
Слать UTF-8 из файла: `curl --data-binary @payload.json`. Батч `run_eval.py`
гоняется на сервере и от этого не страдает.

## Воспроизвести
```bash
# на сервере (есть localhost:8000 и python3)
scp evaluation/run_eval.py root@46.224.145.5:/root/infohub/
ssh root@46.224.145.5 'cd /root/infohub; \
  export SMOKE_TOKEN=$(grep "^RATE_LIMIT_BYPASS_TOKEN=" .env | cut -d= -f2-); \
  python3 run_eval.py > /tmp/eval.json'   # JSON в конце stdout
```
Набор вопросов и эталоны для ручной оценки — в самом `run_eval.py` (поле `expect`).
После исправлений перепрогнать и сравнить как регрессию.
