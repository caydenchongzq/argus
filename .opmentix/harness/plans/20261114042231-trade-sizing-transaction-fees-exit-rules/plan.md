---
id: 20261114042231-trade-sizing-transaction-fees-exit-rules
title: Native-first portfolio improvements — sizing, fees, exits, accounts and configuration cleanup
---

## Brief

**Superseded:** use the [normal implementation plan](../20261114135901-native-first-portfolio-improvements/plan.md). This original research record is retained for provenance only; do not implement or advance it. Cancellation is a human harness action, so its server-owned lifecycle state is left unchanged.

Deliver code changes for practical trade sizing, fees, exit behaviour, a combined Tiger/Moomoo Singapore portfolio, removal of hardcoded AI subthemes and obsolete configuration cleanup. Complete necessary research as preparation for implementation within this plan. The owner questions sub-US$1,000 swing purchases and small leftover holdings, estimates approximately $3 per buy or sell, and prefers batching long-term purchases around $1,000 too. These are candidate policy defaults to resolve before implementation approval, not already enforced rules.

Deliver a sourced decision record followed by implementation, focused tests, independent review and behavioural acceptance. Planning includes application and add-on changes plus a safe migration of owned settings; implementation begins after the harness Plan approval gate. No broker orders or paid model runs are needed for acceptance. Broker credentials stay local; live import requires the existing reviewed preview/apply flow. Do not replace the owner's book during research or testing.

Lifecycle: retain this plan identity and follow Discovery → Plan → Implementation → Review → Acceptance → Close. Although originally created with harness `kind: research`, that kind can follow the full lifecycle. Do not use its optional research-only closure path; code delivery and independent verification are required before closure. Leave server-owned state/history untouched.

Additional owner direction (2026-11-14): remove the hardcoded AI subtheme taxonomy and clean up configuration JSON properties that no longer serve a purpose. The removal is the desired outcome; research must identify its full dependency chain and safe cleanup scope before implementation. Do not replace it with another fixed taxonomy.

Native-first direction: assess TradingAgents' existing native configuration and extension points before designing changes to our `addons/` or settings. Reuse native capabilities where they satisfy the requirement; add custom policy only for demonstrated gaps. Native means the package/CLI outside `addons/`; the local checkout is a personal fork, so do not assume it matches current upstream.

## Discovery

Research: [research.md](./research.md)

Preliminary discovery by `opmentix-researcher` (`research_scope`), 2026-11-14:

- Sizing and trade validation belong to the sibling TradingAgents fund manager, not just the Argus dashboard. Its `RISK_POLICY` has no minimum notional; its offline check explicitly asserts no `min_trade_usd`. `validate_trades` uses whole-share quantities and caps oversells but does not account for commissions or prevent small remainders.
- Argus reads a single book with ticker, quantity and average price. Tiger import replaces that book, aggregates duplicate market/symbol rows with quantity-weighted average cost, and blocks mixed currencies. Adding Moomoo through the existing replacement path would lose the Tiger book.
- The existing approved 10% cash / 30% long-term / 60% swing mix is flexible guidance. Preserve its soft cash reference, flexible holding period and sector guidance while studying new trade rules.
- Moomoo API/cost-basis public documentation is a research lead. Singapore account eligibility, authentication route and actual cost fields remain unverified for this owner. A broker's diluted cost must not silently become acquisition average cost.
- Hardcoded AI subthemes exist in both Argus and TradingAgents: dashboard labels/groupings, watchlist input validation, fund-manager defaults/stats/prompts/reports, and `addons/fund_manager/themes.json` (`subthemes`, `subtheme_labels`). Theme scout also transports `sub_theme`. Removing JSON mappings alone leaves code defaults that recreate the categories.
- AI look-through weighting (`ai_sleeve`) is a separate mechanism from subthemes, and general theme/bucket classification has additional readers. Audit these and legacy target settings individually; their presence in old templates does not prove they are unused. `run_inputs.py` fingerprints theme configuration, so config/source cleanup also affects reviewed-run freshness.
- Follow-up `opmentix-researcher` keys-only inventory found live `weights_pct` despite readers deliberately ignoring unapproved legacy weights; this is a strong cleanup candidate. Live targets are distinct from the bundled example. Budget fields have precedence and AI weights still have consumers, so wholesale template replacement or blind deletion is unsuitable. No user values were copied to this plan.

Open decisions: hard minimum versus guidance; minimum per order versus position; partial-trim exceptions; treatment per account versus consolidated holding; fee currency and broker-specific charges; markets/currencies actually needed. Research should recommend defaults and show tradeoffs before asking the owner to decide.

