# RAG v2 DB enablement

This is the minimal path to run the deterministic RAG v2 locator evaluation
against a connected database.

## What was prepared

- `requirements-rag_v2_db.txt` — minimal DB dependency
- `scripts/prepare_rag_v2_db_mode.sh` — bootstrap/probe/eval helper
- `backend/evaluation/rag_v2_live_corpus_set.json` — balanced RU/EN/KA live suite
- `backend/scripts/evaluate_rag_v2_live_corpus.py` — read-only evaluator

## Default behavior

The helper script sets:

- `INFOHUB_V2_BACKEND_MODE=db`
- `INFOHUB_DATABASE_URL` from an already configured `INFOHUB_DATABASE_URL` or
  `DATABASE_URL`

The script deliberately has no embedded database URL or password. Configure one
of these variables through the environment or the production container before
running it.

## Step 1. Install DB dependency

```bash
cd /root/infohub
export INFOHUB_DATABASE_URL='postgresql://USER:PASSWORD@HOST:5432/DATABASE'
python3 -m pip install -r requirements-rag_v2_db.txt
```

Or via helper:

```bash
cd /root/infohub
export INFOHUB_DATABASE_URL='postgresql://USER:PASSWORD@HOST:5432/DATABASE'
./scripts/prepare_rag_v2_db_mode.sh --install-deps --no-eval
```

## Step 2. Probe DB connectivity

```bash
cd /root/infohub
export INFOHUB_DATABASE_URL='postgresql://USER:PASSWORD@HOST:5432/DATABASE'
./scripts/prepare_rag_v2_db_mode.sh --no-eval
```

Expected success shape:

```json
{
  "mode": "db",
  "has_database_url": true,
  "driver": "psycopg",
  "connectable": true,
  "error": null
}
```

## Step 3. Run live-corpus eval

```bash
cd /root/infohub
export INFOHUB_DATABASE_URL='postgresql://USER:PASSWORD@HOST:5432/DATABASE'
./scripts/prepare_rag_v2_db_mode.sh
```

This will:

1. probe DB backend status,
2. require a genuinely connectable DB backend,
3. run 21 balanced RU/EN/KA locator contracts,
4. save corpus counts, the deployed commit, per-language metrics and failures.

The evaluator disables `semantic_search`, so it does not translate through an
LLM, generate answers or write to the database. Answer-generation quality stays
covered by the separate nightly canary.

On production, use the already configured container instead of exporting a URL
on the host:

```bash
cd /root/infohub
docker exec infohub-backend python /app/scripts/evaluate_rag_v2_live_corpus.py \
  --commit "$(git rev-parse HEAD)" \
  --output /tmp/rag_v2_live_corpus_report.json
```

## Reports

- local helper: `reports/rag_v2_live_corpus_latest.json`
- production container: `/tmp/rag_v2_live_corpus_report.json`
- accepted historical baselines: `evaluation/baselines/`

The older `scripts/run_rag_v2_shadow_eval.py` remains a fixture-oriented
diagnostic. It is not the versioned production baseline and is not used by this
helper.
