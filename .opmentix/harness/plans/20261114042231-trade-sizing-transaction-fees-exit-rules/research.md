# Trade sizing, fees, exits and multi-account portfolio study

This notebook is supporting discovery for the end-to-end delivery in [plan.md](./plan.md). The owner clarified that completion requires code/configuration changes, independent review and verification; research alone is not the deliverable. Remaining discovery must resolve decisions before implementation approval within the same plan.

## Question

What entry and exit guidance makes trades economically worthwhile after approximately $3 per side, while respecting risk, and how can Argus represent Tiger plus Moomoo Singapore holdings accurately?

Study the owner's proposed US$1,000 order/holding guideline for swing and long-term investments; distinguish these thresholds and account scope before recommending policy. Determine read-only Moomoo feasibility and correct same-stock calculations within and across accounts.

Also map removal of the owner's unwanted hardcoded AI subthemes and audit owned config JSON for obsolete properties. Produce a concrete removal/cleanup checklist; avoid introducing a replacement fixed taxonomy or discarding still-used settings.

First establish which requested capabilities already exist in native TradingAgents settings/contracts before proposing changes to our customization in `addons/`.

## Findings

Preliminary evidence only; the full study is pending.

- The fund-manager risk policy and validator currently have no commission model or minimum trade/residual notional. Whole-share quantities and sell caps already exist.
- Tiger duplicate rows are quantity-weighted within a snapshot, but applying the snapshot replaces the entire portfolio book. Current normalized positions have no account identity; mixed currencies are blocked.
- The approved portfolio mix remains flexible 10% cash / 30% long-term / 60% swing guidance. A proposed minimum must be assessed against risk and available capital.
- Public Moomoo documentation is a starting point; the owner's Singapore account/API access and cost-field semantics need verification. No connection has been attempted.
- Subtheme definitions and fallbacks span `server.py`, dashboard UI, fund-manager calculations/prompts/reports and `addons/fund_manager/themes.json`. Theme scout transports `sub_theme`; deleting mappings alone does not remove the behaviour.
- AI sleeve weights, general theme buckets and subthemes are distinct mechanisms. Candidate config keys require a reader/default audit across Argus, fund manager, scout and spending logic. In particular, duplicated budget settings have precedence rules and cannot be declared unused solely because they look redundant.
- Follow-up researcher inventory identified `weights_pct` in live targets as a cleanup candidate because approved-target readers intentionally ignore legacy unapproved weights. Retain a before/after key inventory without copying private values; never replace live targets with the bundled example.

### Native TradingAgents assessment — 2026-11-14

Read-only researcher inspection of package/CLI outside `addons/`, cross-checked against Argus runner. The checkout is the owner's `caydenchongzq/TradingAgents` fork at `6d26628`; the worktree was clean. Native-package placement is verified, current canonical-upstream parity is not. No network or model calls were used.

| Requirement | Native support and implication |
| --- | --- |
| Holdings, average entry cost and available cash | Supported through `PortfolioContext` and CLI `--portfolio`; passed to trader, risk debaters and final decision agent. Argus already supplies this on ticker runs. Reuse this contract. |
| Sizing | Trader emits optional free-text `position_sizing` with numeric entry/stop levels. Useful advice, but no validated share/order-notional contract, fee input or minimum trade setting was found. |
| Full versus partial exits | Native final ratings describe Underweight as a reduction and Sell as exit/avoid entry. No deterministic sell-all, sellable-quantity or minimum-remainder setting was found. |
| Multiple accounts and Moomoo/Tiger import | Native positions have ticker, quantity and average price, with one cash/currency context. No broker/account identity or broker adapters were found. Repeated symbol rows can be rendered but are not account-aware cost/cash accounting. |
| Swing versus long-term | No persistent owner investment role in native position schema. `holding_period_days` controls outcome measurement/reflection and backtest evaluation, not strategy selection or a required holding duration. |
| AI subthemes | No AI subtheme/sleeve configuration found in native package/CLI. These originate in our customization; removing them does not require replacing a native taxonomy. |
| Native configuration generally | Models/providers, reasoning, debate/tool limits, data vendors, news lookbacks, language, cache/memory/checkpoints and benchmarks are configurable. None establishes the requested fee/minimum/residual rules. |
| Whole-portfolio management | The native portfolio manager resolves the risk debate for the analyzed instrument, using portfolio context. It is not an account-aware whole-book allocator or broker execution/validation engine. |

