# MCP-коннектор tax-advisor.ge для Claude

Приватный read-only MCP-эндпоинт внутри `infohub-backend`. Через него Claude
(claude.ai, Cowork, мобильное приложение, Claude Code) напрямую работает с
корпусом tax-advisor.ge.

## Инструменты

| Tool | Что делает | LLM-затраты бэкенда |
|---|---|---|
| `search_corpus(query, language="ka", limit=8, max_chars_per_chunk=4000)` | Retrieval-половина `RAGPipeline.process_query`: фрагменты, метаданные, `source_url`, проверенные `provision_links` Matsne | только перевод запроса, если он не на грузинском |
| `get_document(document_id, offset=0, max_chars=20000)` | Полный текст документа, постранично (`next_offset`) | нет |
| `get_official_provision(act, article)` | Проверенная ссылка на статью из реестров `rag_v2/official_*_provisions.json` и текст статьи из корпуса (`article_ref`) | нет |
| `ask_tax_advisor(question, language="ru")` | Тот же ответ, что `POST /api/v1/public/query`, вместе с evidence-контрактом | да, полный ответ |

Ни один инструмент не пишет в БД и не запускает ingestion.

## Безопасность

- Эндпоинт монтируется, только если задан `MCP_ACCESS_TOKEN` длиной не меньше 32 символов. Если токен пустой, `/mcp` не существует.
- Токен сверяется constant-time (`hmac.compare_digest`) из `Authorization: Bearer` или `X-MCP-Token`.
- Nginx принимает `https://tax-advisor.ge/mcp/<token>` (claude.ai принимает только URL) и передаёт токен в бэкенд заголовком `X-MCP-Token`. Путь при этом переписывается в `/mcp/`, поэтому токен не попадает в логи бэкенда и в labels Prometheus. Для обоих `location` выключен `access_log`.
- Включена защита от DNS rebinding: `MCP_ALLOWED_HOSTS` и Origin `claude.ai`.
- Действует общий rate limit бэкенда (`RATE_LIMIT_USER`).
- Ротация: новый токен в `.env` → `docker compose up -d backend` → обновить URL коннектора.

## Включение в production

```bash
# на сервере, /root/infohub
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # → токен
echo 'MCP_ACCESS_TOKEN=<токен>' >> .env
# дальше обычный релиз через scripts/deploy_production.sh (нужны новый образ backend с mcp==2.2.0 и nginx.conf)
```

Smoke-проверка:

```bash
curl -s https://tax-advisor.ge/mcp/<токен> \
  -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
  -H 'mcp-protocol-version: 2025-06-18' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | head -c 400
# без токена или с неверным токеном: 401 (/mcp/) или 404 от фронтенда (/mcp/<мусор>)
```

## Подключение

- **claude.ai / Cowork / мобильное приложение:** Settings → Connectors → Add custom connector → URL `https://tax-advisor.ge/mcp/<токен>`. Авторизацию оставить пустой.
- **Claude Code:**
  ```bash
  claude mcp add --transport http tax-advisor https://tax-advisor.ge/mcp/ \
    --header "Authorization: Bearer <токен>"
  ```

## Тесты

`backend/tests/test_mcp_server.py` проверяет авторизацию, Host-проверку, список инструментов, пагинацию, реальные реестры статей и нормализацию номеров статей. БД, модель и LLM для этих тестов не нужны.

## Ограничения v1

- `search_corpus` повторяет legacy-retrieval из `rag/pipeline.py` и не использует путь `rag_v2 live_runtime`. При изменении retrieval в `process_query` нужно синхронизировать `_retrieve_chunks` в `api/mcp_server.py`.
- `ask_tax_advisor` проходит через `process_public_query`, поэтому shadow-телеметрия записывает его как `/api/v1/public/query`.
- Исторические редакции (Temporal Legal Engine) не подключены: в публичных ответах они ещё не authoritative.
