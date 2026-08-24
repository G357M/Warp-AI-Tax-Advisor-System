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
mode `none`, no published ports, no host bind mounts and no production volumes.
The image-declared PostgreSQL data volume must be newly created and anonymous.
The drill validates the dump, restores it with fail-fast semantics, requires all
current critical tables, checks document/chunk/fact counts, orphan references,
foreign-key validation and the pgvector extension, records RPO/RTO, then removes
the temporary container and its ephemeral volume on every exit. It never
connects to or names the production database container or its volumes. Evidence
targets are mode `0600` and are never overwritten. Schema-v2 evidence records
the host-bind, production-volume and ephemeral-volume facts separately.

The first full production-host drill passed on 2026-08-22 against the protected
pre-auth-migration custom dump
`infohub_ai_pre_auth_20260822T114300Z-052f974.dump` (2,802,237,970 bytes,
SHA-256 `c54e5cdf8738d150d6cccb54dd1c66fcb7859bb0c31966a5f7f2e673e4ff921c`).
It restored 15,140 documents, 275,976 chunks, 11,370 decision facts and 2,986
decision links in 699 seconds. The recorded RPO was 1,165 seconds; every
integrity check passed and the disposable container was removed. The mode-600
evidence remains at
`/root/infohub/.state/database-restore-drills/database_restore_drill_20260822T120700Z_052f974.json`
with SHA-256
`288ef3308ea36bab6538c793848111333aac08e0d298ce14a3963643dd0132c0`.
This proves recovery from that server-side dump only.

The newest weekly off-site copy held on the owner's computer was tested on
2026-08-22. The exact custom dump `infohub_ai-2026-08-17.dump` is
2,800,328,054 bytes, has original mtime `2026-08-17T12:52:16Z` and SHA-256
`cca73b4da74249775e376da07e6613eeb81d5ee50fd77968b700f4e1645b628d`.
It was transferred as a `.partial`, re-hashed before promotion and restored in
the same isolated server-side drill because Docker Desktop did not have enough
safe system-disk headroom for the expanded database. The restore passed in 695
seconds with an RPO of 453,971 seconds: 15,113 documents, 275,582 chunks,
11,353 decision facts and 2,985 decision links, with no missing critical tables,
orphans or unvalidated foreign keys and with pgvector present. The mode-600
evidence remains at
`/root/infohub/.state/database-restore-drills/offsite_restore_drill_20260822T185827Z_612f3c4.json`
with SHA-256
`c6a6884d302797ef156513ce0792bee9dcc5bb781fdb734523cfce8044d7e8e7`.
The temporary uploaded copy and restored volume were removed after validation;
the owner's original off-site file was not modified. A separate provider-level
Hetzner recovery was subsequently completed as recorded below.

Git Bash on Windows is supported by the restore script. It converts the
off-site host path with `cygpath` while preventing MSYS from rewriting `/tmp`
paths passed to Docker. Do not mount the backup into the test container: the
copy is deliberate evidence that the standalone off-site artifact is readable.
The PostgreSQL image creates its own anonymous data volume; cleanup uses
`docker rm -v` so that disposable restored data cannot accumulate.

### Hetzner provider-level restore evidence and future drill boundary

Seeing a completed snapshot in the Hetzner panel proves provider retention, not
application recovery. A complete provider-level drill requires a new temporary
server created from one specifically recorded snapshot. It is a separate,
billable operation and must not be run without explicit approval.

For that drill:

1. Record the source server, snapshot ID, creation time and status from the
   provider panel.
2. Create a uniquely named temporary server from that exact snapshot with a
   pre-attached firewall: SSH only from the operator IP, no public application
   ports and no outbound traffic. Do not change production DNS.
3. Prevent scheduled jobs and application containers from starting until their
   targets have been reviewed. Never attach the drill host to a production
   Docker network or disconnect independently managed services such as the
   Plausible instance serving `stats.modern-travel.ge`.
4. Verify the filesystem, repository commit, environment/configuration files,
   PostgreSQL volume and an isolated local health check. Record provider RPO,
   boot/application RTO and hashes/counts without copying secrets into Git.
