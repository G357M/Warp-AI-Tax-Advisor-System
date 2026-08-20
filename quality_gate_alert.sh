#!/bin/bash
# Aggregate-only Telegram alerting for deterministic nightly quality gates.

set -u

INFOHUB_DIR="/root/infohub"
ENV_FILE="$INFOHUB_DIR/.env"

EXIT_CODE="${1:-1}"
GATE_LABEL="${2:-unknown quality gate}"
SUMMARY="${3:-}"
HOST="$(hostname)"
NOW="$(date -u '+%Y-%m-%d %H:%M UTC')"

# The caller passes only the evaluator's aggregate machine-summary line. Keep
# a defensive single-line/length boundary before it can leave the host.
GATE_LABEL="$(printf '%s' "$GATE_LABEL" | tr '\r\n' '  ' | cut -c1-120)"
SUMMARY="$(printf '%s' "$SUMMARY" | tr '\r\n' '  ' | cut -c1-2500)"

TELEGRAM_BOT_TOKEN=""
TELEGRAM_CHAT_ID=""
if [ -f "$ENV_FILE" ]; then
    TELEGRAM_BOT_TOKEN="$(grep -E '^TELEGRAM_BOT_TOKEN=' "$ENV_FILE" | tail -1 | cut -d= -f2- | tr -d '"'"'"' \r')"
    TELEGRAM_CHAT_ID="$(grep -E '^TELEGRAM_CHAT_ID=' "$ENV_FILE" | tail -1 | cut -d= -f2- | tr -d '"'"'"' \r')"
fi

send_telegram() {
    local text="$1"
    if [ -z "$TELEGRAM_BOT_TOKEN" ] || [ -z "$TELEGRAM_CHAT_ID" ]; then
        echo "[quality_gate_alert] Telegram creds missing in $ENV_FILE — would have sent:"
        echo "----"
        echo "$text"
        echo "----"
        return 0
    fi
    if curl --fail --silent --show-error --max-time 20 \
            -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            -d "chat_id=${TELEGRAM_CHAT_ID}" \
            -d "disable_web_page_preview=true" \
            --data-urlencode "text=${text}" >/dev/null; then
        echo "[quality_gate_alert] Telegram alert sent."
    else
        echo "[quality_gate_alert] WARN: Telegram send failed."
    fi
}

if [ "$EXIT_CODE" = "0" ] && [ -n "$SUMMARY" ]; then
    echo "[quality_gate_alert] ${GATE_LABEL} healthy — no alert."
    exit 0
fi

send_telegram "🔴 InfoHub ${GATE_LABEL} FAILED on ${HOST}
${SUMMARY:-aggregate summary was not produced}
${NOW}
The deterministic nightly quality contract is below threshold or its protected artifact is incomplete. See the latest /root/infohub/logs/scraper_*.log and /root/infohub/.state/."
exit 0