Provisional design implication: keep native single-instrument research and portfolio-context plumbing; determine the smallest deterministic policy/account layer only for unmet requirements. Native advisory text must not be presented as an enforced financial constraint. No native or add-on configuration was changed.

## Sources

Local preliminary references, inspected 2026-11-14:

- `../TradingAgents/addons/fund_manager/fund_manager.py`: `RISK_POLICY`, `validate_trades`, portfolio guidance and role handling.
- `../TradingAgents/addons/fund_manager/check_offline.py`: assertion that `min_trade_usd` is absent.
- `tiger_import.py`: `normalize_snapshot`, quantity-weighted duplicate aggregation and single-book normalization.
- `server.py`: `/api/portfolio` reads the single book and computes quantity × price and acquisition-cost P/L.
- `README.md` and `.opmentix/harness/knowledge/project-guide.md`: import limits, read-only boundaries and existing owner guidance.
- `server.py`, `static/app.js`, `static/index.html`, `run_inputs.py`: subtheme UI/API consumers, fallbacks and config fingerprints.
- `../TradingAgents/addons/fund_manager/themes.json` and bundled `targets.json`: hardcoded taxonomy and example settings; distinguish these from active `data/targets.json` during the audit.
- `../TradingAgents/addons/theme_scout/theme_scout.py` and `../TradingAgents/addons/cost_ledger.py`: additional tag/AI-weight consumers and spending-setting precedence.

Native assessment references:

- `../TradingAgents/tradingagents/default_config.py`: `build_default_config`, environment override inventory and evaluation-only `holding_period_days` comment.
- `../TradingAgents/tradingagents/portfolio.py:25`: `Position`/`PortfolioContext` schema, render/matching and input loading. `README.md:312` documents holdings support.
- `../TradingAgents/cli/main.py:48` and `tradingagents/graph/trading_graph.py:179`: CLI input and graph propagation.
- `../TradingAgents/tradingagents/agents/schemas.py:180`: advisory position sizing; `agents/managers/portfolio_manager.py:42`: single-instrument final ratings and context.
- `../TradingAgents/tests/test_portfolio_context.py`: existing unit scenarios cover missing versus flat context, symbol aliases, validation and decision-agent context threading. Tests were inspected, not run.
- `run_analysis.py:338`: native ticker command passes `--portfolio` using the current book.
- Local Git status/remote/history: clean fork at `6d26628`; portfolio feature history includes `6436d1f`. Upstream was not fetched or independently verified.

Official documentation leads to verify during T4; these do not establish live access for the owner's account:

- [Moomoo position query and cost fields](https://openapi.moomoo.com/moomoo-api-doc/en/trade/get-position-list.html)
- [Moomoo Singapore position-cost explanation](https://www.moomoo.com/sg/support/topic5_37)
- [Moomoo API portal](https://open.moomoo.com/)

## Conclusion

No final policy recommendation yet. Use the tasks and acceptance criteria in [plan.md](./plan.md) to complete the study. Treat $3 as an approximate per-side fee and USD as the illustrative fee currency until confirmed. US$1,000 is a candidate guideline, and a 10% gain is an arithmetic example, not an expected return.

The native-first assessment is complete for the installed checkout: native portfolio context can be reused and is already wired. Fee rules, minimums, residual exits and broker-account calculations remain demonstrated gaps for subsequent research. Reassess upstream only if a version comparison or upgrade becomes part of the implementation decision.

## Logs

- 2026-11-14 12:10 UTC — Reclassified this notebook as supporting discovery for the same plan's code delivery; research-only completion is excluded.
- 2026-11-14 11:47 UTC — Added native capability matrix, source/provenance evidence and native-first reuse recommendation; no runtime changes or paid validation.
- 2026-11-14 10:59 UTC — Added AI subtheme removal and configuration cleanup questions, preliminary dependency findings and source references; no runtime configuration changed.
- 2026-11-14 04:23 UTC — Opened research notebook with preliminary evidence and source leads; full study and owner decisions remain pending.
