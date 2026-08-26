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

## Verified live and recovery state (2026-08-24)

- `documents = 15140`
- `document_chunks = 275976`
- `court_decision documents = 11423`
- `decision_facts = 11370`
- `GET /api/v1/public/health` → `healthy`
- public health exposes `last_document_ingested_at`, `documents_last_24h` and
  `documents_last_7d`, so a stable total can be distinguished from a stopped
  ingestion pipeline;
- the nightly aggregate-only freshness audit compares official per-species
  catalog totals across runs and alerts when a source grows without a corpus
  insert, becomes unavailable, decreases unexpectedly or returns processing
  errors; transient failures cannot overwrite its last good baseline;
- unchanged sub-100-character source cards are fingerprinted in the existing
  persistent Redis volume and deferred for at most seven days; changed cards
  bypass the cache immediately and any Redis error fails open to normal detail
  retrieval;
- origin TLS certificate → valid through `2026-11-17`
- provider-level Hetzner restore → passed from automatic backup image
  `423119703` created at `2026-08-22T18:28:06Z`;
- disposable restore server `163175971`, firewall `11504939` and temporary SSH
  key were removed after evidence capture; production, DNS and Plausible were not
  changed.

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
Для Налогового кодекса, Общего административного кодекса, Гражданского
кодекса и Закона «О предпринимателях» точная норма теперь
означает также проверенную прямую ссылку на конкретную статью в актуальном
официальном документе Matsne, а не только ссылку на акт целиком.
Строгие версионированные реестры содержат соответственно 326 однозначных
article anchors из публикации 245, 232 из публикации 45, 1 595 из публикации
140 Гражданского кодекса и 256 из публикации 13 Закона «О предпринимателях».
Каждый реестр воспроизводимо строится из
официального дерева документа, исключает будущие редакции и фрагменты,
назначенные нескольким статьям, а общий API-контракт отклоняет неофициальные
URL. Поэтому удалённые статьи 207–237 Налогового кодекса не получают ложную
exact-ссылку на общий фрагмент `part_511`; статья 623 Гражданского кодекса
получает проверенную ссылку `#part_745`, а статья 208 Закона «О
предпринимателях» — официальный структурный фрагмент
`#DOCUMENT:1;PART:2;CHAPTER:14;ARTICLE:208;`. Для приказа Минфина №996 exact article routing уже сохраняет номер статьи
и выбирает канонический документ InfoHub, но coverage намеренно остаётся
`official_documents`: текущая официальная публикация не предоставляет
устойчивых article anchors, поэтому выдуманная deep-link не создаётся.

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
5. **Both backup layers now have recovery evidence.** Серверный custom dump пройден с RPO 1 165 секунд / RTO 699 секунд; exact off-site custom dump от 2026-08-17 отдельно пройден с RPO 453 971 секунд / RTO 695 секунд и полными integrity gates. Provider-level восстановление Hetzner automatic backup также пройдено на изолированном временном сервере: ОС загрузилась, PostgreSQL и frontend проверены, локальный embedding-cache читается; временный сервер, firewall и SSH key удалены. Clone-only filesystem incident был исправлен через offline `e2fsck`, финальная read-only проверка чистая; production и backup image не изменялись.
6. **CI checks real contracts.** GitHub Actions запускает текущие security/quota/evidence/integration тесты, frontend lint/type-check/build, pinned Chromium visual regression для семи RU/KA/EN desktop/mobile состояний, аудит production Python-зависимостей и сборку обоих Docker-образов.
7. **Production CD is intentionally manual.** Workflow требует pinned `HETZNER_KNOWN_HOSTS` и отдельный SSH key; он вызывает тот же проверенный deploy-script и не подменяет его набором команд в YAML.
8. **Dependency baseline.** Production Python resolution проходит `pip-audit`, а полный frontend tree — `npm audit` без известных уязвимостей на 2026-08-20. После контролируемой миграции на Next 16 / React 19 high/critical findings в production frontend являются жёстким CI-блокером.
9. **Frontend runtime is current and checked.** Next 16 использует стандартный Turbopack, route types генерируются перед отдельным `tsc`, а React 19 hooks rules проходят без исключений. Desktop и 390 px smoke-test production-сборки подтверждает навигацию и мобильное меню.
10. **ML runtime is CPU-only by contract.** PyTorch устанавливается из официального CPU index; Docker build и production preflight отклоняют CUDA-сборку до замены работающего backend.
11. **Rollback and future build-cache growth are bounded.** Для backend/frontend сохраняются три новейших main-branch rollback-тега; scoped policy повторно применена 2026-08-24 и удалила восемь накопившихся exact InfoHub tags без затрагивания active images, volumes или Plausible. Production images собираются отдельным `infohub-production-v1` builder с `docker-container` driver; после build только его cache ограничивается 18 GB при 6 GB reserved и 25 GB min-free. Активный host-wide `default` builder, volumes, неизвестные теги и cache других проектов автоматически не очищаются.
12. **Backend configuration uses native Pydantic 2 contracts.** Environment names are explicit model fields, CORS accepts both production JSON and documented comma-separated values, and Celery defaults to the configured Docker `REDIS_URL`; ORM schemas and the declarative base use current Pydantic/SQLAlchemy APIs.
13. **UTC timestamps have an explicit compatibility contract.** Runtime code no longer calls deprecated `datetime.utcnow()`; a shared helper constructs time from aware UTC and returns naive UTC for the existing `timestamp without time zone` database columns. Backend contract tests treat all deprecation warnings as errors.
14. **Deterministic RAG regressions are CI-blocking.** A versioned 20-case RU/EN/KA fixture reports classification accuracy, top-1 locator recall, source-audit accuracy and exact-citation rate without LLM or database access; it covers common legal-reference variants such as Russian `НК`, English `Art.` / `No.` and RU/EN/KA parenthetical point notation. The current 125 RAG v2 tests and 143 matrix subtests run on every change, including multilingual residency/late-payment article routing and negative guards that do not misread ordinary English `no 1432` text as a document number or `part 202` as an article. Live-corpus/LLM evaluation remains a separate operational layer.
15. **Nightly live-corpus maintenance is observable.** The 03:00 UTC scraper runs the real 10-question canary and Telegram alerting; non-fatal fact/subtype/link/amendment steps now preserve their exit codes and emit one aggregated alert. News-subtype prompt text is truncated in Python after valid UTF-8 retrieval, avoiding PostgreSQL multibyte boundary failures.
16. **Live retrieval has a versioned multilingual contract.** A balanced 66-case RU/EN/KA suite runs against the connected corpus, records corpus and commit fingerprints plus per-language metrics, and disables semantic translation so the measurement makes no LLM calls or database writes. It retains citation-variant regressions, covers eight practical-tax topics in all three languages and pins article 180 of the General Administrative Code, article 623 of the Civil Code and article 208 of the Law on Entrepreneurs in RU/EN/KA. Each statutory case requires the expected current article and a verified official Matsne article deep-link. The accepted `2026-08-26.1` connected-corpus baseline for deployed commit `65d1a73` passed 66/66 (22 per language) against 15,150 documents / 276,174 chunks, with classification, top-1, source-audit, minimum-language and official-provision-link metrics all at 1.0; only an aggregate allowlist is stored in Git. Answer generation remains covered separately by the real nightly canary.
17. **Database credentials are environment-only.** The legacy embedded connection fallback was removed, production uses an isolated Docker network with no published PostgreSQL port, and the application role password is rotated through a rollback-capable health-gated script.
18. **Answer safety has a bounded multilingual evaluation contract.** A versioned 12-case RU/EN/KA suite covers grounded VAT answers, foreign jurisdictions, nonexistent provisions and obvious off-topic requests. Execution is dry-run by default and requires the reviewed 12-call LLM ceiling; PostgreSQL writes are prohibited and only an aggregate allowlist may enter Git. Pure model refusals now discard unrelated retrieval sources and become `insufficient`, while obvious scope refusals bypass retrieval and generation. The accepted `e52ecac` production baseline passed 12/12 with every overall and per-language metric at 1.0, using 6 actual provider calls out of the 12-call ceiling.
19. **Decision analytics now has an explicit quality boundary.** A versioned read-only contract measures coverage, extraction version, structural integrity, amount hygiene, outcome alignment, prior-reference safety, article-reference shape and appeal-link integrity without LLM calls or database writes. It also creates a deterministic operational review manifest for a legal expert. New extraction rejects non-positive/non-finite amounts, deduplicates article references without rewriting Georgian superscript numbering, and prevents a decision from citing itself as its own lower instance. Existing-row normalization is dry-run-first and requires an exact expected row count before apply. The v2 extraction prompt bounds both reference arrays and has a tested 1,600-token JSON budget after production showed that the legacy 800-token ceiling could truncate otherwise valid responses before parsing. On production, 61 historical rows were deterministically normalized, all 3 remaining v1 rows were upgraded within a reviewed 3-call ceiling, and the accepted `c2407c9` baseline covers 11,363/11,363 eligible decisions. Coverage, extraction version, structure, positive amounts, prior-reference safety and appeal-link integrity are 1.0; outcome alignment is 0.9981 and simple article-reference shape is 0.9959.
20. **Post-ingest quality drift has an automatic no-LLM alert path.** The nightly runner executes the 66-case RU/EN/KA live-corpus locator contract and the decision-facts quality contract after maintenance. Both use read-only database access, prohibit LLM calls, keep document-level reports in mode-600 server state and expose only aggregate summaries to Telegram. Missing reports or summaries are failures; healthy runs send no message. The provider-backed answer-safety suite intentionally remains manual and bounded.
21. **Expert review has a bounded operational handoff.** The decision-facts manifest samples every anomaly category separately, so large duplicate/unclear queues cannot hide missing identity fields or alignment/article anomalies. A stdlib-only builder deduplicates the sample into stable review IDs and produces restricted JSON/CSV/instructions/checksums only after the operator supplies both the exact dry-run item count and exact source-report SHA-256. It refuses insecure input and overwrites, neutralizes spreadsheet formulas, performs no database/LLM work and never treats a blank review bundle as legal verification. The accepted `48c9e88` production baseline retained all quality thresholds and produced 19 stratified + 18 anomaly records across all six non-empty categories, or 35 unique expert-review items after deduplication.
22. **All three recovery layers have isolated execution evidence.** A dry-run-first script fingerprints one explicit database backup and requires the exact SHA-256 before execute. The restore uses a unique disposable pgvector/PostgreSQL container with no network, ports or production volumes; it fails on missing critical tables, insufficient corpus counts, orphan decision/chunk/link rows, unvalidated foreign keys or a missing vector extension. On 2026-08-22 the protected 2.80 GB pre-auth production dump passed 15,140 documents / 275,976 chunks / 11,370 facts / 2,986 links in 699 seconds. The exact weekly off-site dump from the owner's computer independently passed 15,113 / 275,582 / 11,353 / 2,985 in 695 seconds with RPO 453,971 seconds and zero integrity anomalies. Provider-level Hetzner automatic backup `423119703` then booted on an isolated temporary server and passed filesystem, PostgreSQL, frontend and embedding-cache checks; temporary server, firewall and SSH key were deleted after evidence capture. The image-declared anonymous PostgreSQL volumes from database drills were also removed, and cleanup now uses `docker rm -v` so future drills return their disk space.
23. **The complete decision-facts legal-review backlog is exportable without database writes.** A separate connected exporter includes every unique row from the three unresolved fact queues and every member of every duplicate-number candidate group. It reports only aggregate counts during dry-run and requires exact review/group/member counts plus the exact source snapshot hash before creating a mode-600 operational export. A stdlib-only host builder creates protected full worksheets, and a tamper-aware validator requires evidence, rationale, confidence, UTC attribution and a distinct second reviewer for outcome/prevailing-party changes or duplicate exclusions. The only machine output after review is a non-executable proposal manifest with `apply_supported=false`; no SQL apply/delete path exists. The accepted `555749c` production snapshot contains 192 unique fact-review items (22 outcome-alignment, 39 article-reference and 131 unclear-outcome queue memberships) plus 463 duplicate-candidate groups / 946 members. Machine comparison classified only 1 group as `exact`, 5 as `likely` and 457 as `ambiguous`; all 463 remain pending legal review.
24. **Duplicate review has an official-source automation layer.** A bounded stdlib-only verifier reads the protected review bundle, accepts only fixed InfoHub HTTPS document UUIDs and compares their current official public-API bodies, identity fields, structured decision content and metadata. It stores hashes, lengths and similarity evidence rather than legal text, performs no database/LLM work and cannot create a legal verdict. Identical official content becomes a batch-confirmation candidate. A second conservative `official_content_high_overlap` signal requires matching identity/decision fields, at least 100 body tokens and at least 0.95 ordered-token similarity; such rows enter a short priority-confirmation CSV but receive no automatic canonical/exclusion choice because their texts differ. The accepted `b43d81c` full production run fetched 946/946 official records and reduced the priority queue from 463 groups to 11: 1 identical plus 10 high-overlap (7 formerly `ambiguous`, 3 `likely`). A separate SHA-pinned prefill tool can now transfer only technical evidence/notes into blank pending cells while preserving all expert work and leaving verdict, canonical, exclusion, confidence, attribution and state fields untouched. Its first protected production run enriched 462 of 463 rows, created zero verdicts/exclusions and passed the existing validator with all 463 rows still pending.
25. **Expert XLSX handoff is importable without manual CSV transcription.** A stdlib-only dry-run-first importer accepts the protected duplicate or fact worksheet, rejects formulas, macros, external relationships and implicitly typed populated cells, verifies every immutable value against `review_bundle.json`, normalizes JSON and requires exact bundle/workbook/output SHA-256 values plus the row count before writing a new mode-`0600` CSV. It performs no database/LLM work and preserves prefilled pending rows as pending; it cannot fabricate reviewer attribution or bypass the distinct-second-review rule.
26. **Account recovery has a safe implementation boundary.** Email verification and password reset use high-entropy one-time credentials whose SHA-256 digests, purpose, expiry and consumption state are stored in PostgreSQL. Password reset increments a session version and revokes every prior JWT, while recovery requests use generic responses and dedicated Redis-backed IP limits. The additive migration grandfathers existing accounts as verified and is part of the health-gated deploy. Production SMTP is not configured yet, so delivery remains disabled: new registrations stay usable and email-request endpoints return an explicit `503` rather than claiming that a message was sent.
27. **Shared ingress keeps the production analytics route declarative.** `stats.modern-travel.ge` is preserved in the versioned Nginx configuration and proxies to the independently managed Plausible container through request-time Docker DNS. A Plausible restart or absence therefore produces an isolated `502` on the statistics host instead of preventing the Tax Advisor ingress from starting.
28. **Frontend fonts are deterministic and language-aware.** Production builds no longer call Google Fonts. Exact Fontsource 5.3.0 packages in the npm lockfile provide Instrument Serif italic, Barlow 300–600, variable Inter and variable Noto Sans/Serif Georgian as local Next assets. The stack places every real language font before metric fallbacks, so Cyrillic now reaches Inter instead of being intercepted by Arial and Georgian reaches Noto. A static CI contract rejects external font delivery or unpinned packages; production build, RU/KA desktop/mobile browser checks and local WOFF2 requests passed.
29. **Visual regressions are CI-blocking and reproducible.** Exact `@playwright/test` 1.62.1 and the matching digest-pinned Noble image exercise seven deterministic Chromium screenshot states plus a functional grounded-answer state that asserts the exact Matsne provision URL. API fixtures, viewport, timezone, color scheme, scale and reduced motion are fixed; fonts are awaited and horizontal overflow is asserted. Linux baselines were visually reviewed, then passed a second clean run 7/7 without snapshot updates. Failed CI runs retain actual/expected/diff artifacts for 14 days.
30. **Production embeddings are cache-only and content-audited.** Production Compose disables Hub downloads by default. Root/public health expose embedding availability and source, and root health returns `503` when the model is unavailable. The deployment preflight resolves the local snapshot without network access, hashes a bounded file manifest, rejects missing model/tokenizer assets or escaping symlinks, runs repeatable RU/EN/KA vector probes with the configured dimension, verifies CPU-only PyTorch and executes only `SELECT 1` against PostgreSQL before replacing the backend.
31. **InfoHub production builds have their own Buildx cache boundary.** Deployment creates or reuses only `infohub-production-v1`, requires the `docker-container` driver and never changes the host's active default builder. Compose pins the two application image names, Buildx Bake loads exactly those targets, and a named-builder-only prune enforces 18 GB max-used, 6 GB reserved and 25 GB min-free after each build. The legacy shared cache is explicitly excluded from automation because other projects may own it.
32. **Disk pressure is measured nightly without cleanup side effects.** Before ingest, a stdlib-only host audit checks root free/used space and aggregates Buildx JSON sizes for the isolated InfoHub builder and shared `default` builder. Defaults alert below 25 GB free, above 82% root usage, above 18 GB project cache or above the 60 GB legacy observation ceiling. Only aggregate JSON can reach Telegram; no cache description, prune, image removal or volume removal exists. The first inventory measured 54.257 GB legacy cache. On 2026-08-24 a separate reviewed graph-aware exact-ID operation retired four old InfoHub dependency roots plus six direct COPY leaves: the legacy builder fell to 19.626 GB / 204 records, all ten target IDs were independently absent, root free space reached 70.73 GB and usage fell to 54.18%. The tool binds roots/leaves/parents, count, bytes and plan SHA-256, processes leaves first and remains intentionally absent from nightly automation; no global prune ran.
33. **No-op API scraper runs avoid eager AI initialization.** Before/after vector totals are read directly from PostgreSQL using the fixed active embedding column, so fully known or short-content-deferred runs do not import the eager `rag` package, load the embedding model or initialize the LLM client. A genuinely new document still enters the unchanged embedding/storage path. CI verifies both column selection and the clean-process import boundary.

