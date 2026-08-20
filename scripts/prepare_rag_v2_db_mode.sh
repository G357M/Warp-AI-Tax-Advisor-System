#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_DEPS=0
RUN_EVAL=1
PYTHON_BIN="${PYTHON_BIN:-}"

for arg in "$@"; do
  case "$arg" in
    --install-deps) INSTALL_DEPS=1 ;;
    --no-eval) RUN_EVAL=0 ;;
    *) echo "Unknown argument: $arg" >&2; exit 2 ;;
  esac
done

export INFOHUB_V2_BACKEND_MODE="${INFOHUB_V2_BACKEND_MODE:-db}"
export INFOHUB_DATABASE_URL="${INFOHUB_DATABASE_URL:-${DATABASE_URL:-}}"

if [[ -z "$INFOHUB_DATABASE_URL" ]]; then
  echo "INFOHUB_DATABASE_URL or DATABASE_URL must be configured explicitly." >&2
  exit 1
fi

cd "$ROOT"

if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x "$ROOT/.venv-rag-v2-db/bin/python" ]]; then
    PYTHON_BIN="$ROOT/.venv-rag-v2-db/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi

echo "[rag-v2] root: $ROOT"
echo "[rag-v2] mode: $INFOHUB_V2_BACKEND_MODE"
echo "[rag-v2] db url: ${INFOHUB_DATABASE_URL%%:*}://***@${INFOHUB_DATABASE_URL#*@}"
echo "[rag-v2] python: $PYTHON_BIN"

if [[ "$INSTALL_DEPS" == "1" ]]; then
  echo "[rag-v2] installing db dependencies"
  "$PYTHON_BIN" -m pip install -r requirements-rag_v2_db.txt
fi

echo "[rag-v2] backend db status"
"$PYTHON_BIN" - <<'PY'
import json
import sys
from pathlib import Path
root = Path.cwd()
sys.path.insert(0, str(root))
from backend.rag_v2.db_utils import db_status
print(json.dumps(db_status(), ensure_ascii=False, indent=2))
PY

if [[ "$RUN_EVAL" == "1" ]]; then
  echo "[rag-v2] running deterministic live-corpus eval"
  "$PYTHON_BIN" backend/scripts/evaluate_rag_v2_live_corpus.py \
    --commit "$(git rev-parse HEAD)" \
    --output reports/rag_v2_live_corpus_latest.json
fi
