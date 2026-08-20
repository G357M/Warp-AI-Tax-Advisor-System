# Production operations

## Source of truth and deployment

The GitHub `main` branch is the versioned source of truth. Production runs from
`/root/infohub` on Hetzner. Deploy only with the repository script:

```bash
cd /root/infohub
./scripts/deploy_production.sh
```

The script refuses non-`main` and dirty tracked worktrees, fetches and merges
with `--ff-only`, validates Compose, preserves rollback image tags, builds both
application images, performs an isolated backend/DB preflight, validates Nginx,
recreates the required containers and checks the public health endpoint.
Untracked server-only diagnostic artifacts are preserved.

If a fast-forward changes the deploy script itself, the running old copy
re-executes the newly checked-out script before builds or container changes.
This ensures a new preflight or rollback guard applies on the deployment that
introduces it, rather than only on the following release.

## Origin TLS renewal

Nginx serves the ACME HTTP-01 path from `/root/infohub/certbot/www`, so Certbot
does not need to stop the production proxy. After deploying this configuration,
convert/renew the existing certificate once:

```bash
certbot certonly \
  --webroot \
  --webroot-path /root/infohub/certbot/www \
  --cert-name tax-advisor.ge \
  -d tax-advisor.ge \
  -d www.tax-advisor.ge \
  --non-interactive \
  --agree-tos \
  --force-renewal
```

The deploy hook installed by `deploy_production.sh` runs `nginx -t` and reloads
the running proxy after a successful renewal. Verify the timer and renewal path:

```bash
systemctl status certbot.timer
certbot renew --dry-run
openssl x509 -in /etc/letsencrypt/live/tax-advisor.ge/fullchain.pem -noout -dates
```

## Backups and restore evidence

Two independent backup layers are confirmed by the owner:

1. Hetzner snapshots/backups configured in the provider panel.
2. A weekly full database backup copied to the owner's computer.

The repository PowerShell backup helper never embeds a password. Its scheduler
must provide credentials through standard non-interactive libpq configuration
(`PGPASSWORD`, `PGPASSFILE` or the platform pgpass file). It writes to a
`.partial` file first, disables interactive password prompts and owner/ACL
statements, then atomically promotes the completed dump, optionally compresses
it and writes a SHA-256 sidecar for the restore drill.

Availability of backup files is not the same as proven recovery. At least once
per quarter, restore the newest database backup into an isolated PostgreSQL
instance, run basic document/chunk/fact counts and record the date and result.
Never test a restore over the production database.

The repository provides a dry-run-first isolated drill. Run the plan on the
host that holds the newest weekly backup:

```bash
./scripts/test_database_restore.sh \
  --backup /restricted/path/infohub_ai_YYYYMMDD.sql.gz
```

Review the reported filename, age, format and SHA-256. Execute only the exact
file and write a new evidence artifact in an existing restricted directory:

```bash
./scripts/test_database_restore.sh \
  --backup /restricted/path/infohub_ai_YYYYMMDD.sql.gz \
  --execute \
  --expected-sha256 SHA256_FROM_PLAN \
  --evidence /restricted/evidence/restore_drill_YYYY_QN.json
```

The PostgreSQL image must already exist locally; image pulls are deliberately
not implicit. The drill creates one unique ephemeral container with network
mode `none`, no published ports and no mounted volumes. It validates the dump,
restores it with fail-fast semantics, requires all current critical tables,
checks document/chunk/fact counts, orphan references, foreign-key validation
and the pgvector extension, records RPO/RTO, then removes the temporary
container on every exit. It never connects to or names the production database
container. Evidence targets are mode `0600` and are never overwritten.

## Logs

Docker services use bounded JSON logs (five files of 10 MB per service).
`/root/infohub/logs/cron.log` is rotated daily for 14 days. Scraper run logs keep
their existing 30-day retention in `run_scraper.sh`.

Install or refresh the host policy with:

```bash
install -m 0644 /root/infohub/ops/logrotate-infohub /etc/logrotate.d/infohub
logrotate --debug /etc/logrotate.d/infohub
```

The nightly runner invokes `scraper_alert.sh` through Bash, so an accidental
loss of its executable bit cannot silently disable Telegram failure alerts.
Post-ingest maintenance steps remain non-fatal to the primary scrape, but their
exit codes are collected and reported in one Telegram alert instead of being
discarded by output-truncation pipelines. The news-subtype query can be checked
without writes or LLM calls with:

```bash
docker exec infohub-backend python /app/scripts/classify_news_subtypes.py --check-pending
```

