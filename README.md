# Argus

Local dashboard for [TradingAgents](../TradingAgents) — view your portfolio, watchlist, per-stock reports, and fund-manager plans, and trigger selective or full runs from one place.

**Decision support only. Not financial advice.**

## Requirements

- Windows laptop with TradingAgents already set up at  
  `D:\software development\trading\TradingAgents`
- Python 3.10+ on PATH
- Docker Desktop (only when you actually run agents / the fund manager)

Argus **never** reads or prints `.env` / API keys. It only reads JSON/Markdown under `TradingAgents\data` and calls `addons\fund_manager\run_portfolio.ps1`.

## Quick start

```powershell
cd "D:\software development\trading\argus"
.\start.ps1 -Install   # first time: creates .venv and installs deps
.\start.ps1            # later starts
```

Open **http://127.0.0.1:8787** (bound to localhost only).

Optional:

```powershell
.\start.ps1 -Port 8790
$env:TRADINGAGENTS_ROOT = "D:\path\to\TradingAgents"
.\start.ps1
```

## What you get

| Tab | Features |
|-----|----------|
| **Portfolio** | Holdings, cost, live-ish marks from the latest `portfolio_stats.json`, P&L, current vs target weight chart, cash |
| **Watchlist** | View / add / remove candidates; writes `data\watchlist.json` with timestamped `.bak` copies |
| **Reports** | List by ticker/date, rendered Markdown, latest rating highlighted |
| **Fund manager** | Latest plan, trades table, history by date |
| **Runs** | One-click or selective runs (book + watchlist checkboxes), toggles for `-RunAgents`, `-NoLLM`, `-IncludeRisk`, `-NoMacro`, `-AnalysisDate`, `-Since`, and `-IncludeWatchlist` when the script supports it. Cost/time warning (~7 min/ticker) + confirm dialog. Background PowerShell process with live log tail |

## Layout

```
argus/
  server.py          FastAPI backend
  start.ps1          launcher (127.0.0.1)
  requirements.txt
  static/            single-page UI (no build step)
  runs/              local run metadata + logs (not TradingAgents)
  README.md
```

## Safety notes

- Binds to **127.0.0.1** only.
- Does **not** modify TradingAgents source files.
- Watchlist edits backup the previous JSON first.
- Do not start paid agent runs from Argus unless you mean to spend OpenRouter credits.

## License / scope

Side project for personal use with your local TradingAgents install.
