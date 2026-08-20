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