5. After evidence is reviewed, request confirmation immediately before
   destroying the temporary server.

The first provider-level drill passed on 2026-08-23 using Hetzner automatic
backup image `423119703`, created at `2026-08-22T18:28:06Z` from production
server `120694722`. No manual snapshot existed; the automatic backup is the
exact provider image proven by this exercise. It booted as disposable CPX32
server `163175971` behind firewall `11504939`, with SSH as the only inbound
service from the operator address, no normal egress, no IPv6/private network and
no DNS change. Production and the independently managed Plausible service were
not changed.

The restored filesystem, repository commit, Docker volumes and PostgreSQL 15.16
data were present. PostgreSQL reported 15,140 documents, 275,976 chunks, 11,370
decision facts and 2,986 decision links, with no invalid/unready indexes; the
frontend passed local HTTPS and the 5.4 GB embedding cache loaded offline with
dimension 768. The fully isolated backend cold start exposed a pre-existing Hub
metadata request before Uvicorn bind. That finding was subsequently closed by
the cache-only loader, health contract and deployment preflight described in
the ML runtime section below.

During the drill, a read-only filesystem was mistakenly remounted while adding
temporary systemd masks. The directory-entry damage was limited to the
disposable clone, repaired with offline `e2fsck -fy`, and followed by a clean
read-only five-pass `e2fsck`. Neither the source server nor backup image was
modified. After evidence capture, server `163175971`, its primary IPs, firewall
`11504939` and temporary SSH key `codex-restore-drill-20260823` were deleted;
cleanup completed at `2026-08-22T21:48:13Z`.

The ignored operator evidence is
`.state/hetzner-restore-drills/20260823T013921+04/evidence.json`, SHA-256
`ab804423463fe8e9424d30f4c2352b87e89caf133ff2f14309f42ea10324d59a`.
It is operational evidence, not a file to add to Git. Future provider drills
must repeat the isolated, explicitly approved procedure above and create new
evidence rather than overwriting this record.

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

### Cache-only embedding startup and readiness audit

Production Compose sets `EMBEDDING_ALLOW_DOWNLOAD=false`. The loader resolves a
local directory or Hugging Face snapshot with `local_files_only=True` and fails
closed if the cache is absent or cannot be loaded. Root health returns `503`
when embeddings are unavailable; both root and public health expose only the
non-sensitive model source (`cache`, `local_path` or `unavailable`).

Every deployment runs the versioned readiness audit before replacing the
backend. The audit forces Hugging Face/Transformers offline mode, requires
production/no-debug policy and CPU-only PyTorch, resolves the same local model
source, then hashes a deterministic bounded manifest of the complete snapshot.
It rejects missing config/modules/tokenizer/weight assets, broken or escaping
symlinks, more than 2,048 files or more than 16 GiB. It runs fixed KA/RU/EN
probes twice and checks row count, configured dimension, finite non-zero vectors
and repeatability within `1e-6`. The only database operation is `SELECT 1`; no
LLM, external network call or PostgreSQL write is permitted.

Run the same read-only plan manually against the deployed image/cache:

```bash
cd /root/infohub
AUDIT_COMMIT="$(git rev-parse --short=12 HEAD)"
docker compose run --rm --no-deps backend \
  python scripts/audit_production_readiness.py --commit "$AUDIT_COMMIT"
```

The `PRODUCTION_READINESS_AUDIT` line contains the content-addressed cache hash,
file count and byte count. To retain evidence, first create a restricted host
directory, then repeat only that exact scope into a new file:

```bash
install -d -m 0700 /root/infohub/.state/production-readiness
AUDIT_ID="$(date -u +%Y%m%dT%H%M%SZ)-$(git rev-parse --short HEAD)"
docker compose run --rm --no-deps \
  -v /root/infohub/.state/production-readiness:/evidence \
  backend python scripts/audit_production_readiness.py \
  --commit "$(git rev-parse --short=12 HEAD)" \
  --execute \
  --output "/evidence/${AUDIT_ID}.json" \
  --expected-cache-sha256 SHA256_FROM_PLAN \
  --expected-cache-files FILES_FROM_PLAN \
  --expected-cache-bytes BYTES_FROM_PLAN
```

