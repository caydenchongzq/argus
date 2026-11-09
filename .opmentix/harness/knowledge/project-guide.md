---
type: project-guide
name: argus
title: Project guide
description: How this repository is put together.
---

## Purpose

Argus is a single-user dashboard for a separate TradingAgents installation. It reads portfolio, watchlist, report, theme, and fund-manager data and can launch selected runs. It is decision support, not financial advice.

## Layout

- `server.py` is the FastAPI backend, including file access, API endpoints, and run orchestration.
- `static/` contains the unbuilt single-page UI, local vendor libraries, and brand assets.
- `start.sh` starts the Linux dashboard on the configured LAN address. `runs/` holds local run metadata and logs.
- `run_analysis.py` is the Linux runner that invokes the sibling TradingAgents checkout; `exec_ta.py` bridges into its dedicated Python environment.
- Argus delegates analysis to the sibling TradingAgents checkout. User policy and watchlist settings are stored in its `data/targets.json`; edit them through the dashboard Agents settings when available.
- `tiger_auth.py` and `tiger_import.py` implement Tiger OAuth and stock snapshot preview/apply. `static/` includes the import review UI.
- `check_offline.py` and the `check_*_offline.py` scripts exercise dashboard, runner, budget and Tiger behavior with isolated fixtures.
- TradingAgents lives outside this repository at `/home/dev/projects/trading/TradingAgents` by default; `TRADINGAGENTS_ROOT` selects its location. `DASHBOARD_RUNS_DIR` overrides Argus run storage.

## Commands

- Linux: run `./setup_tradingagents_env.sh` once, then `./start.sh`; the dashboard is available at `http://192.168.1.115:8787` when that address is assigned to the host.
- Run checks with the project Python environment: `.venv/bin/python check_offline.py`, `.venv/bin/python check_runner_offline.py`, `.venv/bin/python check_runner_budget_offline.py`, and `.venv/bin/python check_tiger_offline.py`; run `node check_tiger_ui_offline.js`, `node check_run_scenarios_offline.js` and `node check_money_formatter_offline.js` for UI guard checks. In TradingAgents, relevant checks include `addons/check_cost_ledger.py`, `addons/fund_manager/check_offline.py` and `addons/theme_scout/check_offline.py`.
- Windows PowerShell startup remains available through `start.ps1` for the earlier local workflow.

## Conventions

- The chosen initial access model is trusted LAN with no login or TLS. Bind only to the intended interface and keep the service off the public Internet; anyone on the trusted network can reach sensitive portfolio information and dashboard controls.
- Analysis is started manually from the dashboard; cron and other scheduling are deferred. The Runs tab offers six scenarios: free snapshot refresh, free market screen, paid weekly scout, selected ticker analysis, selected analysis plus portfolio review, and fund-manager-only portfolio review. Paid runs require explicit scope/manifest confirmation. The weekly spending check is currently disabled at the user's request; cost tracking remains enabled and the check can be re-enabled in Agents → Watchlist and spending settings. No run submits broker orders.
- User-approved portfolio guidance is flexible whole-account 10% cash / 30% long-term / 60% swing. Cash can fall below 10%, including to zero, when justified; the split is guidance, not a forced rebalance or an automatic trade rule. Sector weights are guidelines and swing holding periods are flexible.
- Watchlist scout output is a monitoring proposal, not a buy recommendation. Proposals require review and explicit application. Current configured candidate limits are a 14-day cooldown, no weekly add/drop cap, 100 saved non-held candidates overall, and 10 per sector; holdings remain visible regardless. Discovery offers eight ETF-based sector choices and does not represent every GICS sector. Scout coverage and partial failures should be read from its report.
- A failed selected ticker analysis stops a bundled run before fund-manager review; completed ticker reports are preserved, and the review must be rerun after resolving the failed ticker. Market and macro inputs can be stale or unavailable, so check report freshness and source notes before relying on conclusions.
- Tiger import uses OAuth, previews a stock-only snapshot, and requires an explicit replacement confirmation. Unsupported options (including FOP/MLEG) are reported; incomplete stock data blocks application. Tiger credentials stay outside the repository.
- The initial data contract is shared files, not PostgreSQL or Docker. Argus and TradingAgents use the sibling checkout directly.
- Do not read or expose TradingAgents `.env` files or API keys. Avoid modifying its source unless explicitly required.
- The UI has no build step. Markdown rendering and sanitization use locally vendored libraries; preserve sanitization when changing report rendering.
- Treat portfolio import, watchlist and run operations as real side effects. Offline checks use temporary data to avoid altering the real data folder.
- Backup/restore was rehearsed using a temporary archive of TradingAgents `data/` and Argus `runs/`; 21 files passed hash checks after restore. No durable off-host backup destination is configured, so this rehearsal does not replace a real backup policy.

## Logs

- 2026-11-09 16:50 UTC — Recorded current run scenarios, flexible portfolio guidance, watchlist limits and review boundary, disabled spending-check preference, data freshness cautions, and relevant offline checks after plan completion.
- 2026-11-08 06:24 — Initialized project guide from repository scan.
- 2026-11-08 — Updated guide after Linux deployment acceptance: native sibling TradingAgents runtime, trusted LAN access, dashboard-triggered runs, Tiger stock-only replace flow, and backup rehearsal evidence. Paid analysis and durable off-host backup remain open for future work.
