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
12. **Backend configuration uses native Pydantic 2 contracts.** Environment names are explicit model fields, CORS accepts both production JSON and documented comma-separated values, and Celery defaults to the configured Docker `REDIS_URL`; ORM schemas and the declarative base use current Pydantic/SQLAlchemy APIs.
13. **UTC timestamps have an explicit compatibility contract.** Runtime code no longer calls deprecated `datetime.utcnow()`; a shared helper constructs time from aware UTC and returns naive UTC for the existing `timestamp without time zone` database columns. Backend contract tests treat all deprecation warnings as errors.
14. **Deterministic RAG regressions are CI-blocking.** A versioned RU/EN/KA fixture reports classification accuracy, top-1 locator recall, source-audit accuracy and exact-citation rate without LLM or database access; the existing 107 RAG v2 tests and 104 matrix subtests now run on every change. Live-corpus/LLM evaluation remains a separate operational layer.
15. **Nightly live-corpus maintenance is observable.** The 03:00 UTC scraper runs the real 10-question canary and Telegram alerting; non-fatal fact/subtype/link/amendment steps now preserve their exit codes and emit one aggregated alert. News-subtype prompt text is truncated in Python after valid UTF-8 retrieval, avoiding PostgreSQL multibyte boundary failures.
16. **Live retrieval has a versioned multilingual contract.** A balanced 21-case RU/EN/KA suite runs against the connected corpus, records corpus and commit fingerprints plus per-language metrics, and disables semantic translation so the measurement makes no LLM calls or database writes. The accepted `ea53af6` production baseline passed 21/21 with every metric at 1.0; only an aggregate allowlist is stored in Git. Answer generation remains covered separately by the real nightly canary.
17. **Database credentials are environment-only.** The legacy embedded connection fallback was removed, production uses an isolated Docker network with no published PostgreSQL port, and the application role password is rotated through a rollback-capable health-gated script.
18. **Answer safety has a bounded multilingual evaluation contract.** A versioned 12-case RU/EN/KA suite covers grounded VAT answers, foreign jurisdictions, nonexistent provisions and obvious off-topic requests. Execution is dry-run by default and requires the reviewed 12-call LLM ceiling; PostgreSQL writes are prohibited and only an aggregate allowlist may enter Git. Pure model refusals now discard unrelated retrieval sources and become `insufficient`, while obvious scope refusals bypass retrieval and generation. The accepted `e52ecac` production baseline passed 12/12 with every overall and per-language metric at 1.0, using 6 actual provider calls out of the 12-call ceiling.
19. **Decision analytics now has an explicit quality boundary.** A versioned read-only contract measures coverage, extraction version, structural integrity, amount hygiene, outcome alignment, prior-reference safety, article-reference shape and appeal-link integrity without LLM calls or database writes. It also creates a deterministic operational review manifest for a legal expert. New extraction rejects non-positive/non-finite amounts, deduplicates article references without rewriting Georgian superscript numbering, and prevents a decision from citing itself as its own lower instance. Existing-row normalization is dry-run-first and requires an exact expected row count before apply. The v2 extraction prompt bounds both reference arrays and has a tested 1,600-token JSON budget after production showed that the legacy 800-token ceiling could truncate otherwise valid responses before parsing. On production, 61 historical rows were deterministically normalized, all 3 remaining v1 rows were upgraded within a reviewed 3-call ceiling, and the accepted `c2407c9` baseline covers 11,363/11,363 eligible decisions. Coverage, extraction version, structure, positive amounts, prior-reference safety and appeal-link integrity are 1.0; outcome alignment is 0.9981 and simple article-reference shape is 0.9959.

---

## Current priorities

- retrieval quality для нормативных вопросов;
- normative vs dispute separation;
- exact lookup по статье / номеру / кодексу;
- citation precision и explainability;
- аккуратные incremental updates корпуса без слепого дубляжа;
- безопасный cadence ручного answer-safety прогона и alert по агрегированной метрике без неконтролируемого автоматического расхода LLM;
- экспертная проверка детерминированной decision-facts review-выборки и документирование результатов без смешения структурной метрики с юридической достоверностью;
- отдельная безопасная политика для глобального BuildKit cache, общего для всех проектов хоста;
- email verification / password recovery и автоматизированная оплата;
- реальные Business organizations/seats до возврата обещаний про командный доступ;
- квартальный тест восстановления резервной копии, а не только факт её создания.


## Scrapling status

As of 2026-05-07, targeted live audits across long `law`/`regulation`, short `news` cards, metadata-heavy anomalies, and hard outlier candidates did **not** show enough benefit to justify Scrapling rollout as a preferred extractor. Operational decision: keep Scrapling as audit/debug/fallback/repair tooling only, while the native InfoHub extraction path remains primary. See `docs/SCRAPLING_AUDIT_SUMMARY_2026-05-07.md`.