The writer refuses a changed scope, insecure evidence directory or existing
target and creates mode-`0600` JSON. It records relative cache filenames and
content hashes, never model contents, credentials, legal documents or probe
text. Keep it under ignored `.state/`; do not commit it.

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

## Project-scoped BuildKit cache

Production builds never use or prune the host's active `default` builder. The
deployment helper creates `infohub-production-v1` with the isolated
`docker-container` driver, builds and loads only the explicit
`infohub-backend` and `infohub-frontend` images, then applies retention only to
that named builder. It never passes `--use`, so unrelated projects keep their
existing builder selection.

Review the exact dry-run plan without deleting cache:

```bash
cd /root/infohub
python3 scripts/manage_infohub_buildkit.py ensure
python3 scripts/manage_infohub_buildkit.py prune
```

The defaults keep at most 18 GB of project cache, reserve 6 GB and target at
least 25 GB of free host space. Apply the printed named-builder policy with:

```bash
python3 scripts/manage_infohub_buildkit.py prune --execute
```

`scripts/deploy_production.sh` performs the same bounded prune after every
successful image build and attempts it after a failed build. An existing
builder with the same name but any driver other than `docker-container` is a
hard failure before image replacement. Overrides are limited to validated
`INFOHUB_BUILDX_BUILDER`, `INFOHUB_BUILDKIT_MAX_USED_SPACE`,
`INFOHUB_BUILDKIT_RESERVED_SPACE` and `INFOHUB_BUILDKIT_MIN_FREE_SPACE`.

The legacy cache already held by the shared `default` builder remains outside
this policy. Do not run global `docker builder prune` or `docker system prune`
automatically: it may remove cache or images owned by other projects. Review
and retire that legacy cache only as a separate host-wide maintenance action.

### Nightly storage-pressure audit

The nightly runner executes a read-only storage audit before ingest:

```bash
cd /root/infohub
python3 scripts/audit_production_storage.py
```

It measures root filesystem headroom and aggregate cache bytes from
`docker buildx du --format json` for the bounded `infohub-production-v1`
builder and the shared `default` builder. It never returns cache descriptions
in its machine summary and has no prune, image-removal or volume-removal code.
The default thresholds are 25 GB minimum free space, 82% maximum root usage,
18 GB maximum project cache and a 60 GB observation ceiling for the legacy
cache. A pressure or measurement failure sends the single aggregate
`PRODUCTION_STORAGE_AUDIT=` line through the existing Telegram path; a healthy
run sends no message and all outcomes leave the primary scraper exit unchanged.

The first read-only inventory on 2026-08-23 measured 54.26 GB in the legacy
builder. Four reclaimable, non-shared records totalling 34.616 GB were old
InfoHub `pip install --no-cache-dir -r requirements-production.txt` layers;
another 3.811 GB matched the previous InfoHub CPU-only virtualenv/copy chain.
This attribution is evidence for a later exact host-maintenance decision, not
permission for automatic global prune. The independent Plausible service and
its images, containers, networks and volumes remain outside every InfoHub
cleanup policy.

### Exact-ID legacy cache retirement

Use the dedicated retirement tool only for records already attributed through
the read-only inventory. Pass dependency roots as `--record-id` and every
reviewed direct `[6/6] COPY . .` leaf as `--dependent-record-id`. A dry-run
re-inspects every exact ID and refuses a different description, parent, type,
mutability, shared/reclaimable state, missing timestamp or invalid size:

```bash
cd /root/infohub
python3 scripts/retire_infohub_legacy_buildkit.py \
  --record-id EXACT_REVIEWED_ROOT_ID \
  --dependent-record-id EXACT_REVIEWED_COPY_LEAF_ID
```

Record the emitted `record_count`, `total_bytes` and `plan_sha256`. After code
review and green CI, repeat the identical IDs and require all three values for
the mutation:

```bash
python3 scripts/retire_infohub_legacy_buildkit.py \
  --record-id EXACT_REVIEWED_ROOT_ID \
  --dependent-record-id EXACT_REVIEWED_COPY_LEAF_ID \
  --execute \
  --expected-record-count 2 \
  --expected-total-bytes EXACT_DRY_RUN_BYTES \
  --expected-plan-sha256 EXACT_DRY_RUN_SHA256
```

The execution issues one `docker buildx prune` per exact ID against the fixed
`default` builder, with additional `inuse!=true`, `shared!=true`,
`mutable!=true`, `immutable!=false`, `type=regular` and InfoHub
dependency-description regexp filters. These negative boolean selectors match
the installed Buildx behavior; equality to `false` produces a safe no-op. The
tool retries a transient exact-ID no-op at most three times, revalidates the
complete reviewed metadata before every attempt and then requires every exact
ID to be absent. COPY leaves must have exactly one parent in the reviewed root
set; roles and parent IDs are plan-hashed, and leaves execute before roots. The
tool never discovers or adds descendants automatically. Stop on any changed
plan or metadata; do not fall back to a description-only, age-only or global
prune. Re-run the storage audit and application/Plausible identity checks after
the operation.

The separate rollback-image retention was applied after that inventory. It
removed twelve exact obsolete `infohub/backend:rollback-*` and
`infohub/frontend:rollback-*` tags while retaining the newest three of each.
Because the deleted images shared most layers, it returned about 1 GB rather
than their summed virtual sizes. No BuildKit cache, active image, volume or
Plausible resource was touched.

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

### Full unresolved decision-facts review

The sampled handoff above is suitable for calibration, but it does not close
the complete legal-review backlog. The full workflow exports every unique fact
row in the outcome-alignment, non-simple article-reference and unclear-outcome
queues, plus every member of every duplicate-number candidate group. It is
also read-only/no-LLM. Its `exact`, `likely` and `ambiguous` labels are
comparison signals, never legal findings and never deletion instructions.

First run a connected aggregate-only plan inside the deployed backend:

```bash
cd /root/infohub
REVIEW_COMMIT="$(git rev-parse HEAD)"
docker exec infohub-backend python \
  /app/scripts/export_decision_facts_expert_review.py \
  --commit "$REVIEW_COMMIT"
```

The plan prints only the queue counts, duplicate classes/member counts and a
source snapshot SHA-256. Materialize exactly that snapshot to a new container
path by copying all four expected values from the plan:

```bash
REVIEW_ID="$(date -u +%Y%m%dT%H%M%SZ)-$(git rev-parse --short HEAD)"
CONTAINER_EXPORT="/tmp/decision_facts_full_expert_review_${REVIEW_ID}.json"
docker exec infohub-backend python \
  /app/scripts/export_decision_facts_expert_review.py \
  --commit "$(git rev-parse HEAD)" \
  --execute \
  --output "$CONTAINER_EXPORT" \
  --expected-review-items REVIEW_ITEMS \
  --expected-duplicate-groups DUPLICATE_GROUPS \
  --expected-duplicate-members DUPLICATE_MEMBERS \
  --expected-snapshot-sha256 SNAPSHOT_SHA256
install -d -m 0700 /root/infohub/.state
HOST_EXPORT="/root/infohub/.state/decision_facts_full_expert_review_${REVIEW_ID}.json"
docker cp "infohub-backend:${CONTAINER_EXPORT}" "$HOST_EXPORT"
chmod 0600 "$HOST_EXPORT"
```

The execute step fails if the live source changed after the plan, any count is
different or the output already exists. Build the protected worksheets with a
second dry-run/exact-execute pair:

```bash
python3 backend/scripts/build_decision_facts_full_review_bundle.py \
  --input "$HOST_EXPORT"

python3 backend/scripts/build_decision_facts_full_review_bundle.py \
  --input "$HOST_EXPORT" \
  --output-dir ".state/decision-facts-full-expert-review/${REVIEW_ID}" \
  --execute \
  --expected-report-sha256 REPORT_SHA256_FROM_PLAN \
  --expected-review-items REVIEW_ITEMS \
  --expected-duplicate-groups DUPLICATE_GROUPS \
  --expected-duplicate-members DUPLICATE_MEMBERS
```