## Backend ML runtime

Production is CPU-only. The backend build installs the pinned PyTorch wheel
from the official `https://download.pytorch.org/whl/cpu` index before resolving
the rest of `requirements-production.txt`. The final image contains only the
virtual environment and runtime libraries; compiler and Git packages remain in
the discarded builder stage.

Both the Docker build and production deploy preflight fail unless the installed
PyTorch version has the `+cpu` suffix, reports no CUDA runtime and reports CUDA
as unavailable. This prevents a dependency refresh from silently restoring the
multi-gigabyte NVIDIA runtime on the CPU-only Hetzner host.

## Rollback image retention

Every deployment preserves the previous backend and frontend image under a
commit-addressed rollback tag. Review the bounded retention plan with:

```bash
./scripts/prune_infohub_rollbacks.sh
```

The default keeps the three newest main-branch rollback tags for each InfoHub
application image. It refuses to run if the active containers do not match the
current `:latest` images, protects unrecognized or non-main commits and never
touches volumes, current images or global Docker build cache. Apply only the
printed policy with:

```bash
./scripts/prune_infohub_rollbacks.sh --apply
```

BuildKit cache is shared by every project on the host and therefore remains
outside this automated policy. Review it separately before any global prune.

## Database credential rotation

Database URLs and passwords must come only from the environment. The RAG v2
adapter and helper scripts deliberately have no fallback credential. Rotate the
application role from the production repository with:

```bash
cd /root/infohub
./scripts/rotate_database_password.sh --check
./scripts/rotate_database_password.sh
```

The script verifies the existing backend connection and local PostgreSQL
administrative path, creates a mode-600 environment backup under the ignored
`.state/` directory, atomically updates `POSTGRES_PASSWORD`, changes the role
password, recreates only the backend, and checks both a fresh SQL connection and
the public health endpoint. A failed verification restores the previous role
password and environment automatically. After a successful rotation, verify the
independent weekly off-host backup job because it may use its own stored copy of
the database credential.

## Deterministic live-corpus RAG evaluation

Run the balanced RU/EN/KA locator suite inside the configured backend:

```bash
cd /root/infohub
docker exec infohub-backend python /app/scripts/evaluate_rag_v2_live_corpus.py \
  --commit "$(git rev-parse HEAD)" \
  --output /tmp/rag_v2_live_corpus_report.json \
  --baseline-output /tmp/rag_v2_live_corpus_baseline.json
```

This is a read-only retrieval check: `semantic_search` is explicitly disabled,
so the run does not invoke translation or answer-generation LLMs. The report
records corpus counts, suite hash, deployed commit, overall metrics,
per-language metrics and individual failures. Copy accepted reports into
`evaluation/baselines/` only from `--baseline-output`: that allowlist excludes
queries and document-level results. Keep the full report as an operational
artifact and do not silently replace a failed baseline.

The nightly runner executes this live-corpus check and the decision-facts
quality contract after post-ingest maintenance. Both are read-only and prohibit
LLM calls. Their latest full and aggregate reports are stored under
`/root/infohub/.state/` with mode `0600`; only the evaluators' aggregate
machine-summary line can reach Telegram. A healthy run sends no message. A
non-zero evaluator exit, missing summary or incomplete protected artifact sends
a quality-gate alert but does not replace the primary scraper exit code.

The four rolling operational files are:

```text
/root/infohub/.state/rag_v2_live_corpus_nightly_report.json
/root/infohub/.state/rag_v2_live_corpus_nightly_baseline.json
/root/infohub/.state/decision_facts_quality_nightly_report.json
/root/infohub/.state/decision_facts_quality_nightly_baseline.json
```

Before each run, the prior files move to the same names with a `.previous`
suffix. This keeps one recoverable generation while preventing an old report
from remaining at the current path when an evaluator or copy fails. Both
generations remain mode `0600`.

The bounded answer-safety suite remains manual because it invokes the provider;
it is deliberately not part of the nightly quality gates.

Run the exact shared no-LLM gate path manually without starting the scraper or
any provider-backed maintenance step:

```bash
cd /root/infohub
./run_quality_gates.sh
```

This command exits non-zero when either gate or its artifact handling fails.
The nightly wrapper records the same failure and alerts, but preserves the
primary scraper exit code.

## Bounded live answer-safety evaluation

Inspect the versioned execution plan first; this does not connect to the corpus
or invoke an LLM:

```bash
cd /root/infohub
docker exec infohub-backend python /app/scripts/evaluate_answer_safety_live.py
```

