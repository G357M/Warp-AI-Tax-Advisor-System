#!/bin/bash
# Telegram alerting for the nightly RAG canary (П0.4).
#
# Called by run_scraper.sh:  canary_alert.sh <canary_exit_code> <canary_line>
# where <canary_line> is canary_eval.py's "CANARY: 8/10 failed=pit_rate,micro".
#
# Alerts when the canary is below threshold (exit code != 0) or produced no
# parsable output at all. Credentials come from /root/infohub/.env, same as
# scraper_alert.sh; no-ops with a log message when they are missing.

set -u

INFOHUB_DIR="/root/infohub"
ENV_FILE="$INFOHUB_DIR/.env"

EXIT_CODE="${1:-1}"
CANARY_LINE="${2:-}"
HOST="$(hostname)"
NOW="$(date -u '+%Y-%m-%d %H:%M UTC')"

TELEGRAM_BOT_TOKEN=""
TELEGRAM_CHAT_ID=""
if [ -f "$ENV_FILE" ]; then
    TELEGRAM_BOT_TOKEN="$(grep -E '^TELEGRAM_BOT_TOKEN=' "$ENV_FILE" | tail -1 | cut -d= -f2- | tr -d '"'"'"' \r')"
    TELEGRAM_CHAT_ID="$(grep -E '^TELEGRAM_CHAT_ID='   "$ENV_FILE" | tail -1 | cut -d= -f2- | tr -d '"'"'"' \r')"
fi

send_telegram() {
    local text="$1"
    if [ -z "$TELEGRAM_BOT_TOKEN" ] || [ -z "$TELEGRAM_CHAT_ID" ]; then
        echo "[canary_alert] Telegram creds missing in $ENV_FILE — would have sent:"
        echo "----"
        echo "$text"
        echo "----"
        return 0
    fi
    if curl -s --max-time 20 \
            -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            -d "chat_id=${TELEGRAM_CHAT_ID}" \
            -d "disable_web_page_preview=true" \
            --data-urlencode "text=${text}" >/dev/null; then
        echo "[canary_alert] Telegram alert sent."
    else
        echo "[canary_alert] WARN: Telegram send failed."
    fi
}

if [ "$EXIT_CODE" = "0" ]; then
    echo "[canary_alert] canary healthy (${CANARY_LINE:-no line}) — no alert."
    exit 0
fi

send_telegram "🔴 InfoHub RAG canary FAILED on ${HOST}
${CANARY_LINE:-canary produced no output}
${NOW}
The nightly known-answer check is below threshold — a RAG regression may be live. See latest /root/infohub/logs/scraper_*.log"
exit 0