Keep `review_bundle.json` and `duplicate_members.csv` unchanged. Make new
working copies of the two editable worksheets, retain mode `0600`, and record
the exact official-source locator, rationale, confidence, reviewer and UTC
timestamp for every completed row. Corrections to `outcome`/`in_favor` and all
duplicate exclusions require a distinct second reviewer. An inaccessible
source must be recorded as such; it is not evidence that the extracted value
is correct or incorrect.

Do not manually copy reviewed Excel cells back into CSV. Upload the working
`.xlsx` as a new mode-`0600` regular file, then run the stdlib-only importer.
It reads text cells only, rejects formulas/macros/external relationships,
verifies all immutable columns against `review_bundle.json`, normalizes JSON
and performs no database or LLM work. First capture the exact hashes and row
count:

```bash
REVIEW_DIR=".state/decision-facts-full-expert-review/${REVIEW_ID}"
python3 backend/scripts/import_decision_facts_review_workbook.py \
  --bundle "$REVIEW_DIR/review_bundle.json" \
  --workbook "$REVIEW_DIR/duplicate_groups.working.xlsx" \
  --review-type duplicate-groups
```

Materialize a new validator-ready CSV only with every value from that plan:

```bash
python3 backend/scripts/import_decision_facts_review_workbook.py \
  --bundle "$REVIEW_DIR/review_bundle.json" \
  --workbook "$REVIEW_DIR/duplicate_groups.working.xlsx" \
  --review-type duplicate-groups \
  --execute \
  --output "$REVIEW_DIR/duplicate_groups.imported-v1.csv" \
  --expected-bundle-sha256 BUNDLE_SHA256 \
  --expected-workbook-sha256 WORKBOOK_SHA256 \
  --expected-output-sha256 OUTPUT_SHA256 \
  --expected-rows DUPLICATE_GROUPS
```

Use `--review-type review-items` for the fact worksheet. If its sheet label is
not `review_items completed`, pass the exact label with `--sheet-name`. The
importer preserves pending rows as pending: prefilled evidence or a technical
duplicate proposal is not converted into an expert signature. A completed
duplicate exclusion still requires a distinct second reviewer.

The validator may be run during the review without `--require-complete`. For
the final pass, require every row and first capture its exact input hash:

```bash
REVIEW_DIR=".state/decision-facts-full-expert-review/${REVIEW_ID}"
python3 backend/scripts/validate_decision_facts_expert_review.py \
  --bundle "$REVIEW_DIR/review_bundle.json" \
  --review-items "$REVIEW_DIR/review_items.completed.csv" \
  --duplicate-groups "$REVIEW_DIR/duplicate_groups.completed.csv" \
  --require-complete
```

Only after that passes may the proposal manifest be materialized with the
reported `input_sha256` and completed counts:

```bash
python3 backend/scripts/validate_decision_facts_expert_review.py \
  --bundle "$REVIEW_DIR/review_bundle.json" \
  --review-items "$REVIEW_DIR/review_items.completed.csv" \
  --duplicate-groups "$REVIEW_DIR/duplicate_groups.completed.csv" \
  --require-complete \
  --execute \
  --output "$REVIEW_DIR/correction_proposals.json" \
  --expected-input-sha256 INPUT_SHA256 \
  --expected-complete-review-items REVIEW_ITEMS \
  --expected-complete-duplicate-groups DUPLICATE_GROUPS
```

`correction_proposals.json` is deliberately non-executable:
`postgresql_writes_allowed=false`, `apply_supported=false` and
`proposal_only=true`. Applying any accepted legal correction remains a
separate, reviewed change with its own backup, migration/rollback plan and
post-change quality gate. Full exports, worksheets and proposal manifests are
operational evidence and must never enter Git.

#### Automated official-API duplicate triage

Manual opening of every candidate is not required. The stdlib-only verifier
can compare the current official InfoHub API records without connecting to
PostgreSQL or an LLM. Dry-run makes no network calls. Start with the exact and
likely classes and capture the exact protected-bundle hash and counts:

