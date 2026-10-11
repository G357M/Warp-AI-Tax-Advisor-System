# Админка, этап 1: основа — дизайн

Дата: 2026-10-11. Статус: на согласовании.

## Контекст и цель

`/admin` — рабочее место единственного администратора (Гела). Сейчас админка
визуально разнородна (inline-стили, navy/slate вместо стиля сайта), почти не
переведена (меню на английском, страницы на русском), Settings — нерабочая
форма-заглушка, а изменяющие действия администратора нигде не журналируются.

Этап 1 — первый из пяти (1 основа → 2 клиенты → 4 качество ответов →
3 динамика → 5 операции). Он создаёт то, на чём строятся остальные:
единый стиль и компоненты, переводы RU/KA/EN, журнал действий администратора,
переработанные Dashboard и Settings.

### Успех этапа

- Все страницы `/admin/*` используют один CSS-модуль и общие компоненты;
  в `frontend/app/admin/**` нет атрибутов `style={{…}}`.
- Все строки админки доступны на RU/KA/EN и следуют языку из шапки сайта.
- Каждое изменяющее действие администратора (смена роли, ручная активация
  подписки, смена статуса feedback) атомарно оставляет запись в
  `admin_audit_log`; журнал виден на странице `/admin/audit`.
- Dashboard показывает, что требует внимания; Settings честно показывает
  конфигурацию без секретов.

### Решения, принятые с пользователем

- Одна роль `admin`, без разделения прав.
- Стиль — единый с сайтом (liquid-glass, `#DC2626`); вариант A: CSS-модуль на
  токенах сайта + компоненты в `components/admin/`, без новых UI-библиотек.
- Журнал — вариант A: явный вызов helper-а в изменяющем эндпоинте, в той же
  транзакции.

### Вне этапа 1

Новая функциональность Users (поиск, карточка, блокировка) — этап 2; графики —
этап 3; лента диалогов и оценка ответов — этап 4; запуск задач и статусы
бэкапа/канарейки — этап 5. Логика сверки платежей (`/admin/billing`) не
меняется. Произвольный SQL и опасные действия из браузера не добавляются.

## 1. Журнал действий администратора (бэкенд)

### Таблица `admin_audit_log`

| Колонка | Тип | Примечание |
|---|---|---|
| `id` | UUID PK | |
| `actor_id` | UUID NOT NULL | администратор; без FK, чтобы удаление пользователя не ломало журнал |
| `action` | VARCHAR(64) NOT NULL | `user.role_changed`, `subscription.activated`, `feedback.status_changed` |
| `target_type` | VARCHAR(32) NOT NULL | `user`, `checkout`, `feedback` |
| `target_id` | VARCHAR(64) NOT NULL | id объекта строкой |
| `before` | JSON NULL | значимые поля до изменения |
| `after` | JSON NULL | значимые поля после |
| `reason` | TEXT NULL | причина из диалога подтверждения |
| `created_at` | TIMESTAMP NOT NULL | UTC (`utc_now`) |

Индексы: `(created_at DESC)`, `(action, created_at)`, `(actor_id, created_at)`.
Append-only: statement-триггер `BEFORE UPDATE OR DELETE OR TRUNCATE`,
вызывающий исключение, `ENABLE ALWAYS` — тот же приём, что у
`billing_review_decisions`.

В `before`/`after` никогда не пишутся пароли, хэши, токены и прочие секреты —
только перечисленные в helper-е поля.

### Установка схемы

`backend/scripts/add_admin_audit_log.py` по образцу
`add_billing_review_journal.py`: кортеж `DDL`, `contract_sha256()`,
`apply_schema()` с аудитом колонок и триггера, запуск через
`schema_contract_cli.run` (по умолчанию dry plan, `--apply` +
`--expected-contract-sha256`). В `scripts/deploy_production.sh` добавляется
шаг с закреплённым SHA перед `docker compose up … backend`. ORM-модель
`AdminAuditLog` в `backend/models/` (для чтения и вставки).

### Helper

`backend/core/admin_audit.py`:

```python
def record_admin_action(db, *, actor, action, target_type, target_id,
                        before=None, after=None, reason=None) -> AdminAuditLog
```

