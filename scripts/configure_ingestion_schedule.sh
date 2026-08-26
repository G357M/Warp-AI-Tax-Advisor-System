#!/bin/bash
# Safely reconcile the production cron entries for InfoHub ingestion.

set -euo pipefail

MODE="${1:---dry-run}"
if [ "$#" -gt 1 ] || { [ "$MODE" != "--dry-run" ] && [ "$MODE" != "--apply" ]; }; then
    echo "Usage: $0 [--dry-run|--apply]" >&2
    exit 2
fi
INFOHUB_DIR="/root/infohub"
STATE_DIR="$INFOHUB_DIR/.state/ingestion-cron-backups"
FULL_JOB="0 3 * * * $INFOHUB_DIR/run_scraper.sh >> $INFOHUB_DIR/logs/cron.log 2>&1"
REFRESH_JOB="17 9,15,21 * * * $INFOHUB_DIR/run_scraper.sh --ingest-only >> $INFOHUB_DIR/logs/cron.log 2>&1"
CURRENT_CRONTAB="$(crontab -l 2>/dev/null || true)"
PRESERVED_CRONTAB="$(printf '%s\n' "$CURRENT_CRONTAB" | grep -vF "$INFOHUB_DIR/run_scraper.sh" || true)"

echo "INFOHUB_INGESTION_CRON_PLAN={\"mode\":\"${MODE#--}\",\"full_daily_utc\":\"03:00\",\"refresh_utc\":[\"09:17\",\"15:17\",\"21:17\"],\"preserve_unrelated_entries\":true,\"singleton_lock\":true}"
printf '%s\n%s\n' "$FULL_JOB" "$REFRESH_JOB"

if [ "$MODE" = "--dry-run" ]; then
    exit 0
fi
if [ "$(id -u)" -ne 0 ]; then
    echo "Applying this schedule must run as root." >&2
    exit 2
fi

install -d -m 0700 "$STATE_DIR"
BACKUP_FILE="$STATE_DIR/crontab_$(date -u +%Y%m%dT%H%M%SZ).txt"
printf '%s\n' "$CURRENT_CRONTAB" > "$BACKUP_FILE"
chmod 0600 "$BACKUP_FILE"

CRON_INPUT="$(mktemp)"
trap 'rm -f "$CRON_INPUT"' EXIT
{
    if [ -n "$PRESERVED_CRONTAB" ]; then
        printf '%s\n' "$PRESERVED_CRONTAB"
    fi
    printf '%s\n%s\n' "$FULL_JOB" "$REFRESH_JOB"
} > "$CRON_INPUT"
crontab "$CRON_INPUT"

INSTALLED="$(crontab -l)"
printf '%s\n' "$INSTALLED" | grep -Fxq "$FULL_JOB"
printf '%s\n' "$INSTALLED" | grep -Fxq "$REFRESH_JOB"
echo "INFOHUB_INGESTION_CRON_APPLIED={\"backup\":\"$BACKUP_FILE\",\"verified\":true}"