```bash
cd /root/infohub
REVIEW_DIR=".state/decision-facts-full-expert-review/REVIEW_ID"
python3 backend/scripts/verify_infohub_duplicate_candidates.py \
  --bundle "$REVIEW_DIR/review_bundle.json" \
  --candidate-class exact \
  --candidate-class likely
```

Execute only that pinned scope into a new operational directory:

```bash
VERIFY_ID="$(date -u +%Y%m%dT%H%M%SZ)-$(git rev-parse --short HEAD)"
python3 backend/scripts/verify_infohub_duplicate_candidates.py \
  --bundle "$REVIEW_DIR/review_bundle.json" \
  --candidate-class exact \
  --candidate-class likely \
  --execute \
  --output-dir ".state/infohub-duplicate-verification/${VERIFY_ID}" \
  --expected-input-sha256 INPUT_SHA256_FROM_PLAN \
  --expected-groups GROUPS_FROM_PLAN \
  --expected-members MEMBERS_FROM_PLAN
```

The verifier accepts only fixed HTTPS `infohub.rs.ge/{language}/workspace/
document/{uuid}` URLs and constructs requests against the fixed official
`infohubapi.rs.ge/api` base. Request concurrency, rate, timeout, response size
and retries are bounded by a versioned contract. The mode-600 report stores
metadata, lengths, SHA-256 fingerprints and similarity values, never the legal
body text.

Use `duplicate_technical_triage.csv` for prioritization:

- `official_content_identical` means all current official normalized bodies
  and core identity fields match; it is eligible for efficient expert batch
  confirmation after source sampling;
- `official_content_high_overlap` requires matching identity fields, matching
  structured decision content, at least 100 body tokens and at least 0.95
  ordered-token similarity; it is placed in the shorter
  `duplicate_confirmation_queue.csv` for priority expert confirmation;
- `official_content_near_identical` and `same_content_identity_mismatch`
  require manual comparison;
- `official_content_differs` is not a duplicate conclusion, only evidence that
  the official bodies differ;
- `verification_incomplete` must be retried or checked manually.

Only normalized-body-equivalent `official_content_identical` groups receive deterministic
technical canonical/exclusion candidates. A high-overlap group does not,
because the expert must decide which non-identical publication is canonical.
The verifier cannot edit the expert worksheet, produce a legal verdict, create
a correction manifest or write/delete database rows. To verify every class,
omit both `--candidate-class` arguments and repeat the dry-run/exact-execute
pair into a different output directory.

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

## Account email verification and recovery

The additive auth migration runs automatically inside the reviewed production
deploy script before containers are replaced. It adds `email_verified_at`,
`session_version` and `auth_action_tokens`; on its first run only, all existing
accounts are marked verified. Re-running it never verifies later accounts.

Email delivery is intentionally off unless every required production setting
is present. Configure these values in `/root/infohub/.env` without committing
credentials:

```dotenv
EMAIL_DELIVERY_ENABLED=true
AUTH_PUBLIC_BASE_URL=https://tax-advisor.ge
SMTP_HOST=smtp.provider.example
SMTP_PORT=587
SMTP_USER=provider-user
SMTP_PASSWORD=provider-secret
SMTP_FROM=Tax Advisor <noreply@tax-advisor.ge>
SMTP_USE_TLS=true
SMTP_USE_SSL=false
```

Use exactly one transport mode: STARTTLS (normally port 587) or implicit SSL
(normally port 465). `SMTP_PASSWORD` is mandatory when `SMTP_USER` is set. The
production settings validator refuses incomplete, dual-TLS or non-HTTPS
configuration before the deployment mutates runtime containers.

Before setting `EMAIL_DELIVERY_ENABLED=true`, verify SPF/DKIM/DMARC with the
chosen provider and perform one registration, verification, password-reset and
old-session-revocation smoke flow using a dedicated test account. Never log or
store a raw action token; PostgreSQL contains only its SHA-256 digest. If email
delivery is disabled, registrations remain immediately usable and recovery
request endpoints return `503`.
