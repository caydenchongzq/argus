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
| **Portfolio** | Holdings from the book. Value, weight and cash % are quantity × the latest stats price, recomputed when the book has changed |
| **Watchlist** | View / add / remove candidates; writes `data\watchlist.json` with timestamped `.bak` copies |
| **Reports** | List by ticker/date, rendered Markdown, latest rating highlighted |
| **Fund manager** | Latest plan. Trades come from `final` / `final_check` (the add-on does not write a `decision` key). History includes timestamped run folders |
| **Runs** | Selective runs. Cost warning is ~2.5 min/ticker plus 5 fund-manager calls (Luna for conservative and neutral; Opus is not the default). POST `/api/runs` needs `confirm: true` and the `X-Argus-Confirm` token from `GET /api/session`. Requests whose Host is not localhost / 127.0.0.1 are rejected |

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

- Binds to **127.0.0.1** only, and rejects any other Host header.
- Markdown from reports is rendered with pinned local marked 15.0.12 and sanitized with DOMPurify 3.2.4. Chart.js 4.4.7 is local too.
- POST `/api/runs` requires the per-process confirm token plus `confirm: true`.
- Does **not** modify TradingAgents source files.
- Watchlist edits backup the previous JSON first.
- Do not start paid agent runs from Argus unless you mean to spend OpenRouter credits.

## License / scope

Side project for personal use with your local TradingAgents install.
