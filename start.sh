#!/usr/bin/env bash
set -euo pipefail

ARGUS_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ ! -x "$ARGUS_DIR/.venv/bin/python" ]]; then
  echo "Create the Argus environment first: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

export TRADINGAGENTS_ROOT="${TRADINGAGENTS_ROOT:-$(cd "$ARGUS_DIR/../TradingAgents" && pwd)}"
exec "$ARGUS_DIR/.venv/bin/python" -m uvicorn server:app \
  --app-dir "$ARGUS_DIR" \
  --host "${ARGUS_HOST:-127.0.0.1}" \
  --port "${ARGUS_PORT:-8787}" \
  --workers 1