Добавляет запись в текущую сессию без `commit()`; коммит делает эндпоинт
вместе с самим изменением. Ошибка вставки → исключение → откат всей
транзакции: изменения без записи в журнале не бывает. `reason` обрезается до
1000 символов; `action` проверяется по фиксированному набору констант.

### Подключение к существующим действиям

- `PATCH /admin/users/{id}/role` — `user.role_changed`, before/after `{role}`.
- `PATCH /admin/feedback/{id}` — `feedback.status_changed`, before/after `{status}`.
- `POST /billing/admin/activate` — `subscription.activated`, target —
  checkout (по `checkout_id`) или пользователь (legacy email-путь),
  before/after `{plan, status, period_end}`. Существующая идемпотентность
  сохраняется: повтор, не изменивший состояние, записи не создаёт.

Все три эндпоинта принимают необязательное поле `reason` (до 1000 символов).
Решения сверки платежей уже пишутся в `billing_review_decisions` и здесь не
дублируются.

### API чтения

`GET /admin/audit?action=&actor_id=&limit=50&offset=0` (фильтры по датам
не нужны этапу 1: журнал листается от новых к старым) →
`{items: [{id, actor: {id, username}, action, target_type, target_id, before,
after, reason, created_at}], total}`. `limit` ≤ 200. Под `require_admin`
(через router-зависимость, как остальные `/admin`).

## 2. Стиль и компоненты (фронтенд)

### Стиль

`frontend/app/admin/admin.module.css` — единственный модуль стилей админки
(кроме уже существующего `billing/reconciliation.module.css`). Строится на
токенах `globals.css`: фон `hsl(var(--background))`, текст
`--foreground`/`--muted-foreground`, линии `--border`, акцент `--primary`
(активный пункт меню, основная кнопка, focus-ring), панели — класс
`liquid-glass`, радиус `--radius`, шрифтовой стек сайта. Статусные цвета:
success `--success`, error `--error*`, warning `#d97706`.

`billing/reconciliation.module.css`: заменяются только цвета navy/slate на
токены; разметка и поведение не меняются. `billing/DESIGN.md` обновляется под
новую палитру.

### Компоненты `frontend/components/admin/`

| Компонент | Назначение |
|---|---|
| `PageHeader` | заголовок, подзаголовок, слот действий |
| `StatTile` | подпись, значение, деталь, необязательная ссылка |
| `DataTable<T>` | колонки `{key, header, render?}`, строки, слоты поиска и пагинации, состояния loading/error/empty; ≤767 px строки становятся карточками |
| `Badge` | `tone: success / warning / error / neutral` |
| `ConfirmDialog` | заголовок, текст, необязательное поле «причина», confirm/cancel; на базе `components/ui/Dialog` |
| `AdminState` | единые блоки «загрузка», «ошибка» (с «повторить»), «пусто» |
| `Pagination` | назад/вперёд, «N–M из K» |

### Переводы

`frontend/lib/admin-i18n.ts`: словарь `{ru, ka, en}` по разделам (`nav`,
`common`, `dashboard`, `audit`, `config`, `users`, `documents`, `feedback`,
`scraper`, `analytics`) и хук `useAdminCopy()` → `{lang, c, locale}`,
использующий язык из `useLang()`; `ka` и `en` типизированы по `ru`, поэтому
пропущенная строка ломает typecheck. Даты и числа форматируются локалью языка (`ru-RU`, `ka-GE`,
`en-GB`). Грузинские строки проверяются по `georgian-writing-style`.
Строки Payments остаются в `lib/billing-reconciliation.ts`.

### Перенос страниц

Layout, Dashboard, Audit (новая), Settings/Config (переписана) получают новый
вид и функциональность. Users, Documents, Feedback, Scraper, Analytics
переводятся на компоненты, стиль и переводы без изменения поведения. Смена
роли и активация подписки в Users и смена статуса в Feedback идут через
`ConfirmDialog` и передают `reason`. В меню добавляется пункт «Журнал»
(`/admin/audit`); пункт Settings переименовывается в «Конфигурация».
Неиспользуемые после переноса зависимости (например `framer-motion` в
Settings) удаляются из админки, но не из `package.json`, если они нужны сайту.

