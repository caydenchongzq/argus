# Discovery evidence — native-first portfolio improvements

## Question

Which native TradingAgents capabilities can be reused, what trade-policy defaults fit the owner's fee/size preferences, how should overlapping broker positions be represented, and exactly which AI subtheme/configuration properties can be removed?

This is supporting discovery for the [normal implementation plan](./plan.md). Source/API investigation and economic comparisons are complete. Implementation, offline integration verification and actual broker connectivity are not completed research claims.

## Findings

### Native reuse and current defects

The installed `caydenchongzq/TradingAgents` fork at `6d26628` has native `PortfolioContext` (positions, optional average cost and optional cash/currency), CLI `--portfolio`, and graph threading to trader/risk/final-decision agents. Argus already supplies the portfolio. Native trader sizing is free text; native final Underweight/Sell is qualitative. There is no native broker/account identity, fee input, enforced minimum or residual rule. `holding_period_days` measures outcomes; it does not set investment intent. Native package code needs no change for this plan; current canonical upstream parity was not claimed or fetched.

Current customized `validate_trades` casts shares with `int()`, allows model price estimates, warns rather than rejects overspending, ignores commissions and computes percentages using pre-fee equity. Its single-ticker keys cannot distinguish the same instrument across accounts. The dashboard's `check.trades or decision.trades` can resurrect raw proposals if a validated list is empty. New validation must be the source for actionable tables, state and post-fee risk, with explicit accepted/adjusted/rejected/HOLD status and original proposals retained only as history.

### Economics and policy recommendation

Using an illustrative flat US$3 per buy and per sell, round-trip fees are US$6 before spread, slippage, taxes and other charges. The currency and fee are planning assumptions from the owner's estimate, not verified tariffs. Scenarios are arithmetic, not return forecasts.

| Purchase notional | Fee-only break-even | Net at +3% | Net at +5% | Net at +10% | Net at -5% |
| --- | --- | --- | --- | --- | --- |
| $500 | 1.2% | $9 | $19 | $44 | -$31 |
| $1,000 | 0.6% | $24 | $44 | $94 | -$56 |
| $2,000 | 0.3% | $54 | $94 | $194 | -$106 |

Host verified these figures using Python Decimal arithmetic and assertions. Larger positions make the same percentage gain/loss larger and reduce fee drag as a percentage; they do not make the investment safer. At a 5% stop, a $1,000 position risks approximately $50 plus fees before gaps/slippage. If that exceeds the trade risk budget, skip the trade rather than increase it to meet a minimum.

Two $500 purchases cost $6 to enter, compared with $3 for one $1,000 purchase. Different purchase dates/prices can dominate the $3 saving; batching reduces fees but does not prove superior market returns. Recommend $1,000 per-account/order buy floor for swing and long-term purchases, including top-ups; no arbitrary desired-profit or fixed stock-count target. Holding count should follow available capital, conviction and concentration, with the existing soft portfolio mix preserved.

Recommend an explicit EXIT close the available position, and convert a partial trim leaving a positive value below $1,000 into a visibly adjusted full-exit recommendation where possible. Example: 15 shares at $100, proposed sell 10, leaves $500: recommend 15; proposed sell five leaves exactly $1,000: retain five. A necessary $600 sale remains allowed. Do not force action on existing small holdings or sell unavailable units. Existing fractional balances can be included in a complete exit recommendation; no fractional purchases are introduced. If availability/cash cannot be verified, label the result unvalidated rather than claim full closure.

The implementation defaults are in `plan.md`; plan approval approves those defaults. One order per row permits a defensible $3 estimate. Staged/duplicate rows without concrete single-order meaning are rejected. Valid sells precede buys in the hypothetical cash simulation, and only net proceeds from that account are usable. Cash, equity and derived metrics must include fees, and remain unknown when inputs are unknown.

### Account, price and cost design