---

## Current priorities

- retrieval quality для нормативных вопросов;
- normative vs dispute separation;
- exact lookup по статье / номеру / кодексу;
- citation precision и explainability;
- аккуратные incremental updates корпуса без слепого дубляжа;
- безопасный cadence ручного answer-safety прогона без неконтролируемого автоматического расхода LLM;
- фактическая проверка подготовленной decision-facts выборки профильным экспертом и документирование результатов без смешения структурной метрики с юридической достоверностью;
- последовательное закрытие полной decision-facts очереди через защищённые worksheets; машинные duplicate-классы используются только для приоритизации, не как основание для удаления;
- подключение production SMTP и end-to-end smoke для уже реализованных email verification / password recovery;
- автоматизированная оплата;
- реальные Business organizations/seats до возврата обещаний про командный доступ;
- квартальный повтор recovery drill с новым pinned evidence, чтобы подтверждённое восстановление не стало одноразовым историческим фактом.


## Scrapling status

As of 2026-05-07, targeted live audits across long `law`/`regulation`, short `news` cards, metadata-heavy anomalies, and hard outlier candidates did **not** show enough benefit to justify Scrapling rollout as a preferred extractor. Operational decision: keep Scrapling as audit/debug/fallback/repair tooling only, while the native InfoHub extraction path remains primary. See `docs/SCRAPLING_AUDIT_SUMMARY_2026-05-07.md`.