Planning handoff: `opmentix-planner` (`research_plan_tasks`) supplied the study breakdown, ordering and worked-example acceptance criteria. Native assessment is complete; other discovery decisions and implementation remain open. The owner's latest direction explicitly includes code delivery; a report alone is not completion. No closure or stage advance requested.

Native-first follow-up by `opmentix-researcher` (`research_scope`), 2026-11-14: native `PortfolioContext` plus CLI `--portfolio` already supplies holdings, acquisition averages and cash to trader/risk/decision agents. Argus already passes `--portfolio` on native runs. Sizing and partial/full exit descriptions are advisory; no native commission/minimum/residual rule or broker/account identity was found. Native configuration controls model/data/debate behaviour and outcome evaluation; `holding_period_days` evaluates outcomes and is not a swing/long-term investment mandate. See research notebook for capability matrix and source references. Static inspection only; no paid run or broker access.

## Plan

Execution order: T10 → T1, then T2/T3 (trade economics), T4/T5 (accounts) and T8/T9 (cleanup). Complete those before T6 locks decisions and implementation interfaces. After Plan approval, establish T12 account boundaries, deliver T11/T13/T14 against those interfaces, then T15 config migration, T16 independent verification and T7 curation/closure. Keep task IDs stable; the three discovery workstreams can run independently after T1.

- [x] T10: Assess native TradingAgents settings and contracts before custom add-on design.
  - `research.md`: researcher-sourced capability matrix identifies reusable portfolio context, advisory sizing/exit output and gaps in fees, hard minimums, account-aware aggregation and investment roles. Record local-fork provenance and distinguish absence of a setting from lack of any useful native capability. Completed by source inspection; current upstream parity remains unverified.
- [ ] T1: Trace the current recommendation, validation, import and display paths; distinguish current behaviour from the owner's desired rules.
  - `research.md`: document source references and existing guardrails, including whole-share rounding, cash, investment roles and sibling-repository ownership.
- [ ] T2: Compare economical entry sizes for swing and long-term purchases, including new positions and top-ups.
  - `research.md`: compare $500/$1,000/$2,000 at illustrative 3%/5%/10% gains, $3 per side, fee break-even, loss scenarios and repeated small purchases. Evaluate position-count guidance against capital, concentration and stop risk; never enlarge a risky trade merely to meet a floor.
- [ ] T3: Recommend exit behaviour and exceptions.
  - `research.md`: distinguish full exit, partial trim and risk-reducing sale; compare hold, trim and close when a trim leaves under $1,000. Cover existing small holdings, whole-share rounding and per-account remainders; minimums must not trap a necessary exit.
- [ ] T4: Verify Moomoo Singapore read-only API feasibility using official sources.
  - `research.md`: identify account/position/cash endpoints, eligibility, authentication/runtime requirements, costs and average/diluted cost semantics. Distinguish documented support from untested account access; document a later local read-only verification checklist without connecting accounts now.
- [ ] T5: Specify account-aware calculations and import behaviour without implementing them.
  - `research.md`: recommend account snapshots plus a consolidated exposure view, account-scoped refresh rather than full-book overwrite, account-specific cash/sell quantities/fees, and explicit cost provenance. Work through repeated buys in one account, overlapping stocks across accounts, partial sales, unavailable cost data, duplicate refreshes, stale/failed snapshots and mixed currencies. Restrict aggregation to verified equivalent instruments and compatible currency/cost definitions.
- [ ] T6: Resolve discovery into a decision-complete implementation specification for this plan.
  - `plan.md`, `research.md`: lock fee currency/defaults, minimum order versus residual semantics, risk-exit exceptions, account scope, supported markets and cost-basis handling. Record concrete API/schema/migration changes and file ownership. Prefer native contracts; select custom behaviour only for demonstrated gaps. Resolve material owner policy decisions before requesting Plan-to-Implementation approval.
- [ ] T8: Map removal of hardcoded AI subthemes end to end, including producer defaults and saved tags.
  - `research.md`: specify removal from Argus portfolio/watchlist summaries, columns/forms/API validation and TradingAgents stats/prompts/reports/scout output; inventory hardcoded fallback labels and persisted `sub_theme` fields. Plan safe handling of existing watchlist wrappers/metadata and older reports without rewriting history. No replacement taxonomy or unrelated sector-scouter removal.
- [ ] T9: Audit owned configuration JSON and define minimal safe cleanup.
  - `research.md`: distinguish active `data/targets.json` from the bundled example and `themes.json`; list candidate keys with readers, defaults, precedence and keep/remove rationale. Include obsolete AI mappings, labels/cap/source metadata and legacy settings only when justified by actual usage or explicitly superseded behaviour. Treat AI sleeve weighting and general theme buckets separately from subtheme removal; identify owner decisions if their removal changes useful behaviour.
  - `research.md`: describe a backed-up, repeatable cleanup preserving approved portfolio guidance, model/spending/watchlist settings, holdings/costs and unrelated user metadata. Identify code consumers/tests to change before removing required properties; avoid missing-key fallbacks silently restoring removed behaviour. Complete T8/T9 before T6 synthesis and T7 curation.
