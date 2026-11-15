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
- `run_analysis.py` is the Linux runner that invokes the sibling TradingAgents checkout; `exec_ta.py` bridges into its dedicated Python environment. The bridge must put the selected entry-point directory before the TradingAgents root on `sys.path`, matching direct Python script execution so add-on sibling imports resolve correctly.
- Argus delegates analysis to the sibling TradingAgents checkout. User policy and watchlist settings are stored in its `data/targets.json`; edit them through the dashboard Agents settings when available.
- `tiger_auth.py` and `tiger_import.py` implement Tiger OAuth and stock snapshot preview/apply. `static/` includes the import review UI.
- `portfolio_import.py` coordinates broker account snapshots; `moomoo_import.py` is the optional read-only Moomoo Singapore adapter. Both feed the versioned account book shared with TradingAgents.
- `check_offline.py` and the `check_*_offline.py` scripts exercise dashboard, runner, budget and Tiger behavior with isolated fixtures.
- TradingAgents lives outside this repository at `/home/dev/projects/trading/TradingAgents` by default; `TRADINGAGENTS_ROOT` selects its location. `DASHBOARD_RUNS_DIR` overrides Argus run storage.

## Commands

- Linux: run `./setup_tradingagents_env.sh` once, then `./start.sh`; the dashboard listens on `http://127.0.0.1:8788` by default. LAN access uses the configured host address and port 8788 when `ARGUS_HOST` permits it.
- Run checks with the project Python environment: `.venv/bin/python check_offline.py`, `.venv/bin/python check_runner_offline.py`, `.venv/bin/python check_runner_budget_offline.py`, `.venv/bin/python check_exec_ta_offline.py`, `.venv/bin/python check_tiger_offline.py`, `.venv/bin/python check_portfolio_import_offline.py`, and `.venv/bin/python check_moomoo_offline.py`; run `node check_tiger_ui_offline.js`, `node check_broker_import_ui_offline.js`, `node check_run_scenarios_offline.js`, `node check_fund_manager_ui_offline.js` and `node check_money_formatter_offline.js` for UI guard checks. In TradingAgents, relevant checks include `addons/check_cost_ledger.py`, `addons/check_portfolio_book.py`, `addons/check_config_cleanup.py`, `addons/fund_manager/check_trade_validation.py`, `addons/fund_manager/check_offline.py` and `addons/theme_scout/check_offline.py`.
- Windows PowerShell startup remains available through `start.ps1` for the earlier local workflow.

## Conventions

