# CURRENT_STATE.md

## Source of truth

Этот файл — краткое актуальное описание production-состояния проекта `tax-advisor.ge`.

Если другие документы в репозитории противоречат этому файлу, приоритет такой:
1. `docs/CURRENT_STATE.md`
2. `/root/infohub/README.md`
3. `docker-compose.yml`
4. текущий код и live state БД / API

---

## Project identity

- **Project:** `tax-advisor.ge / InfoHub`
- **Purpose:** AI/RAG-система по грузинскому налоговому и смежному правовому корпусу
- **Public domain:** `https://tax-advisor.ge`
- **Production host path:** `/root/infohub`
- **Primary upstream:** `https://infohub.rs.ge`
- **Native API:** `https://infohubapi.rs.ge/api`

---

## Live architecture

```text
infohub.rs.ge / infohubapi.rs.ge
              ↓
   scraping / export / normalization
              ↓
      PostgreSQL + pgvector
              ↓
        retrieval / ranking
              ↓
         FastAPI public API
              ↓
       Next.js frontend UI
```

---

## Production stack

### Backend
- FastAPI
- SQLAlchemy
- PostgreSQL
- pgvector
- Redis
- sentence-transformers 6.0.0
- PyTorch 2.13.0 CPU-only runtime
- OpenAI / Anthropic integration

### Frontend
- Next.js 16.3.1
- React 19.2.8
- TypeScript
- TailwindCSS

### Infra
- Docker Compose
- Nginx
- Hetzner

---

## Verified live state (2026-08-20)

- `documents = 15126`
- `document_chunks = 275821`
- `court_decision documents = 11416`
- `decision_facts = 11363`
- `GET /api/v1/public/health` → `healthy`
- origin TLS certificate → valid through `2026-11-17`

Main containers:
- `infohub-backend`
- `infohub-postgres`
- `infohub-redis`
- `infohub-frontend`
- `infohub-nginx`

---

## Product logic

Ключевая практическая задача проекта — отвечать на налоговые и правовые вопросы **с опорой на корпус документов**, а не просто генерировать общий текст.

Особенно важно:
- отличать **normative** вопросы от **dispute/case-law** вопросов;
- уметь находить точные статьи, ставки, пункты, номера документов;
- не давать нормативным вопросам тонуть в массе dispute-документов;
- возвращать grounded answer с источниками.

Каждый public/authenticated ответ теперь содержит детерминированный `evidence`
контракт. Он различает точную норму, документальную опору, неполную опору,
недостаточность источников и вопрос вне юрисдикции. Статус вычисляется кодом,
а не LLM; термин `grounded` намеренно не подменяется словом `verified`.

Пользовательский контур:
- браузерная сессия хранится в `HttpOnly`, `SameSite=Lax` cookie; Bearer JWT
  сохранён как совместимый API-механизм, но новый frontend не пишет JWT в
  `localStorage`;
- авторизованный Free-аккаунт получает 5 успешно обработанных вопросов в день;
  неуспешный запрос и отклонённая шестая попытка квоту не увеличивают;
- Pro и Business получают безлимитные вопросы и доступ к сохранённой истории с
  официальными источниками; Free-история закрыта тарифным gate на backend;
- гостевой public-чат остаётся демонстрационным контуром под IP rate limit и не
  изображается как аккаунтная квота Free.

---

## Operational notes

1. **Не путать local labs и production.** Источник истины для боевой системы — `/root/infohub`.
2. **Deploy only through the checked script.** Использовать `/root/infohub/scripts/deploy_production.sh` — он делает fast-forward-only, preflight и public health-check.
3. **pgvector is the real vector path.** Старые упоминания Chroma относятся к раннему этапу проекта.
4. **Historical docs exist.** Старые сводки и черновики могут описывать pre-production состояние.
5. **Backups have two owner-confirmed layers.** Hetzner snapshots/backups и еженедельная полная копия БД на компьютер владельца; восстановление нужно проверять отдельно раз в квартал.
6. **CI checks real contracts.** GitHub Actions запускает текущие security/quota/evidence/integration тесты, frontend lint/type-check/build, аудит production Python-зависимостей и сборку обоих Docker-образов.
7. **Production CD is intentionally manual.** Workflow требует pinned `HETZNER_KNOWN_HOSTS` и отдельный SSH key; он вызывает тот же проверенный deploy-script и не подменяет его набором команд в YAML.
8. **Dependency baseline.** Production Python resolution проходит `pip-audit`, а полный frontend tree — `npm audit` без известных уязвимостей на 2026-08-20. После контролируемой миграции на Next 16 / React 19 high/critical findings в production frontend являются жёстким CI-блокером.
9. **Frontend runtime is current and checked.** Next 16 использует стандартный Turbopack, route types генерируются перед отдельным `tsc`, а React 19 hooks rules проходят без исключений. Desktop и 390 px smoke-test production-сборки подтверждает навигацию и мобильное меню.
10. **ML runtime is CPU-only by contract.** PyTorch устанавливается из официального CPU index; Docker build и production preflight отклоняют CUDA-сборку до замены работающего backend.
11. **Rollback retention is bounded and dry-run-first.** Для backend/frontend сохраняются три новейших main-branch rollback-тега; неизвестные теги, active `:latest`, volumes и общий BuildKit cache не затрагиваются.

---

## Current priorities

- retrieval quality для нормативных вопросов;
- normative vs dispute separation;
- exact lookup по статье / номеру / кодексу;
- citation precision и explainability;
- аккуратные incremental updates корпуса без слепого дубляжа;
- непрерывный RAG-eval на эталонных вопросах и контроль актуальности источников;
- отдельная безопасная политика для глобального BuildKit cache, общего для всех проектов хоста;
- email verification / password recovery и автоматизированная оплата;
- реальные Business organizations/seats до возврата обещаний про командный доступ;
- квартальный тест восстановления резервной копии, а не только факт её создания.


## Scrapling status

As of 2026-05-07, targeted live audits across long `law`/`regulation`, short `news` cards, metadata-heavy anomalies, and hard outlier candidates did **not** show enough benefit to justify Scrapling rollout as a preferred extractor. Operational decision: keep Scrapling as audit/debug/fallback/repair tooling only, while the native InfoHub extraction path remains primary. See `docs/SCRAPLING_AUDIT_SUMMARY_2026-05-07.md`.

