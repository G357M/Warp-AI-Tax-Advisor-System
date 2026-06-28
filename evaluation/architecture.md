# InfoHub / tax-advisor.ge — как система устроена

_Снимок на 2026-06-28, по живому стенду infohub-production (46.224.145.5)._

## Назначение
RAG-ассистент по налоговому/правовому законодательству Грузии. Публичный фронт —
`tax-advisor.ge`. Отвечает на вопросы на трёх языках (ka / ru / en) с цитированием
источников из корпуса документов infohub.rs.ge.

## Стек (docker-compose, 5 контейнеров)
| Контейнер | Роль |
|---|---|
| `infohub-backend` | FastAPI, RAG-пайплайн, порт 8000 |
| `infohub-postgres` | pgvector (pg15), хранилище документов + эмбеддингов |
| `infohub-redis` | кэш / rate-limit |
| `infohub-frontend` | Next.js (`NEXT_PUBLIC_API_URL=https://tax-advisor.ge/api`) |
| `infohub-nginx` | reverse-proxy + TLS |

Здоровье на момент проверки: `database, redis, embeddings, vector_store, llm` = все `true`.

## Данные
- **14 725 документов** в `documents`, **269 218 чанков** с эмбеддингами.
- Типы: `court_decision` 10 734, `regulation` 1 687, `law` 925, `news` 803, споры
  (фин. мин. / СД) ~470, изменения в актах ~90 и пр.
- Эмбеддинги: `sentence-transformers/paraphrase-multilingual-mpnet-base-v2`, dim **768**.
- LLM: **gpt-4o-mini** (OpenAI).

## Пайплайн ответа
Публичный эндпоинт: `POST /api/v1/public/query` `{query, language}` →
`{response, sources[], retrieved_count, processing_time}`.
Rate-limit: 10 запросов / окно; обход — заголовок `X-Smoke-Token` (=`RATE_LIMIT_BYPASS_TOKEN`).

Внутри две ветки:

1. **RAG v2** (`rag_v2/pipeline_v2.py`) — продвинутый путь: классификатор запроса,
   несколько генераторов кандидатов, legal-reranker, резолвер статей/цитат,
   exact-doc-resolver. **Включён только в режиме `rollout` для 4 классов запросов**:
   `named_document_lookup, canonical_law_lookup, local_regulation_lookup, amendment_tracking`
   (top_k=3). Shadow-режим логирует сравнение v2 vs v1 в `/tmp/rag_v2_shadow.jsonl`.

2. **RAG v1** (`rag/pipeline.py`, `process_query`) — fallback для всего остального
   (ставки, режимы, общие вопросы). Семантический поиск по vector_store +
   несколько эвристик добора (`_canonical_override_chunks`, `_title_lookup_chunks`,
   `_keyword_fallback_chunks`), затем генерация ответа LLM.

**Следствие:** большинство «фактических» вопросов (какая ставка, может ли ООО…)
обслуживает именно **v1**, а не продвинутый v2. Это ключ к интерпретации результатов
(см. `findings.md`).

## Скрапер (контекст)
Корпус пополняется ночным скрапером infohub.rs.ge (cron 03:00 UTC,
`run_scraper.sh` → контейнер). Подробно — в памяти проекта `infohub-scraper-state`.
