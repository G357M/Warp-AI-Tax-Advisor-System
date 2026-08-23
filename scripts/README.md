# Scripts

Utility scripts for project management and operations.

## Available Scripts

### setup.py
Initialize the project and create database tables.

```bash
python scripts/setup.py
```

This script will:
- Verify database connection
- Create all required tables
- Create a default admin user (username: admin, password: changeme)

**Important**: Change the admin password after first setup!

## Future Scripts

### scrape.py
Run the InfoHub spider manually.

```bash
python scripts/scrape.py [--initial]
```

### migrate.py
Run database migrations.

```bash
python scripts/migrate.py
```

### reindex.py
Reindex all documents in the vector database.

```bash
python scripts/reindex.py
```

### backup_database.ps1
Create and rotate the owner-side PostgreSQL backup.

Configure credentials outside the repository with `PGPASSWORD`, `PGPASSFILE`
or the standard pgpass file. The script is non-interactive and emits a SHA-256
sidecar for the exact final artifact.

```powershell
./scripts/backup_database.ps1
```

### test_database_restore.sh
Plan and execute a SHA-pinned restore into an isolated disposable PostgreSQL
container. This never targets production resources.

```bash
./scripts/test_database_restore.sh --backup /restricted/path/infohub_ai.sql.gz
```

### manage_infohub_buildkit.py

Create and validate the production-only `docker-container` Buildx builder,
build/load the two explicit InfoHub images and bound only that builder's cache.
The prune command is dry-run-first and never targets the host-wide default
builder.

```bash
python3 scripts/manage_infohub_buildkit.py ensure
python3 scripts/manage_infohub_buildkit.py prune
python3 scripts/manage_infohub_buildkit.py prune --execute
```

Normal production builds invoke the `build` subcommand through
`scripts/deploy_production.sh`; operators should not run a global Docker prune.

### audit_production_storage.py

Read the root-filesystem headroom and aggregate cache usage for the isolated
InfoHub builder and the legacy shared `default` builder. The command only runs
`docker buildx du`; it has no prune, image-removal or volume-removal path.

```bash
python3 scripts/audit_production_storage.py
```

The default contract requires at least 25 GB free, at most 82% root usage, at
most 18 GB in `infohub-production-v1`, and observes a 60 GB alert ceiling for
the legacy shared cache. A healthy audit exits `0`; pressure exits `1`; an
unmeasurable state exits `2`. All cases emit one aggregate
`PRODUCTION_STORAGE_AUDIT=` JSON line. The nightly runner forwards only that
line to the existing Telegram alert path and never cleans the shared builder.

Threshold overrides are validated through
`INFOHUB_STORAGE_MIN_FREE_SPACE`, `INFOHUB_STORAGE_MAX_USED_PERCENT`,
`INFOHUB_PROJECT_CACHE_MAX_USED_SPACE` and
`INFOHUB_LEGACY_CACHE_OBSERVATION_CEILING`. The project builder override reuses
the restricted `INFOHUB_BUILDX_BUILDER` name.

### import_decision_facts_review_workbook.py

Convert a protected expert-review XLSX worksheet into the exact CSV contract
used by the decision-facts validator. The command is dry-run-first, rejects
formulas, macros, external relationships and non-text cells, and verifies every
immutable column against `review_bundle.json`. It performs no database or LLM
work.

```bash
python3 backend/scripts/import_decision_facts_review_workbook.py \
  --bundle /restricted/review_bundle.json \
  --workbook /restricted/duplicate_groups.working.xlsx \
  --review-type duplicate-groups
```