One canonical versioned `my_book.json` with `accounts[]` and derived top-level compatibility fields avoids a fragile second portfolio file. The shared stdlib `addons/portfolio_book.py` can be imported by Argus (which already adds `ADDONS` to its Python path) and add-on readers. Native research receives the aggregate projection; custom trade validation receives per-account records. Account identity and a selected-account replace operation prevent cross-broker overwrite/double-counting.

Repeated buys in one account: 10×$100 + 5×$120 = $1,600 acquisition cost, 15 shares and $106.6667 average before additional fees. The same two holdings across Tiger and Moomoo produce identical consolidated arithmetic while preserving each account's own cost and quantity. At a common $130 mark, value is $1,950 and unrealized gain $350. Unrounded costs feed calculations; round only presentation. Never average account averages without quantity weights.

Broker `average_cost` is preserved with its documented cost-method/source; do not invent historic fees, realized gains or tax lots. Incompatible definitions or a missing constituent cost produce unknown consolidated acquisition cost/P&L. Diluted cost includes realized-trade effects and is stored separately, never substituted. Selling shares in one account changes only its holdings and cash; subsequent snapshots supply the authoritative remaining broker average.

USD US-listed stocks/ETFs are the supported first-version projection. Other markets/currencies are disclosed as excluded, with no FX conversion. Snapshot completeness refers to that selected scope. Partial/failed/stale refreshes do not erase the last good snapshot. Legacy single books are wrapped on reviewed writes with backup, with explicit replace-legacy versus add-account selection so existing Tiger holdings are not duplicated.

### Moomoo Singapore verification and limitation

Researchers fetched official SDK sources and docs read-only. Official SDK `SecurityFirm.FUTUSG` is labelled Moomoo SG; account list supplies market authorization/status and account/position queries exist. Implementation inspected the pinned 10.12.7208 distribution and verified its constructor is `OpenSecTradeContext(filter_trdmarket=TrdMarket.US, security_firm=SecurityFirm.FUTUSG)`. The earlier main-branch `OpenUSTradeContext` reference is not present in that pinned distribution; the pinned source controls the adapter and its fixture constructor assertions. Use optional `moomoo-api==10.12.7208` plus an installed compatible local OpenD gateway. Import lazily in Argus' optional broker environment; no SDK install or account sign-in was performed during discovery. No order or unlock methods are needed.

Position results include instrument/market/currency, `qty`, `can_sell_qty`, `average_cost`, `diluted_cost`, `cost_price` and `cost_price_valid`. Accept finite positive `average_cost` as broker acquisition average with provenance; otherwise keep unknown. `cost_price_valid` applies to the generic cost-price field (diluted for securities), not an independent acquisition-average validity flag.

**Cash is not safely established by `currency=USD`.** Official funds protocol says that parameter is ignored for non-comprehensive accounts. `cashInfoList` is documented as futures-only; SDK `us_cash` maps from that list. Securities cash/withdrawal amounts and net cash power do not prove a USD-denominated unleveraged cash balance. Do not use `cash`, `available_funds`, `power` or `usd_net_cash_power` as a replacement.

Chosen implementation: import usable Moomoo holdings and costs with `cash: null` when verified USD cash is unavailable. Reject actionable trades for that account; do not silently assign zero, inherit Tiger cash or count buying power. If any account cash is unknown, consolidated cash/equity/cash percentage/whole-book risk denominators remain unavailable. Show priced holdings value and a labelled known-cash subtotal. Native `PortfolioContext.cash` already permits null; fund-manager/scout/dashboard coercions and formatting must change. Known accounts may still produce account-local validated proposals, without a claim that whole-book risk is fully assessed. This supports useful combined holdings now without inventing cash or adding a manual-balance service.

Live SG account entitlement, OpenD compatibility and actual response shape remain explicit deployment verification items. This does not block finishing the implementation design; fixture tests cannot establish live authorization. A valid USD cash field can be enabled only with documented or controlled live evidence, not guessed from field names.

### Configuration and AI subtheme inventory

Keys-only inspection of live settings avoided copying private values. Remove the following only after code/schema consumers are updated:

| Property/feature | Decision and reason |
| --- | --- |
| `themes.json.subthemes`, `subtheme_labels`; code fallback categories; new `sub_theme` fields | Remove fixed AI subtheme feature across backend/UI, fund-manager stats/prompts/reports and scout schema/grouping/versioning. JSON-only deletion resurrects fallback constants. |
| `weights_pct` | Remove live/template legacy unapproved allocations: approved-target reader intentionally ignores them; only `approved_targets_pct` is authoritative. |
| `is_guidance` | Remove unused config key: no runtime reader found. |
| Persisted curator `cooldown_days`, `max_adds_per_week`, `max_drops_per_week`, `shadow`, `shadow_until` | Remove no-op saved controls and write paths. Scout currently fixes cooldown to 14 days, weekly caps to unlimited and review/shadow behaviour; deleting keys must not change those effective choices. |
| General `themes`/`buckets` | Keep active concentration and theme-weight readers. |
| `ai_sleeve` weights/cap/as_of/source | Keep separate active AI look-through analytics and provenance; UI warning cap is advisory. Subtheme removal is not authorization to silently discard all AI analytics. |
| `cash_policy`, `portfolio_guidance`, approved targets | Keep active owner settings; no mandatory rebalance added. |
| `budget`, top-level `weekly_budget_usd` | Keep active precedence/compatibility; all estimate/enabled fields have readers. Preserve disabled spending checks. |
| `_note`, model config, candidate/sector limits, unrelated metadata | Preserve: documentation, active behaviour or unrelated user data. |

Current watchlist `sub_theme` tags can be stripped in a backed-up migration, preserving wrappers/order/other fields. Do not rewrite immutable event history or saved reports. Remove `sub_theme` from scout proposal schema and version semantics, and reject stale pre-change proposals through existing input-version checks. Whole config/book fingerprints already invalidate reviewed manifests when content changes; include new shared-contract code in run fingerprints too.

Migration uses shared `.argus-run.lock`, expected hashes, full prevalidation, timestamped backups and atomic writes. For a multi-file cleanup failure, restore already-replaced files from backups and report the failure. Test this with temporary fixtures; never test against the real book. No general-purpose schema service or unrelated cleanup is needed.

## Sources

Local evidence inspected on 2026-11-14:

- `tradingagents/default_config.py`, `tradingagents/portfolio.py`, `cli/main.py`, `tradingagents/graph/trading_graph.py`, `tradingagents/agents/schemas.py`, `tradingagents/agents/managers/portfolio_manager.py`, native README and `tests/test_portfolio_context.py` in the sibling checkout: native capabilities/limitations. Native tests were inspected, not executed.
- `../TradingAgents/addons/fund_manager/fund_manager.py`: `RISK_POLICY`, `validate_trades`, `TRADE_ITEM`, `render_plan_trades`, stats/risk/log/context paths; `check_offline.py`: legacy-weights and minimum-policy assertions.
- `server.py`: `_decision_bundle`, portfolio rendering, settings read/write, Tiger account aliases/preview/apply and `_data_write_lock`; `run_analysis.py`: native portfolio handoff; `run_inputs.py`: reviewed input fingerprints.
- `tiger_import.py`: cost normalization, currency completeness, duplicate aggregation and atomic backup replacement.
- `../TradingAgents/addons/fund_manager/themes.json`, bundled `targets.json`, live targets key inventory: keep/remove audit.
- `../TradingAgents/addons/theme_scout/theme_scout.py`: subtheme schema, grouping/versioning and fixed curator settings; `../TradingAgents/addons/cost_ledger.py`: budget alias precedence; `static/app.js`/`static/index.html`: visible controls and rendering.

Official external sources fetched by `moomoo_discovery` (2026-11-14):

