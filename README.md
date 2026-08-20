> **Актуальное production-состояние:** см. `docs/CURRENT_STATE.md`

# tax-advisor.ge / InfoHub

## Что это

`tax-advisor.ge` — это боевой AI-проект по сбору, нормализации, индексации и поиску по грузинскому налоговому и смежному правовому корпусу.

Главный источник данных:
- `https://infohub.rs.ge`
- native API: `https://infohubapi.rs.ge/api`

Цель проекта:
1. выкачать и поддерживать у себя полную или практически полную базу релевантных документов;
2. построить собственную searchable knowledge base;
3. давать ответы через AI с опорой на документы, фрагменты и цитаты;
4. обслуживать это на домене `https://tax-advisor.ge`.

> Важно: старые документы и заметки в репозитории местами ещё упоминают `infohub.ge`. Для текущего боевого контура правильный источник — `infohub.rs.ge`.

---

## Что именно хранит система

Проект ориентирован не на «общий чат-бот», а на правовой корпус, в котором есть как минимум:
- законодательные и подзаконные акты;
- разъяснения и нормативные публикации;
- налоговые и таможенные споры / судебно-административные материалы;
- связанные метаданные, ссылки на источник и служебные поля для retrieval.

На практике особенно важно различать как минимум две большие линии источников:
- **normative lane** — нормы, кодексы, законы, приказы, разъяснения;
- **dispute lane** — споры, судебные/квазисудебные решения и конфликтные кейсы.

Это разделение критично для качества ответов: вопросы про ставки, статьи и правила не должны тонуть в массе dispute-документов.

---

## Текущий production контур

Боевой проект расположен на Hetzner в:
- `/root/infohub`

Публичный домен:
- `https://tax-advisor.ge`

Основные контейнеры:
- `infohub-backend`
- `infohub-postgres`
- `infohub-redis`
- `infohub-frontend`
- `infohub-nginx`

### Проверенное live-состояние на 2026-05-07

Проверено на production:
- `documents`: **14153**
- `document_chunks`: **259603**
- public health: **healthy**

Это уже не пустой MVP и не mock-база, а живая загруженная правовая система.

---

## Архитектура

```text
infohub.rs.ge / infohubapi.rs.ge
              │
              ▼
     scraping / export / normalization
              │
              ▼
   PostgreSQL + pgvector + metadata
              │
              ▼
       RAG / retrieval / ranking
              │
              ▼
        FastAPI public API
              │
              ▼
      Next.js frontend on tax-advisor.ge
```

### Основные слои

#### 1. Ingestion / scraping
В репозитории есть несколько путей извлечения данных:
- `backend/scraper/infohub_scraper.py`
- `backend/scraper/enhanced_scraper.py`
- `backend/scraper/playwright_scraper.py`
- `backend/scraper/firecrawl_scraper.py`
- `backend/scraper/spiders/infohub_spider.py`
- `corpus-tools/` — утилиты экспорта/нормализации корпуса

Задача ingestion-слоя:
- получить документы и метаданные из `infohub.rs.ge` / `infohubapi.rs.ge`;
- сохранить source URL, тип документа, заголовки, структуру и текст;
- подготовить материал к нормализации и индексации.

#### 2. Processing
- очистка текста;
- нормализация HTML/markdown/native payload;
- разбиение на chunks;
- подготовка метаданных для retrieval и цитирования.

Основные файлы:
- `backend/processor/chunker.py`
- `corpus-tools/...`

#### 3. Storage
Текущий production storage:
- **PostgreSQL** — документы, метаданные, full text;
- **pgvector** — embeddings / similarity search;
- **Redis** — cache и служебные runtime-задачи.

> Исторически в коде ещё встречаются следы `ChromaDB`, но live-контур работает через Postgres/pgvector и именно его надо считать главным storage path.

#### 4. Retrieval / RAG
Backend ищет релевантные chunks, затем собирает контекст и формирует grounded answer.

Основные файлы:
- `backend/rag/pipeline.py`
- `backend/rag/vector_store_pgvector.py`
- `backend/rag/embeddings.py`
- `backend/rag/llm.py`

#### 5. API и frontend
- **FastAPI** обслуживает public и internal endpoints;
- **Next.js 16** — пользовательский фронтенд сайта `tax-advisor.ge`.

---

## Текущий стек

### Backend
- Python
- FastAPI
- SQLAlchemy
- pgvector / PostgreSQL
- Redis
- sentence-transformers
- OpenAI / Anthropic integration

