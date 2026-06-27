# RAG v2 DB enablement

This is the minimal path to switch the local `backend/rag_v2` shadow-eval from fixtures to DB-backed mode.

## What was prepared

- `requirements-rag_v2_db.txt` — minimal DB dependency
- `scripts/prepare_rag_v2_db_mode.sh` — bootstrap/probe/eval helper
- `scripts/run_rag_v2_shadow_eval.py` — live-aware shadow eval

## Default behavior

The helper script sets:

- `INFOHUB_V2_BACKEND_MODE=db`
- `INFOHUB_DATABASE_URL=postgresql://infohub_user:xcX88l6XiMs-jDK@localhost:5432/infohub_ai`

You can override both through environment variables.

## Step 1. Install DB dependency

```bash
cd /root/.openclaw/workspace
python3 -m pip install -r requirements-rag_v2_db.txt
```

Or via helper:

```bash
cd /root/.openclaw/workspace
./scripts/prepare_rag_v2_db_mode.sh --install-deps --no-eval
```

## Step 2. Probe DB connectivity

```bash
cd /root/.openclaw/workspace
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

## Step 3. Run live-aware shadow eval

```bash
cd /root/.openclaw/workspace
./scripts/prepare_rag_v2_db_mode.sh
```

This will:

1. probe DB backend status,
2. run fixture shadow-eval,
3. include live cases automatically when DB is truly connectable.

## Reports

- `reports/rag_v2_shadow_eval_report.json`
- `reports/rag_v2_shadow_eval_summary.md`

## Current blocker in this environment

At preparation time, the script worked but reported:

- db mode enabled,
- database URL present,
- DB driver missing (`psycopg or psycopg2 is required for db mode`).

So the next real execution step is simply dependency installation, then rerun the helper.
