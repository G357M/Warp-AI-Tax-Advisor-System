#!/usr/bin/env bash

# Telegram alert for operational jobs (nightly DB backup, restore drill).
#
# Usage: ops_alert.sh <job> <message>
#
# Credentials come from /root/infohub/.env (TELEGRAM_BOT_TOKEN,
# TELEGRAM_CHAT_ID), same as scraper_alert.sh. Missing credentials or a
# failed send are logged, never fatal: the caller is already failing and the
# alert must not mask its exit code.

set -u

ENV_FILE="${INFOHUB_ENV_FILE:-/root/infohub/.env}"
JOB="${1:-ops job}"
MESSAGE="${2:-failed}"
HOST="$(hostname)"
NOW="$(date -u '+%Y-%m-%d %H:%M UTC')"

TELEGRAM_BOT_TOKEN=""
TELEGRAM_CHAT_ID=""
if [ -f "$ENV_FILE" ]; then
    TELEGRAM_BOT_TOKEN="$(grep -E '^TELEGRAM_BOT_TOKEN=' "$ENV_FILE" | tail -1 | cut -d= -f2- | tr -d '"'"'"' \r')"
    TELEGRAM_CHAT_ID="$(grep -E '^TELEGRAM_CHAT_ID='   "$ENV_FILE" | tail -1 | cut -d= -f2- | tr -d '"'"'"' \r')"
fi

text="🔴 InfoHub ${JOB} FAILED on ${HOST}
${MESSAGE}
${NOW}"

if [ -z "$TELEGRAM_BOT_TOKEN" ] || [ -z "$TELEGRAM_CHAT_ID" ]; then
    echo "[ops_alert] Telegram creds missing in $ENV_FILE — would have sent:"
    echo "----"
    echo "$text"
    echo "----"
    exit 0
fi

if curl -s --max-time 20 \
        -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d "chat_id=${TELEGRAM_CHAT_ID}" \
        -d "disable_web_page_preview=true" \
        --data-urlencode "text=${text}" >/dev/null; then
    echo "[ops_alert] Telegram alert sent."
else
    echo "[ops_alert] WARN: Telegram send failed."
fi
exit 0