- [ ] T11: Implement economical sizing, fee accounting and exit/residual policy end to end.
  - TradingAgents `addons/fund_manager/`: carry the approved settings into decision context and deterministic validation; calculate fees and resulting cash, distinguish entry/top-up/trim/full exit, and handle whole-share rounding. Respect available account cash, sellable quantities and risk exits; do not silently enlarge a trade to meet a floor.
  - Argus backend/UI and focused offline checks: expose only the policy controls and net-cost/remainder explanations needed for user decisions. Retain native `--portfolio` research/context wiring and the flexible portfolio mix.
- [ ] T12: Implement account-aware holdings, imports and consolidated calculations.
  - Argus portfolio/import backend and TradingAgents book-consumer boundary: preserve broker/account/currency identity and per-account cash/cost provenance; migrate the existing single book without losing holdings. Refresh one account without replacing others; build a compatible consolidated research view while retaining account-specific trade validation and display.
  - Offline fixtures/checks: cover duplicate symbols, weighted acquisition cost, partial sales, unavailable costs, repeated/stale/failed snapshots and currency boundaries. Do not infer realized P/L from position snapshots or merge unlike instruments/cost definitions.
- [ ] T13: Add read-only Moomoo Singapore import using the verified supported API path.
  - Moomoo adapter plus Argus preview/apply API/UI: reuse existing import safeguards where appropriate, keep credentials local, normalize documented cost fields and preserve Tiger data. Add only the SDK/runtime dependency demonstrated necessary by T4.
  - Adapter/guard checks: verify complete versus incomplete snapshots, unsupported holdings and retry behaviour with fixtures. Record live account compatibility separately; without access, deliver the tested integration and explicitly flag live verification as untested rather than claiming success.
- [ ] T14: Remove the hardcoded AI subtheme feature across all producers and consumers.
  - Argus backend/UI and TradingAgents fund-manager/theme-scout code and checks: remove hardcoded categories, fallback labels, subtheme-only controls/grouping, generated fields and prompt/report requirements. Keep historical reports readable and preserve unrelated sector discovery and portfolio roles; do not introduce a substitute fixed taxonomy.
- [ ] T15: Clean owned JSON configuration and obsolete persisted tags safely.
  - Active user settings, theme config and bundled examples: apply the T9 keep/remove inventory after consumers/defaults are fixed. Back up before migration, preserve unrelated values/wrappers and make cleanup repeatable; handle removed keys without recreating hardcoded defaults.
  - Config API/UI, run-input fingerprints, documentation and migration checks: keep the effective settings and saved-run freshness aligned. AI sleeve weighting/general theme buckets remain separate decisions, not automatic casualties of subtheme removal.
- [ ] T16: Verify implemented behaviour and complete the independent review loop.
  - Relevant Argus and TradingAgents offline checks: test fee/cash arithmetic, entry/exit boundaries, account isolation, cost provenance, import guards, JSON preservation and absence of subtheme fallbacks. No paid analysis or real portfolio mutation in tests.
  - `plan.md`: record implementer test evidence, independent reviewer rounds and fixes, then independent verifier results against every delivery criterion. No implementation-stage advance before tests pass and independent review is clean.
- [ ] T7: Curate delivered behaviour and prepare final human acceptance.
  - `plan.md`, `research.md`, project guide and knowledge if justified: delegate `opmentix-curator`, document effective policy, schema/migration, native/custom ownership, tests, rollback and any live-verification limits. Request closure only after code delivery, clean independent review and acceptance evidence.

Discovery acceptance (required before implementation approval):

