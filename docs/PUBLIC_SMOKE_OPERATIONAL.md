# Public Smoke Operational Workflow

## Fast path

```bash
make smoke-public
make smoke-public-core
make smoke-public-multilang
make smoke-public-multilang-core
make smoke-public-api
make smoke-public-both
```

## Purpose

This note separates two different public-surface checks for `tax-advisor.ge`:

1. **Browser-path smoke** — answers real public/browser traffic quality.
2. **API-client smoke** — checks whether Cloudflare blocks non-browser clients (currently expected).

These must not be mixed, otherwise Cloudflare `1010` can look like a false production outage.

## Canonical smoke for public path

Use browser-like external smoke as the default truth source for public availability/quality.

### Recommended commands

Simple wrapper:

```bash
scripts/run_public_smoke.sh browser
scripts/run_public_smoke.sh browser-core
scripts/run_public_smoke.sh browser-multilang
scripts/run_public_smoke.sh browser-multilang-core
scripts/run_public_smoke.sh api
scripts/run_public_smoke.sh both
```

Direct trimmed watch:

```bash
python3 scripts/run_public_stability_watch.py \
  --url https://tax-advisor.ge/api/v1/public/query \
  --profile trimmed \
  --repeats 1
```

Direct core watch:

```bash
python3 scripts/run_public_stability_watch.py \
  --url https://tax-advisor.ge/api/v1/public/query \
  --profile core \
  --repeats 1
```

Make target:

```bash
make smoke-public-core
```

## Multilingual public smoke

To verify real public behavior across **Russian, English, and Georgian**, use the multilingual profiles.

### Recommended commands

```bash
make smoke-public-multilang
make smoke-public-multilang-core
```

Wrapper form:

```bash
scripts/run_public_smoke.sh browser-multilang
scripts/run_public_smoke.sh browser-multilang-core
```

Direct form:

```bash
python3 scripts/run_public_stability_watch.py \
  --url https://tax-advisor.ge/api/v1/public/query \
  --profile multilingual-trimmed \
  --repeats 1
```

### Query file format

Multilingual query files can declare language per line:

```text
[ru] Что говорит статья 168 Налогового кодекса?
[en] What does Article 168 of the Tax Code say?
[ka] რა წერია საქართველოს საგადასახადო კოდექსის 168-ე მუხლში?
```

The watch script sends each request with its own `language` field and reports `request_language` plus a `query_label` like `[en] What does Article 168...`.

### Important behavior

For **external URLs**, the script now defaults to:

- `client_profile=browser`
- browser-like headers (`User-Agent`, `Origin`, `Referer`)
- automatic respect for `x-ratelimit-*`

This is intentional. It makes the external smoke reflect the real browser/public path instead of a Python-script signature that Cloudflare may block.

## Current Cloudflare policy decision

Current default decision: **leave non-browser clients blocked** unless there is an explicit product need to open `/api/v1/public/query` beyond browser traffic.

Reason:
- browser/public path is healthy,
- API-client `1010` is currently a controlled policy outcome,
- opening the path wider should be a deliberate Cloudflare/WAF change, not an accidental side effect.

## Separate API-client negative check

Use this to verify Cloudflare policy against non-browser clients.

Wrapper form:

```bash
scripts/run_public_smoke.sh api
```

Direct form:

```bash
python3 scripts/run_public_stability_watch.py \
  --url https://tax-advisor.ge/api/v1/public/query \
  --queries-file scripts/public_canary_queries_trimmed.txt \
  --client-profile api \
  --repeats 1
```

### Expected result today

- `policy_block: true`
- Cloudflare body contains `error code: 1010`
- `expected_outcome_ok: true`

This is a **policy signal**, not a product-quality failure.

## Result interpretation

### Browser profile

Healthy result:

- `success: true`
- `expected_outcome_ok: true`
- `weak_answer: false`

Example browser result excerpt:

```json
{
  "client_profile": "browser",
  "http_status": 200,
  "success": true,
  "expected_outcome_ok": true,
  "policy_block": false,
  "retrieved_count": 1
}
```

For multilingual profiles, also expect:

- `request_language` matches the query file prefix
- response text is in the same language as the request
- article-style lookups in Georgian resolve to the correct article instead of a false no-answer
- core multilingual profile covers canonical article lookup, point lookup, named document summary, dispute lookup, local regulation, and amendment tracking

### API profile

Healthy result under current policy:

- `policy_block: true`
- `expected_outcome_ok: true`

Example API-policy result excerpt:

```json
{
  "client_profile": "api",
  "http_status": 403,
  "success": false,
  "expected_outcome_ok": true,
  "policy_block": true,
  "error_body": {"raw_body": "error code: 1010"}
}
```

Unexpected result examples:

- browser profile gets widespread `403 1010` -> investigate Cloudflare/WAF pathing
- browser profile gets `200` but `weak_answer: true` -> retrieval/answer quality issue
- api profile gets `200` unexpectedly -> Cloudflare policy changed
- api profile gets transport failure -> infra/path issue, not policy confirmation

## Operational rule

- Treat **browser-profile external smoke** as the public production canary.
- Treat **api-profile smoke** as a separate Cloudflare policy monitor.
- Do **not** call API-profile `1010` a production outage unless the product is explicitly supposed to support non-browser clients.

## Overrides

If needed, defaults can be overridden:

- `--client-profile browser|api|auto`
- `--no-browser-like-defaults`
- `--ignore-rate-limit`
- `--user-agent ...`
- `--origin ...`
- `--referer ...`
