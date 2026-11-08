# Argus

Local dashboard for [TradingAgents](../TradingAgents) — view your portfolio, watchlist, per-stock reports, and fund-manager plans, and trigger selective or full runs from one place.

**Decision support only. Not financial advice.**

## Requirements

- Python 3.10+.
- TradingAgents checked out beside Argus, or set `TRADINGAGENTS_ROOT` to its location.
- TradingAgents' own Python environment, prepared from its `pyproject.toml`; its Linux package requires Python 3.11 or newer.
- Provider credentials configured for the same local user when paid runs are intended.
- Set `TRADINGAGENTS_PYTHON` to another prepared interpreter only when the TradingAgents checkout is elsewhere. Argus checks required runtime imports before starting any stage and stops with setup instructions if they are missing.

Argus **never** reads or prints `.env` / API keys. It reads portfolio and report data and launches the TradingAgents Python add-on commands through `run_analysis.py`; it does not invoke Docker or PowerShell.

## Quick start

```powershell
cd "D:\software development\trading\argus"
.\start.ps1 -Install   # first time: creates .venv and installs deps
.\start.ps1            # later starts
```

Open **http://127.0.0.1:8787** (loopback by default).

On Linux, create the virtual environment, then run:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
./start.sh
```

Prepare the separate TradingAgents runtime once from the Argus directory. This installs the checked out TradingAgents package and its declared dependencies into `TradingAgents/.venv`; it does not read or print provider credentials. Then run the isolated runtime check:

```sh
./setup_tradingagents_env.sh
./check_tradingagents_runtime.sh
```

The check imports the actual TradingAgents data modules and runs its real `preflight.py` with `--session-only` and a temporary output/data directory. It makes no market-data request, model call, or write to the real TradingAgents data folder. Analysis jobs then use the sibling `TradingAgents/.venv/bin/python` by default; an explicit `TRADINGAGENTS_PYTHON` override is also checked before stages start.

Argus starts on loopback by default. To expose it to your trusted LAN, bind to the specific bridged interface address (never `0.0.0.0`):

```sh
ARGUS_HOST=192.168.1.115 ./start.sh
```

Then open `http://192.168.1.115:8787`. LAN mode has no login or TLS: anyone on that LAN can view portfolio data and operate the dashboard. Keep it on a trusted private network. Host validation, same-origin checks, and confirmation tokens for writes and runs remain enabled.

Analysis runs start only when requested in the dashboard; there is no cron or timer. Manual runs and theme scouting share a process lock. “No LLM” skips every model stage, including per-ticker agents, while retaining the free snapshot workflow. Cost checks use the existing estimates and ledger; provider-side limits remain the hard spending control.

Optional:

```powershell
.\start.ps1 -Port 8790
$env:TRADINGAGENTS_ROOT = "D:\path\to\TradingAgents"
.\start.ps1
```

## What you get

| Tab | Features |
|-----|----------|
| **Portfolio** | Holdings from the book. Value, weight and cash % are quantity × the latest stats price, recomputed when the book has changed. An AI sub-theme table shows direct holding weight |
| **Watchlist** | View / add / remove candidates; writes `data\watchlist.json` and appends `data\watchlist_log.jsonl`; **Undo** reverses the last add or removal. Candidates are grouped by AI sub-theme |
| **Reports** | List by ticker/date, rendered Markdown, latest rating highlighted |
| **Fund manager** | Latest plan. Trades come from `final` / `final_check` (the add-on does not write a `decision` key). History includes timestamped run folders |
| **Themes** | Latest theme-scout report and the free daily screen. Run buttons use the confirm token. The Sol call is off unless the checkbox is set |
| **Runs** | Selective runs. Cost warning is ~2.5 min/ticker plus 5 fund-manager calls (Opus for conservative, Luna for neutral). POST `/api/runs` needs `confirm: true` and the `X-Argus-Confirm` token from `GET /api/session`. Requests whose Host does not match loopback or the explicitly configured `ARGUS_HOST` are rejected |

## Layout

```
argus/
  server.py          FastAPI backend
  start.ps1          Windows launcher (127.0.0.1)
  start.sh           Linux launcher (127.0.0.1 by default)
  run_analysis.py    native TradingAgents pipeline for dashboard runs
  requirements.txt
  static/            single-page UI (no build step)
  runs/              local run metadata + logs (not TradingAgents)
  README.md
```

## Safety notes

- Binds to **127.0.0.1** by default. Optional LAN binding requires the explicit interface address in `ARGUS_HOST`; wildcard binding is rejected. In LAN mode, there is no login or TLS and anyone on the private network can access portfolio data.
- Markdown from reports is rendered with pinned local marked 15.0.12 and sanitized with DOMPurify 3.2.4. Chart.js 4.4.7 is local too.
- POST `/api/runs` requires the per-process confirm token plus `confirm: true`.
- Does **not** modify TradingAgents source files.
- Watchlist edits require the per-process confirmation token, use atomic JSON replacement, and are blocked while an analysis holds the shared data lock.
- Tiger import uses OAuth2 account/position queries only. It replaces the Argus book with supported US stock positions and cash only. Options, futures and other non-stock positions are shown as excluded; unsupported stock rows, incomplete stock queries and mixed currencies block replacement. Apply requires the preview plus explicit stock-only and replacement confirmations, a backup (when a book already exists) and an unchanged book version. The portfolio book has no verified cross-market ticker mapping, so Singapore or unknown-market stocks are rejected instead of guessing a suffix.
- Do not start paid agent runs from Argus unless you mean to spend OpenRouter credits.

## Tiger read-only setup

Tiger OAuth is for individual accounts and does not use the RSA private key. First enable OpenAPI for the funded account in the Tiger Developer Center. Install the optional SDK into the same Python environment that runs Argus, then authorize as the same Linux user so the token is stored in that user's local Tiger directory. The helper uses Tiger's device-code flow, so the verification page and code can be opened on Windows while Argus runs in the Linux guest:

```sh
.venv/bin/pip install -r tiger-requirements.txt
.venv/bin/python tiger_auth.py
```

Open the printed authorization link, sign in to Tiger, and grant account/position query access only; leave trading permissions disabled. Then open Argus, choose **Import from Tiger**, load the authorized account, and review the snapshot before applying. The browser sees account aliases, not raw account identifiers. Do not send RSA keys, OAuth tokens, or account exports through chat. OAuth access can expire and may need reauthorization. This is an initial read-only test path; Singapore account/position field compatibility has not been verified live.

If Argus currently shows `my_book.json` as missing, that is a first-import state: the Portfolio tab starts empty and the reviewed **Apply replacement** action creates the book. Fetching a preview does not create or modify it. Tiger's current [Python preparation guide](https://docs-en.itigerup.com/docs/prepare) documents `OAuth2SessionManager` and the authorization flow; [authentication guidance](https://docs-en.itigerup.com/docs/authentication) explains OAuth account and permission selection. The Tiger SDK is optional and is not installed by the main `requirements.txt`.

## License / scope

Side project for personal use with your local TradingAgents install.