## 3. Dashboard и Config

### Dashboard (`/admin`)

1. Блок «Требует внимания» — показываются только непустые пункты, каждый со
   ссылкой: новые feedback (`status='new'`) → `/admin/feedback`; платежи в
   очереди сверки → `/admin/billing`; ручные заявки, ожидающие активации
   (`provider='manual'`, `status='pending'`, не истёкшие) → `/admin/users`;
   ночной ингест старше 36 ч → `/admin/scraper`; очередь decision_facts > 0 →
   `/admin/scraper`.
2. Шесть существующих плиток (`StatTile`).
3. Корпус по типам.
4. Последние 5 записей журнала → ссылка на `/admin/audit`.

`GET /admin/stats` дополняется полями `feedback.new`,
`billing.reconciliation_open`, `billing.manual_pending` и
`attention.ingest_stale` (bool, порог 36 ч). Фильтр очереди сверки выносится из
`reconciliation_queue` в общую функцию (например
`reconciliation_queue_filter()` в `api/routes/billing.py` или сервисном
модуле), которую используют и список, и счётчик, — чтобы цифра на Dashboard не
расходилась со списком на `/admin/billing`. Ответ существующего списка не
меняется.

### Config (`/admin/settings`)

`GET /admin/config` — только чтение, явный белый список:

- приложение: `APP_VERSION`, `ENVIRONMENT`, `DEBUG`;
- LLM/RAG: `LLM_PROVIDER`, `LLM_MODEL`, `EMBEDDING_MODEL`, `RAG_TOP_K`,
  `RAG_MIN_SIMILARITY`, `JEV_MODE`;
- почта: `EMAIL_DELIVERY_ENABLED`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM`;
- биллинг: `BILLING_TBC_ENABLED`, `BILLING_CONTACT_EMAIL`, лимит Free
  (`FREE_DAILY_QUESTIONS`);
- лимиты: `RATE_LIMIT_ENABLED`;
- наличие секретов (только `true/false`): `OPENAI_API_KEY`,
  `ANTHROPIC_API_KEY`, `SMTP_PASSWORD`, `TBC_API_KEY`, `TBC_CLIENT_ID`,
  `TBC_CLIENT_SECRET`, `TYPESAFE_API_KEY`.

Страница показывает это сгруппированными таблицами и поясняет, что значения
меняются в `/root/infohub/.env` с последующим деплоем.

## Ошибки и граничные случаи

- Не-админ или истёкший токен: layout уже перенаправляет на `/login`; API
  отвечает 401/403.
- Ошибка загрузки секции Dashboard не роняет страницу: каждый блок имеет свой
  `AdminState` с повтором.
- Сбой записи в журнал откатывает изменение; UI показывает ошибку, состояние не
  меняется.
- Пустой журнал — `AdminState empty`.

## Тестирование

Бэкенд (pytest, как в CI):

- unit: `record_admin_action` отвергает неизвестный `action`, обрезает `reason`;
- Postgres: запись создаётся вместе с изменением роли/статуса/активации;
  форсированная ошибка вставки не оставляет ни изменения, ни записи; UPDATE и
  DELETE журнала отвергаются триггером; `add_admin_audit_log.py` идемпотентен
  и его контрактный SHA совпадает с закреплённым в deploy-скрипте;
- `/admin/config`: ни одно значение ответа не совпадает со значением полей,
  чьё имя содержит `SECRET`, `PASSWORD`, `KEY` или `TOKEN`; эти поля
  представлены только булевыми флагами;
- `/admin/audit`: фильтры, пагинация, 403 для не-админа;
- `/admin/stats`: `billing.reconciliation_open` равен числу записей в полном
  списке `/billing/admin/reconciliation` на одних и тех же данных.

Фронтенд:

- `tsc`, lint;
- статическая проверка: в `frontend/app/admin/**` нет `style={{`;
- e2e-смоук каждой страницы админки на 1280 px и 390 px (RU и KA);
- обновлённые снимки `visual.spec.ts` для админки.

## Деплой

Новая таблица ставится шагом `deploy_production.sh` до старта бэкенда.
Rollback: код откатывается обычным деплоем предыдущего коммита; таблица
аддитивна и старому коду не мешает.