- [Official Python SDK setup/OpenD](https://github.com/MoomooOpen/py-moomoo-api)
- [SDK trading contexts and query signatures](https://github.com/MoomooOpen/py-moomoo-api/blob/main/moomoo/trade/open_trade_context.py)
- [Singapore firm enum](https://github.com/MoomooOpen/py-moomoo-api/blob/main/moomoo/common/constant.py)
- [SDK fund/position output mapping](https://github.com/MoomooOpen/py-moomoo-api/blob/main/moomoo/trade/trade_query.py)
- [Funds request currency semantics](https://github.com/MoomooOpen/py-moomoo-api/blob/main/moomoo/common/pb/Trd_GetFunds.proto#L9-L17) — currency ignored except comprehensive accounts.
- [Cash field scope](https://github.com/MoomooOpen/py-moomoo-api/blob/main/moomoo/common/pb/Trd_Common.proto#L339-L364) and [per-currency cash record](https://github.com/MoomooOpen/py-moomoo-api/blob/main/moomoo/common/pb/Trd_Common.proto#L298-L305) — per-currency cash list documented for futures.
- [SDK per-currency cash mapping](https://github.com/MoomooOpen/py-moomoo-api/blob/main/moomoo/trade/trade_query.py#L213-L245) — explains why a USD-looking field name does not prove securities cash availability.
- [Position fields and cost semantics](https://openapi.moomoo.com/moomoo-api-doc/en/trade/get-position-list.html)
- [Account list and authorization fields](https://openapi.moomoo.com/moomoo-api-doc/en/trade/get-acc-list.html)
- [SDK package/version](https://pypi.org/project/moomoo-api/)
- [Singapore cost-basis explanation](https://www.moomoo.com/sg/support/topic5_37) — supporting lead; protocol/SDK evidence controls adapter field use.

## Conclusion

Discovery is complete for planning. Reuse native research/context, add deterministic policy/account logic in the existing add-on boundary, introduce a single-file account book, implement read-only Moomoo positions with explicit unknown-cash semantics, remove fixed AI subthemes and only audited obsolete configuration properties.

The normal plan contains the proposed defaults, exact file changes, migration approach and focused acceptance tests. No further architecture/provider decisions are delegated to the implementer. The plan subsequently received implementation approval; code, deployment and the backed-up settings cleanup are now delivered with independent review and offline verification recorded in `plan.md`. Live Moomoo connectivity and SG account authorization remain explicitly untested. This notebook retains discovery evidence rather than serving as a live delivery-status record.

## Logs

- 2026-11-15 01:40 UTC — Linked discovery conclusions to completed implementation/migration and final acceptance evidence; retained explicit live broker limitations.

- 2026-11-14 16:31 UTC — Implementation verified the pinned SDK distribution and corrected the constructor to OpenSecTradeContext with a US filter; current API examples were insufficient for this version-specific detail.

- 2026-11-14 14:22 UTC — Added exact official protocol/source citations for the Moomoo cash limitation; discovery-to-plan approval requested with complete implementation plan.
- 2026-11-14 14:20 UTC — Planner sanity review accepted null-cash holdings design and clarified fractional exit schema, malformed-policy preflight and hypothetical-versus-available cash; incorporated in implementation plan.
- 2026-11-14 14:13 UTC — Finished economic comparisons, source/API investigation, cash-semantic limitation, account contract and per-key config audit; replaced provisional notes with implementation-ready conclusions and verified/untested boundaries.

- 2026-11-14 13:59 UTC — Carried supporting discovery forward to the normal implementation plan; research remains a prerequisite to code delivery.

- 2026-11-14 12:10 UTC — Reclassified this notebook as supporting discovery for the same plan's code delivery; research-only completion is excluded.
- 2026-11-14 11:47 UTC — Added native capability matrix, source/provenance evidence and native-first reuse recommendation; no runtime changes or paid validation.
- 2026-11-14 10:59 UTC — Added AI subtheme removal and configuration cleanup questions, preliminary dependency findings and source references; no runtime configuration changed.
- 2026-11-14 04:23 UTC — Opened research notebook with preliminary evidence and source leads; full study and owner decisions remain pending.