### Frontend
- Next.js 16
- React 19
- TypeScript
- TailwindCSS

### Infra
- Docker Compose
- Nginx
- Hetzner

---

## Ключевая продуктовая логика

Проект решает не только задачу «найти похожие куски текста», но и более жёсткую задачу:
- понять тип запроса;
- отделить нормативные вопросы от dispute/case-law вопросов;
- вытащить правильные статьи, ставки, пункты и документы;
- ответить по-русски / по-грузински / по-английски;
- по возможности сослаться на источник и релевантный документ.

Особенно важные классы запросов:
- ставки налогов;
- конкретные статьи кодекса;
- изменения законодательства;
- таможенные и налоговые споры;
- поиск точного документа по номеру / названию / типу.

---

## API

Главный публичный путь:
- `POST /api/v1/public/query`

Проверка здоровья:
- `GET /api/v1/public/health`
- `GET /health`

Примеры других маршрутов есть в:
- `backend/api/routes/public.py`
- `backend/api/routes/query.py`
- `backend/api/routes/scraper.py`
- `backend/api/routes/auth.py`

### Пример health check

```bash
curl https://tax-advisor.ge/api/v1/public/health
```

### Пример public query

```bash
curl -X POST https://tax-advisor.ge/api/v1/public/query \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "Какая ставка НДС в Грузии?",
    "language": "ru"
  }'
```

---

## Структура репозитория

```text
/root/infohub
├── backend/           # API, RAG, storage adapters, scraper modules
├── frontend/          # Next.js frontend
├── corpus/            # экспортированный / нормализованный корпус
├── corpus-tools/      # утилиты выгрузки, нормализации и переиндексации
├── nginx/             # nginx config
├── static-frontend/   # static assets used by nginx
├── scripts/           # вспомогательные setup scripts
├── audits/            # артефакты аудита корпуса и источников
├── logs/              # runtime logs
└── docker-compose.yml # production compose
```

---

## Важные operational notes

1. **Не путать локальные repair/labs-копии с боевым проектом.**
   Источник истины для live-системы — `/root/infohub` на Hetzner.

2. **Изменение host-файла не всегда меняет live-поведение.**
   Backend работает из Docker image, поэтому реальные изменения backend-кода требуют rebuild/restart контейнера.

3. **README ниже уровня `/root/infohub` может отставать.**
   Некоторые docs в репозитории писались на более раннем этапе и содержат старые ссылки на `infohub.ge`, ChromaDB или ещё не реализованные части.

4. **Retrieval quality важнее простого объёма corpus.**
   После большой загрузки корпуса узким местом становится уже не только ingestion, а ranking, query intent и точность нормативных ответов.

---

## Приоритеты развития

Текущие практические направления развития:
- улучшение retrieval для нормативных вопросов;
- более точное разделение normative vs dispute;
- better exact lookup по номеру документа / статье / кодексу;
- повышение качества цитирования и explainability;
- аккуратное обновление корпуса без повторной слепой загрузки дублей.

---

## Быстрый старт для оператора

### Проверить контейнеры

```bash
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
```

### Проверить public health

```bash
curl https://tax-advisor.ge/api/v1/public/health
```

### Проверить число документов

```bash
docker exec infohub-postgres psql -U infohub_user -d infohub_ai -c "select count(*) from documents;"
```

### Безопасно развернуть изменения из GitHub

```bash
cd /root/infohub
./scripts/deploy_production.sh
```

Скрипт делает только fast-forward из `origin/main`, сохраняет rollback-теги
образов, выполняет preflight backend/БД и проверяет public health. Процедуры
TLS renewal, логов и проверки резервных копий описаны в
[`docs/PRODUCTION_OPERATIONS.md`](docs/PRODUCTION_OPERATIONS.md).

---

## Статус README

Этот README обновлён под реальный production-контур проекта `tax-advisor.ge`.

Если другие документы в репозитории противоречат ему по источнику данных (`infohub.ge` vs `infohub.rs.ge`) или по storage path (`ChromaDB` vs `pgvector`), ориентироваться нужно в первую очередь на:
1. текущий код в `/root/infohub`;
2. `docker-compose.yml`;
3. live database state;
4. этот README.


## Public smoke quick checks

- Operational note: `docs/PUBLIC_SMOKE_OPERATIONAL.md`
- Browser/public trimmed smoke: `make smoke-public`
- Browser/public core smoke: `make smoke-public-core`
- API policy smoke: `make smoke-public-api`
- Combined smoke: `make smoke-public-both`

