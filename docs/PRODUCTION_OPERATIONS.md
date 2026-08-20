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

Availability of backup files is not the same as proven recovery. At least once
per quarter, restore the newest database backup into an isolated PostgreSQL
instance, run basic document/chunk/fact counts and record the date and result.
Never test a restore over the production database.

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
  --output /tmp/rag_v2_live_corpus_report.json
```

This is a read-only retrieval check: `semantic_search` is explicitly disabled,
so the run does not invoke translation or answer-generation LLMs. The report
records corpus counts, suite hash, deployed commit, overall metrics,
per-language metrics and individual failures. Copy accepted reports into
`evaluation/baselines/`; do not silently replace a failed baseline.