- The chosen initial access model is trusted LAN with no login or TLS. Bind only to the intended interface and keep the service off the public Internet; anyone on the trusted network can reach sensitive portfolio information and dashboard controls.
- Analysis is started manually from the dashboard; cron and other scheduling are deferred. The Runs tab offers six scenarios: free snapshot refresh, free market screen, paid weekly scout, selected ticker analysis, selected analysis plus portfolio review, and fund-manager-only portfolio review. Paid runs require explicit scope/manifest confirmation. The weekly spending check is currently disabled at the user's request; cost tracking remains enabled and the check can be re-enabled in Agents → Watchlist and spending settings. No run submits broker orders.
- User-approved portfolio guidance is flexible whole-account 10% cash / 30% long-term / 60% swing. Cash can fall below 10%, including to zero, when justified; the split is guidance, not a forced rebalance or an automatic trade rule. Sector weights are guidelines and swing holding periods are flexible.
- Watchlist scout output is a monitoring proposal, not a buy recommendation. Proposals require review and explicit application. Current configured candidate limits are a 14-day cooldown, no weekly add/drop cap, 100 saved non-held candidates overall, and 10 per sector; holdings remain visible regardless. Discovery offers eight ETF-based sector choices and does not represent every GICS sector. Scout coverage and partial failures should be read from its report.
- A failed selected ticker analysis stops a bundled run before fund-manager review; completed ticker reports are preserved, and the review must be rerun after resolving the failed ticker. Market and macro inputs can be stale or unavailable, so check report freshness and source notes before relying on conclusions.
- Tiger import uses OAuth, previews a stock-only snapshot, and requires an explicit replacement confirmation. Unsupported options (including FOP/MLEG) are reported; incomplete stock data blocks application. Tiger credentials stay outside the repository.
- The shared TradingAgents `addons/portfolio_book.py` contract uses `schema_version: 2` and canonical `accounts[]`; top-level cash and consolidated positions are a derived compatibility projection for native CLI/scout readers. Per-account cash remains separate. If any account's cash is unknown, aggregate cash and cash-dependent whole-book totals are unavailable; never coerce unknown to zero. Matching US/USD instruments consolidate quantities, while average cost is consolidated only when all source cost methods are compatible; account-level detail remains available.
- `addons/fund_manager/trade_validation.py` is the deterministic advisory trade-policy validator. Defaults are a $3 estimated fee per accepted order, a $1,000 minimum buy notional per account/order, and a $1,000 residual-value guide. Buys/top-ups do not pool cash across accounts; sells are simulated before buys. Risk-driven sales below the residual guide are allowed, and explicit full exits may include fractional shares when sellable. These checks produce recommendations only; Argus does not submit broker orders.
- Moomoo Singapore imports use the optional `moomoo-api==10.12.7208` SDK and local OpenD at `127.0.0.1:11111`, via `OpenSecTradeContext` filtered to US trading with `SecurityFirm.FUTUSG`. The adapter reads real, active accounts with US authorization and imports supported US/USD stock positions only; it has no order-submission path. Securities-account USD cash remains null because the returned cash/buying-power fields do not establish USD-denominated spendable cash. Such an account cannot fund validated actionable trades. Live OpenD connectivity and account authorization are deployment-specific; offline checks do not establish them.
- **User preference (2026-11-15): Moomoo connection work is on hold.** Do not resume OpenD login, account authorization, or live account-connection attempts unless the user asks. Keep the local gateway stopped. The installed SDK and launcher/integration files remain available; unrelated read-only checks and Tiger verification can continue. This pause is specific to live Moomoo access, not the offline adapter implementation.
- AI subthemes have been removed from current producers and consumers. General themes, sector buckets, and AI look-through analytics remain distinct active features. Legacy subtheme fields may still occur in saved history, which remains readable; obsolete no-op settings are removed by the owned-config migration.
- TradingAgents `addons/config_cleanup.py` previews the owned JSON cleanup and binds apply to a content fingerprint. It uses the shared `.argus-run.lock`, creates mode-preserving backups, performs atomic writes, and restores already-written files if a multi-file update fails. Keep backups for recovery; the migration removes only audited no-op settings and current subtheme tags, preserving unknown metadata, active policy/budget settings, history and `watchlist_log.jsonl`.
- The account-book, policy, cleanup, Moomoo, and UI checks listed above are offline fixture checks. They establish local behavior, not live broker access. Consult the active Opmentix plan for current independent verification and acceptance evidence.
- The initial data contract is shared files, not PostgreSQL or Docker. Argus and TradingAgents use the sibling checkout directly.
- Do not read or expose TradingAgents `.env` files or API keys. Avoid modifying its source unless explicitly required.
- The UI has no build step. Markdown rendering and sanitization use locally vendored libraries; preserve sanitization when changing report rendering.
- When changing a shared static script's exported API, update its versioned script URL in `static/index.html` with the caller. Browsers can otherwise pair a cached helper with a newer `app.js`; the broker preview guard regression in `check_broker_import_ui_offline.js` covers this cache-sensitive contract.
- Treat portfolio import, watchlist and run operations as real side effects. Offline checks use temporary data to avoid altering the real data folder.
- Backup/restore was rehearsed using a temporary archive of TradingAgents `data/` and Argus `runs/`; 21 files passed hash checks after restore. No durable off-host backup destination is configured, so this rehearsal does not replace a real backup policy.

## Logs

- 2026-11-15 02:49 UTC — Documented static helper cache versioning after broker preview exposed an old guard/new caller mismatch.
- 2026-11-15 02:32 UTC — Documented the `exec_ta.py` import-order contract and added its offline check command after a sibling add-on import failure exposed the launcher edge case. Moomoo live-connection hold remains in effect.
- 2026-11-15 02:28 UTC — Recorded the user's durable hold on live Moomoo login/OpenD/account connection work. Keep its gateway stopped unless the user asks to resume; retain the installed SDK/launcher and continue unrelated verification.
- 2026-11-15 01:36 UTC — Corrected the default dashboard port from `start.sh`/README, documented the Moomoo SDK's US-filtered `OpenSecTradeContext` and FUTUSG selection, clarified null USD cash semantics, and refreshed migration guidance. Current acceptance evidence remains in the Opmentix plan; guide does not treat live broker connectivity as verified.
- 2026-11-14 16:30 UTC — Curated implementation facts from `addons/portfolio_book.py`, `addons/fund_manager/trade_validation.py`, `addons/config_cleanup.py`, Argus broker adapters and README. Recorded account-book/projection semantics, advisory policy defaults, unknown Moomoo cash, subtheme/no-op cleanup, check locations, and migration safeguards.
- 2026-11-09 16:50 UTC — Recorded current run scenarios, flexible portfolio guidance, watchlist limits and review boundary, disabled spending-check preference, data freshness cautions, and relevant offline checks after plan completion.
- 2026-11-08 06:24 — Initialized project guide from repository scan.
- 2026-11-08 — Updated guide after Linux deployment acceptance: native sibling TradingAgents runtime, trusted LAN access, dashboard-triggered runs, Tiger stock-only replace flow, and backup rehearsal evidence. Paid analysis and durable off-host backup remain open for future work.