- Reproducible arithmetic shows $500 at a 10% gain yields $44 after $6 round-trip fees; $1,000 yields $94. Fee drag is 1.2% and 0.6% respectively, before other costs. Illustrative returns are not forecasts; fee currency remains an assumption until verified.
- A recommendation explicitly separates minimum order size, target position size and residual position value; compares swing versus long-term use; preserves risk/cash constraints and explains partial-exit exceptions.
- A same-account example (10 shares at $100 plus 5 at $120) produces 15 shares at $106.67 acquisition average before fees. An across-account example preserves both account rows while reconciling total quantity, cost, market value and P/L; sales use the selling account's holdings and documented cost method.
- Include two $500 buys versus one $1,000 buy ($6 versus $3 entry fees), a $1,500 holding trimmed to $500 versus fully closed, and a necessary $600 risk exit. For the across-account example above, a common $130 mark gives 15 shares, $1,950 value, $1,600 acquisition cost and $350 unrealized gain before fees. Do not infer realized P/L from position snapshots alone.
- Moomoo feasibility has official citations and a clear verified/unverified boundary. The design cannot silently overwrite Tiger, count a repeated snapshot twice, spend cash from another account, or treat diluted cost as acquisition average.
- All research questions receive a recommendation or an explicit remaining dependency. The report separates facts, assumptions and owner decisions, and identifies future implementation boundaries and validation scenarios.
- Subtheme removal has a producer-to-display inventory and a concrete follow-up checklist: no hardcoded categories, forms, grouping, prompts or freshly generated subtheme fields remain; older saved data/reports can still be read. Include missing/empty legacy configuration cases to catch fallback resurrection.
- Config cleanup has a per-key keep/remove rationale based on active readers and defaults, distinguishes live config from examples, and includes preservation and rollback checks. Merely deleting JSON properties or treating every legacy-looking key as unused does not satisfy the study.
- Every proposed custom change references the native capability assessment and explains the remaining gap. Do not duplicate existing `--portfolio` plumbing or mistake free-text sizing, a per-ticker portfolio manager, or outcome-evaluation horizon settings for enforced whole-book trading rules.

Delivery acceptance (a report alone cannot satisfy these):

- Fees, entry minimums and exit/remainder behaviour follow the approved T6 specification in both displayed proposals and deterministic validation; trade cash includes fees. Verify immediately below, at and above approved thresholds and necessary exits from small holdings.
- A $600 holding in each of two accounts demonstrates the chosen per-order/per-account/consolidated minimum semantics. Combined exposure must not imply either account can spend the other's cash or sell its shares.
- Account rows and the consolidated view reconcile quantities, acquisition cost, market value and unrealized P/L for the worked examples. Unknown cost leaves cost/P&L unavailable rather than zero; live diluted cost is never silently substituted.
- Tiger refresh preserves Moomoo and vice versa; repeated snapshots do not double count, incomplete snapshots do not overwrite good data, and migration preserves the prior single-account book. Mixed currencies follow the explicitly approved conversion or unsupported-state policy.
- Moomoo read-only adapter and preview/apply workflow have fixture-backed evidence. Record actual live verification if available and disclose it if unavailable; no fabricated account compatibility claim.
- New UI/API output, prompts and reports contain no hardcoded AI subtheme feature or fallback resurrection. Historical reports remain readable. Audited obsolete config keys/tags are removed through backed-up repeatable cleanup with unrelated settings preserved.
- Required focused checks pass, independent reviewer reports a clean round, independent verifier covers each criterion, and final documentation describes the actual shipped behaviour and material limitations.
- Policy adjustments/rejections explain the reason and recompute fees, cash and exposure. Migration repeatability and backup restoration are demonstrated using temporary fixtures; tests never alter the real portfolio.

## Implementation

Required delivery phase of this same plan after the human Plan-to-Implementation gate. The developer implements T11–T15 and focused checks; the host assigns exclusive file ownership and coordinates cross-repository edits. Source changes are expected, with only minimal native changes if reuse requires them. No implementation performed yet.

### Review loop

Not started. Record independent reviewer identity, result, tests, findings and fixes for each round. A clean reviewer result with passed tests and no findings is required before leaving Implementation.

## Review

Pending actual code delivery. Independent review must cover Argus, TradingAgents add-ons, any native integration changes, configuration/data migration and regression coverage. Preserve review evidence and unresolved findings; do not treat a documentation review as code approval.

## Acceptance

Pending independent behavioural verification and final human acceptance of shipped changes. Record criterion-by-criterion tests, fixture-versus-live evidence and remaining limitations. Research-only closure is excluded by owner direction.

## Logs

- 2026-11-14 13:59 UTC — Superseded by 20261114135901-native-first-portfolio-improvements, created with kind normal; all further work belongs to the replacement plan.

- 2026-11-14 12:10 UTC — Corrected scope to end-to-end code delivery at owner request; integrated planner dependencies, added T11–T16 implementation/verification tasks, and required full lifecycle rather than research-only closure.
- 2026-11-14 11:47 UTC — Prioritized native-first assessment, integrated researcher capability matrix and confirmed existing Argus portfolio wiring; T10 complete by static inspection, other study tasks remain open.
- 2026-11-14 10:59 UTC — Added owner-requested AI subtheme removal and usage-based configuration cleanup to research scope as T8/T9; documented cross-repository defaults and preservation criteria.
- 2026-11-14 04:24 UTC — Integrated planner handoff and concrete accumulation, exit and consolidated-account acceptance examples; retained study tasks as open.
- 2026-11-14 04:23 UTC — Created and claimed research plan; integrated preliminary researcher evidence, bounded study tasks and observable acceptance criteria. Full research remains open.
