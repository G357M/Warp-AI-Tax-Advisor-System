#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-both}"
shift || true

URL_DEFAULT="https://tax-advisor.ge/api/v1/public/query"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PY_SCRIPT="$SCRIPT_DIR/run_public_stability_watch.py"
TRIMMED_QUERIES="$SCRIPT_DIR/public_canary_queries_trimmed.txt"

usage() {
  cat <<'EOF'
Usage:
  scripts/run_public_smoke.sh [browser|browser-core|browser-multilang|browser-multilang-core|api|both] [extra args passed through]

Examples:
  scripts/run_public_smoke.sh browser --repeats 1
  scripts/run_public_smoke.sh browser-core --repeats 1
  scripts/run_public_smoke.sh browser-multilang --repeats 1
  scripts/run_public_smoke.sh browser-multilang-core --repeats 1
  scripts/run_public_smoke.sh api --repeats 1
  scripts/run_public_smoke.sh both --timeout 30

Defaults:
  - url: https://tax-advisor.ge/api/v1/public/query
  - browser mode: --profile trimmed
  - browser-core mode: --profile core
  - browser-multilang mode: --profile multilingual-trimmed
  - browser-multilang-core mode: --profile multilingual-core
  - api mode: --queries-file scripts/public_canary_queries_trimmed.txt
  - repeats: 1
EOF
}

if [[ "$MODE" == "-h" || "$MODE" == "--help" || "$MODE" == "help" ]]; then
  usage
  exit 0
fi

run_browser() {
  python3 "$PY_SCRIPT" \
    --url "$URL_DEFAULT" \
    --client-profile browser \
    --profile trimmed \
    --repeats 1 \
    "$@"
}

run_browser_core() {
  python3 "$PY_SCRIPT" \
    --url "$URL_DEFAULT" \
    --client-profile browser \
    --profile core \
    --repeats 1 \
    "$@"
}

run_browser_multilang() {
  python3 "$PY_SCRIPT" \
    --url "$URL_DEFAULT" \
    --client-profile browser \
    --profile multilingual-trimmed \
    --repeats 1 \
    "$@"
}

run_browser_multilang_core() {
  python3 "$PY_SCRIPT" \
    --url "$URL_DEFAULT" \
    --client-profile browser \
    --profile multilingual-core \
    --repeats 1 \
    "$@"
}

run_api() {
  python3 "$PY_SCRIPT" \
    --url "$URL_DEFAULT" \
    --client-profile api \
    --queries-file "$TRIMMED_QUERIES" \
    --repeats 1 \
    "$@"
}

case "$MODE" in
  browser)
    run_browser "$@"
    ;;
  browser-core)
    run_browser_core "$@"
    ;;
  browser-multilang)
    run_browser_multilang "$@"
    ;;
  browser-multilang-core)
    run_browser_multilang_core "$@"
    ;;
  api)
    run_api "$@"
    ;;
  both)
    echo '===BROWSER_SMOKE==='
    run_browser "$@"
    echo
    echo '===BROWSER_MULTILINGUAL_SMOKE==='
    run_browser_multilang "$@"
    echo
    echo '===API_POLICY_SMOKE==='
    run_api "$@"
    ;;
  *)
    echo "Unknown mode: $MODE" >&2
    usage >&2
    exit 2
    ;;
esac