Run the accepted 12-case RU/EN/KA suite only with its exact reviewed ceiling:

```bash
docker exec infohub-backend python /app/scripts/evaluate_answer_safety_live.py \
  --execute \
  --max-llm-calls 12 \
  --commit "$(git rev-parse HEAD)" \
  --output /tmp/answer_safety_live_report.json \
  --baseline-output /tmp/answer_safety_live_baseline.json
```

The evaluator counts actual provider invocations across both translation and
answer generation and blocks the first invocation above the ceiling. It uses
the normal read-only retrieval paths and performs no PostgreSQL writes; the
normal Redis translation cache may be updated. The full report contains the
queries, answers and sources and must remain an operational artifact. Only the
aggregate `--baseline-output` allowlist is suitable for Git. This suite is not
scheduled automatically: changing its questions, thresholds or LLM ceiling
requires a reviewed commit first.

## Decision-facts quality and expert-review manifest

Validate the versioned plan without connecting to PostgreSQL:

```bash
cd /root/infohub
docker exec infohub-backend python /app/scripts/evaluate_decision_facts_quality.py
```

Run the read-only production audit and create separate operational/aggregate
artifacts:

```bash
docker exec infohub-backend python /app/scripts/evaluate_decision_facts_quality.py \
  --execute \
  --commit "$(git rev-parse HEAD)" \
  --output /tmp/decision_facts_quality_report.json \
  --baseline-output /tmp/decision_facts_quality_baseline.json
```

The evaluator performs no LLM calls and issues SELECT queries only. The full
report contains a deterministic review manifest with public document IDs,
titles and official URLs. Keep it server-side with restricted permissions; do
not put it in Git:

```bash
install -d -m 0700 /root/infohub/.state
docker cp infohub-backend:/tmp/decision_facts_quality_report.json \
  /root/infohub/.state/decision_facts_quality_report.json
chmod 0600 /root/infohub/.state/decision_facts_quality_report.json
```

Only the aggregate `--baseline-output` allowlist is suitable for versioning.
Passing structural metrics do not mean that the extracted legal outcome was
verified by a lawyer; the manifest exists specifically for that human review.

The anomaly manifest uses a deterministic per-category quota. This prevents a
large duplicate or unclear-outcome queue from hiding smaller categories such
as missing dates, missing decision numbers, outcome alignment or non-simple
article references. Build the legal-expert handoff from the current restricted
report in two steps. First capture the exact item count and report hash:

```bash
cd /root/infohub
python3 backend/scripts/build_decision_facts_review_bundle.py \
  --input .state/decision_facts_quality_nightly_report.json
```

Then materialize only that reviewed scope into a new directory:

```bash
python3 backend/scripts/build_decision_facts_review_bundle.py \
  --input .state/decision_facts_quality_nightly_report.json \
  --output-dir .state/decision-facts-expert-review/REVIEW_ID \
  --execute \
  --expected-items N \
  --expected-report-sha256 SHA256_FROM_PLAN
```

The command refuses symlink or group/world-readable input, refuses to overwrite
an existing output directory and writes JSON, UTF-8 CSV, instructions and
checksums with mode `0600` under a mode-`0700` directory. Spreadsheet formula
prefixes in source text are neutralized in CSV. The blank review columns use
only `correct`, `incorrect`, `not_applicable` or `unable_to_verify`; the bundle
must remain operational and must not be committed to Git. Copying it to a
reviewer is a separate owner-approved disclosure step.

Existing deterministic normalization defects can be inspected without writes:

```bash
docker exec infohub-backend python /app/scripts/repair_decision_fact_normalization.py
```

Apply only the exact fresh dry-run scope:

```bash
docker exec infohub-backend python /app/scripts/repair_decision_fact_normalization.py \
  --apply --expected-changed-rows N
```

This repair can clear non-positive amounts, deduplicate identical article
references and remove self-references. It never changes `raw_json`, so the
original extraction remains auditable. A v1 extraction backlog is separate and
requires bounded LLM calls; inspect it first with
`extract_decision_facts.py --check-pending`, then set both `--limit N` and
`--max-llm-calls N` to the exact reviewed count.

After a bounded extraction upgrade, compare the derived appeal-link scope
without exporting decision titles, numbers or dates:

```bash
docker exec infohub-backend python /app/scripts/link_decision_chains.py \
  --summary-only
```

Only run the destructive `--apply` rebuild after reviewing that aggregate
scope and the current `decision_links` count.
