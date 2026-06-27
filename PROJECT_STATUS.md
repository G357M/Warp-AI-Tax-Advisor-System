> **Актуальное production-состояние:** см. `docs/CURRENT_STATE.md`

# Статус проекта tax-advisor.ge / InfoHub

**Обновлено:** 2026-05-07  
**Production path:** `/root/infohub` on Hetzner  
**Public domain:** `https://tax-advisor.ge`

---

## Что это

`tax-advisor.ge` — production AI/RAG-система по грузинскому налоговому и смежному правовому корпусу.

Главный upstream-источник:
- `https://infohub.rs.ge`
- native API: `https://infohubapi.rs.ge/api`

Система предназначена для:
- сбора и обновления корпуса документов;
- нормализации и chunking;
- индексации в PostgreSQL/pgvector;
- retrieval и AI-ответов с опорой на документы;
- публикации этого функционала на `tax-advisor.ge`.

---

## Проверенное production-состояние

Проверено live на 2026-05-07:
- `documents = 14153`
- `document_chunks = 259603`
- `GET /api/v1/public/health` → `healthy`

Основные контейнеры:
- `infohub-backend`
- `infohub-postgres`
- `infohub-redis`
- `infohub-frontend`
- `infohub-nginx`

---

## Реальный стек

### Backend
- FastAPI
- SQLAlchemy
- PostgreSQL
- pgvector
- Redis
- sentence-transformers
- OpenAI / Anthropic integration

### Frontend
- Next.js 14
- React 18
- TypeScript
- TailwindCSS

### Infra
- Docker Compose
- Nginx
- Hetzner

---

## Что важно понимать

### 1. Источник данных
Старые документы в репозитории местами ссылаются на `infohub.ge`, но для текущего боевого контура правильный источник — `infohub.rs.ge`.

### 2. Vector storage
Исторически проект проходил через Chroma-ориентированную стадию, но текущий production storage — это **PostgreSQL + pgvector**.

### 3. Источник истины
Для live-системы ориентироваться нужно в первую очередь на:
1. `/root/infohub/README.md`;
2. `docker-compose.yml`;
3. текущий код в `/root/infohub`;
4. фактическое состояние БД и health endpoints.

### 4. Основной текущий фокус
На этом этапе главный bottleneck — уже не просто загрузить побольше документов, а улучшать:
- retrieval quality;
- разделение normative vs dispute;
- exact lookup по статьям/номерам/кодексу;
- цитирование и explainability.

---

## Замечание по историческим документам

Ранние версии `docs/ARCHITECTURE.md`, `docs/TECH_SPEC.md`, `docs/DEPLOYMENT.md` и старые комментарии в коде писались до текущего production-состояния. Они частично обновлены, но при противоречии приоритет у live README и реального контура.
