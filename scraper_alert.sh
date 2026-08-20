#!/bin/bash
# Telegram alerting for the InfoHub nightly scraper.
#
# Called by run_scraper.sh:  scraper_alert.sh <exit_code> <new_docs|"?">
#
# Sends a Telegram message when:
#   - the run FAILED (exit_code != 0, or new-doc count couldn't be parsed), OR
#   - the run added 0 new docs for ZERO_NEW_THRESHOLD consecutive runs
#     (0 new on a single night is normal steady state, so we only alert on a streak).
#
# Credentials are read from /root/infohub/.env:
#   TELEGRAM_BOT_TOKEN=...
#   TELEGRAM_CHAT_ID=...
# If they are missing the script no-ops (logs what it would have sent) instead of failing.

set -u

INFOHUB_DIR="/root/infohub"
ENV_FILE="$INFOHUB_DIR/.env"
STREAK_FILE="$INFOHUB_DIR/logs/zero_new_streak"
ZERO_NEW_THRESHOLD="${ZERO_NEW_THRESHOLD:-3}"

EXIT_CODE="${1:-1}"
NEW_DOCS="${2:-?}"
DETAIL="${3:-}"
HOST="$(hostname)"
NOW="$(date -u '+%Y-%m-%d %H:%M UTC')"

# --- load Telegram creds (only the two vars we need) ----------------------
TELEGRAM_BOT_TOKEN=""
TELEGRAM_CHAT_ID=""
if [ -f "$ENV_FILE" ]; then
    TELEGRAM_BOT_TOKEN="$(grep -E '^TELEGRAM_BOT_TOKEN=' "$ENV_FILE" | tail -1 | cut -d= -f2- | tr -d '"'"'"' \r')"
    TELEGRAM_CHAT_ID="$(grep -E '^TELEGRAM_CHAT_ID='   "$ENV_FILE" | tail -1 | cut -d= -f2- | tr -d '"'"'"' \r')"
fi

send_telegram() {
    local text="$1"
    if [ -z "$TELEGRAM_BOT_TOKEN" ] || [ -z "$TELEGRAM_CHAT_ID" ]; then
        echo "[scraper_alert] Telegram creds missing in $ENV_FILE — would have sent:"
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
        echo "[scraper_alert] Telegram alert sent."
    else
        echo "[scraper_alert] WARN: Telegram send failed."
    fi
}

read_streak() {
    local s=0
    [ -f "$STREAK_FILE" ] && s="$(cat "$STREAK_FILE" 2>/dev/null || echo 0)"
    [[ "$s" =~ ^[0-9]+$ ]] || s=0
    echo "$s"
}

# --- decide ---------------------------------------------------------------
# Failure: non-zero exit, or we couldn't parse a numeric new-doc count.
if [ "$EXIT_CODE" != "0" ] || ! [[ "$NEW_DOCS" =~ ^[0-9]+$ ]]; then
    echo 0 > "$STREAK_FILE"
    send_telegram "🔴 InfoHub nightly pipeline FAILED on ${HOST}
Exit code: ${EXIT_CODE}
New docs: ${NEW_DOCS}
Details: ${DETAIL:-primary scraper step failed or summary was not parseable}
${NOW}
Check latest /root/infohub/logs/scraper_*.log"
    exit 0
fi

# Success with 0 new docs: count the streak, alert only past the threshold.
if [ "$NEW_DOCS" -eq 0 ]; then
    streak=$(( $(read_streak) + 1 ))
    echo "$streak" > "$STREAK_FILE"
    if [ "$streak" -ge "$ZERO_NEW_THRESHOLD" ]; then
        send_telegram "🟠 InfoHub scraper: 0 new docs ${streak} runs in a row on ${HOST}
${NOW}
Runs succeed (exit 0) but nothing has been ingested for ${streak} nights — scraper may be silently stuck. Compare source vs DB."
        echo 0 > "$STREAK_FILE"   # reset: re-alert after another full streak, not every night
    else
        echo "[scraper_alert] 0 new (streak ${streak}/${ZERO_NEW_THRESHOLD}) — no alert yet."
    fi
    exit 0
fi

# Healthy run with new docs.
echo 0 > "$STREAK_FILE"
echo "[scraper_alert] +${NEW_DOCS} new docs — healthy, streak reset."
exit 0
