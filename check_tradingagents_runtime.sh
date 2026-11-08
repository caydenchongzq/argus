#!/usr/bin/env bash
set -euo pipefail

argus_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ta_root="${TRADINGAGENTS_ROOT:-$(cd "$argus_dir/../TradingAgents" && pwd)}"
ta_python="${TRADINGAGENTS_PYTHON:-$ta_root/.venv/bin/python}"

if [[ ! -x "$ta_python" ]]; then
  echo "TradingAgents Python is not prepared. Run ./setup_tradingagents_env.sh first." >&2
  exit 2
fi
"$ta_python" -c 'import pandas, yfinance, langchain_core, langgraph, langchain_openai, langchain_anthropic, langchain_google_genai, stockstats; from tradingagents.dataflows.symbols import normalize_symbol, safe_ticker_component'

fixture_root="$(mktemp -d "${TMPDIR:-/tmp}/argus_ta_preflight_XXXXXX")"
trap 'rm -rf "$fixture_root"' EXIT
mkdir -p "$fixture_root/cache" "$fixture_root/output"
FM_DATA_ROOT="$fixture_root" TRADINGAGENTS_ROOT="$ta_root" TZ=America/New_York \
  "$ta_python" "$ta_root/addons/fund_manager/preflight.py" \
  --session-only --analysis-date 2025-01-02 \
  --cache-dir "$fixture_root/cache" --out "$fixture_root/output/preflight.json"
echo "TradingAgents import and isolated no-paid preflight: ok"
