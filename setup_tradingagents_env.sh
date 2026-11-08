#!/usr/bin/env bash
set -euo pipefail

argus_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ta_root="${TRADINGAGENTS_ROOT:-$(cd "$argus_dir/../TradingAgents" && pwd)}"
ta_venv="$ta_root/.venv"

if [[ ! -f "$ta_root/pyproject.toml" || ! -d "$ta_root/tradingagents" ]]; then
  echo "TradingAgents source was not found at TRADINGAGENTS_ROOT." >&2
  exit 2
fi

if [[ ! -x "$ta_venv/bin/python" ]]; then
  python3 -m venv "$ta_venv"
fi
"$ta_venv/bin/python" -m pip install --upgrade pip
"$ta_venv/bin/python" -m pip install -e "$ta_root"
"$ta_venv/bin/python" -c 'import pandas, yfinance, langchain_core, langgraph, langchain_openai, langchain_anthropic, langchain_google_genai, stockstats; from tradingagents.dataflows.symbols import normalize_symbol, safe_ticker_component; print("TradingAgents runtime imports: ok")'
echo "Set TRADINGAGENTS_PYTHON=$ta_venv/bin/python when starting Argus if this is not the default sibling checkout."
