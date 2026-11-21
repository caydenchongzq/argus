---
type: knowledge
title: Fund manager decision continuity
---

## Summary

The TradingAgents add-on now separates instrument research from portfolio allocation. Selected ticker refreshes use the existing native graph in `--research-only` mode, and the existing whole-fund manager consumes that evidence while retaining responsibility for portfolio exposures and account recommendations. Fund-manager decisions include cross-review continuity and current/deferred intent. Both remain advisory; observed portfolio snapshots do not establish trade fills.

## Details

Implemented behavior and durable boundaries:

- The native `--research-only` profile uses the existing agent graph for only the tickers selected by the caller. The wrapper omits `--portfolio`, passes `--no-checkpoint`, and uses a separate `research_only_memory.md`. Native graph memory skips reading, settling, and writing portfolio-aware decisions in this profile; old memory is preserved. The auxiliary `ARGUS_MACRO_CONTEXT_FILE` is rejected because it can carry whole-book context.
- The profile emits versioned `research_brief.json` alongside the native agent reports. It retains supported optional valuation targets/ranges and thesis horizons; unsupported values remain unknown. Existing model and effort selection remain configured. Saved custom system-prompt replacements are suppressed for native seats in this profile so they cannot restore account-specific sizing instructions. The fund-manager and theme-scout prompt configuration is not affected by this native prompt guard.
- The whole-fund manager remains the single owner of exposures, account-specific quantities, and review horizons. It sees all holdings and active watchlist candidates, regardless of selected ticker refresh scope. It reads validated research briefs or legacy analyst evidence with explicit provenance; old trader sizing and portfolio-manager/research-manager allocation advice are not current sizing authority. Coverage marks missing/dated evidence without forcing additional paid refreshes.
- Fund-manager continuity in `addons/fund_manager/decision_continuity.py` selects an eligible prior completed review and compares it with account-local observed snapshot quantities and timestamps. Complete snapshots distinguish known-zero positions from unknown quantities. Prior-review eligibility and ordering prefer precise UTC generation instants against the current-run boundary. New York report dates and run-directory ordering are fallback only when timestamps are unavailable; repeated local clock hours are disambiguated by precise instants when present. Snapshot chronology remains unknown when evidence is incomparable or ambiguous. Quantity changes are not attributed to executions.
- Decisions include proposed `target_shares`, a review horizon, sizing rationale, and `execution_intent` (`current`, `deferred`, or `none`). Deferred advice requires a future condition and contributes zero effective shares, fees, and cash movement to current validator results. Only current proposals enter the existing advisory account validation; hard cash, fee, price, sellability, and position constraints remain there. A hypothetical post-trade quantity remains distinct from observed holdings.
- Decision encoding is explicit: HOLD means `shares: 0` and `execution_intent: none`; a future review or possible opportunity does not make it a deferred order. A deferred recommendation is an actual conditional BUY/SELL with positive proposed shares and a future condition. `target_shares` describes total proposed exposure, while `shares` describes order quantity. `fund_manager.py` places this fixed contract in shared runtime context, so it reaches draft and final calls and remains present when a configured system prompt replaces the built-in prompt. The v2 schema describes the same field semantics; deterministic validation still rejects contradictions rather than rewriting model output.
- Fund-manager report/recovery schemas are versioned. `reprocess_response.py` retains the legacy schema registry alongside v2 schemas so old saved responses can be recovered without a model call. Recovery outputs remain separate and are not continuity baselines.
- No automatic paid refresh, broker order path, fixed allocation, execution ledger, or new trading-frequency rule was introduced. Weekly/earnings-driven ticker refresh remains under existing run selection. This system remains decision support: snapshots do not prove fills, model guidance is not guaranteed economically optimal, and a daily-bar label alone may not establish completed-session trigger semantics.

Key source paths in the sibling TradingAgents checkout:

- `cli/main.py`, `tradingagents/graph/trading_graph.py`, `tradingagents/graph/setup.py`, `tradingagents/reporting.py`, and `addons/agent_config.py`: native research profile, graph reuse, reporting, and prompt/model configuration boundary.
- `addons/fund_manager/fund_manager.py`: versioned research brief validation, whole-book context, continuity instructions, coverage, and v2 decision schema.
- `addons/fund_manager/decision_continuity.py`: eligible prior review selection, timestamp/quantity comparisons, and observed-versus-hypothetical position results.
- `addons/fund_manager/trade_validation.py`: immediate/deferred advisory validation.
- `addons/fund_manager/reprocess_response.py`: legacy/v2 response schema selection.
- `addons/fund_manager/README.md`: operation, report, and offline-check guidance.
- Argus `run_analysis.py`, `run_inputs.py`, `server.py`, and `static/fund-trade-render.js`: selected refresh wiring, fingerprint inputs, API, and report display.

Useful offline commands (run from the respective repository root):

```bash
# TradingAgents
.venv/bin/python -m pytest -q tests/test_research_only_profile.py tests/test_structured_agent_prompts.py tests/test_structured_agents.py tests/test_reporting.py tests/test_portfolio_context.py tests/test_cli_commands.py tests/test_graph_end_to_end.py
.venv/bin/python addons/fund_manager/check_decision_contract.py
.venv/bin/python addons/fund_manager/check_trade_validation.py
.venv/bin/python addons/fund_manager/check_response_recovery.py
.venv/bin/python addons/fund_manager/check_offline.py
.venv/bin/python addons/check_run_native_research_guard.py

# Argus
.venv/bin/python check_runner_offline.py
.venv/bin/python check_runner_budget_offline.py
.venv/bin/python check_offline.py
node check_fund_manager_ui_offline.js
```

These fixture checks make no paid or live-model calls and do not establish live market-provider correctness, broker access, or PowerShell runtime behavior. `check_agent_config.py` needs `ARGUS_AGENT_CONFIG` pointed at an isolated temporary configuration path for deterministic fixture expectations; do not modify the live seat config to satisfy the check. Consult the active Opmentix plan for current implementation, independent review, and acceptance evidence.

## Logs

- 2026-11-20 11:19 UTC — Recorded HOLD/deferred encoding and runtime-context ownership after the run-validation failure exposed prompt ambiguity.

- 2026-11-18 16:18 UTC — Removed temporary review-state wording; preserved live-validation and Windows-runtime limitations.

- 2026-11-18 16:07 UTC — Clarified UTC-first prior-review selection and linked current status to the active plan.

- 2026-11-18 16:06 UTC — Replaced proposed continuity guidance with implemented research-profile and decision-continuity contracts; recorded test scope and review limits.

- 2026-11-18 10:39 UTC — Added durable traps around stale portfolio sizing advice, target versus incremental quantities, debate continuity, staging semantics, and daily-bar timestamp ambiguity.
- 2026-11-18 10:27 UTC — Corrected study references to separate review days, excluding the earlier November 17 report.

- 2026-11-17 15:44 UTC — Added verified fund-manager continuity behavior, source paths, and clearly marked unimplemented design direction.
