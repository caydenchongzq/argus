# Runs interface: behavior and selector study

## Question

How should the six existing scenarios populate one understandable New run draft, without immediately opening confirmation, changing tabs or submitting anything? Which selectors remain useful after research-only stock profiles, and how can their scope and cost be understood?

## Findings

- Current scenario handlers (`static/app.js:1356–1405`) configure then programmatically click Start, or jump to Themes and click screen/scout. This causes the unexpected popup/navigation. Selection should only change local draft state and visible settings; Start alone requests a manifest, and explicit confirmation/consent alone submits the actual job.
- Existing New run controls expose implementation flags: run_agents, analysis_only, no_llm, include_watchlist, include_risk, no_macro, analysis_date and since. A single purpose/mode should derive mutually consistent request fields. No new backend profile or TradingAgents change is required for this UI task.
- The six underlying flows already exist. Four use `/api/runs/manifest` and `/api/runs`; screen/scout use `/api/theme-scout/manifest` and `/api/theme-scout`. Preserve both API families and their binding/hash/consent/concurrency checks. Reuse preparation/confirmation helpers; never synthesize clicks on hidden controls as the dispatch mechanism.
- Stock ticker selections only limit paid stock refreshes. Fund-manager review still sees the entire holdings and watchlist universe. Empty enabled-source scope currently expands to all eligible names; the redesign must require explicit research selection or an explicitly chosen all-scope, never silently promote an empty selection into a paid bulk run.
- `run_agents` selects held-name research, `include_watchlist` selects non-held research; it is not the switch for including candidates in a fund review. User-facing stock selection should express names, not those backend flags. Preserve valid selected names across scenario changes; hidden stale selections must never enter unrelated mode payloads.
- Screen/scout use one-to-eight existing discovery sectors: XLK, XLY, XLV, XLP, XLU, XLE, XLF, SMH. Their API request does not support stock date/since/risk/macro options; only show relevant sector controls. A scout proposal is reviewed/applied separately, never an automatic watchlist edit.
- Analysis date is optional/automatic when blank. `since` restricts saved holding report eligibility, not refreshed stock dates or candidate-report eligibility; it belongs in Advanced with a truthful holding-only explanation, if retained. `no_macro` excludes the FRED macro snapshot from fund review; default is to include it, so use a positive label if exposing it.
- **Current include_risk correction:** after the implemented research-only handoff, `parse_report()` returns new brief output before that optional branch; legacy output collects risk_debate, but current `build_context()` never forwards it. It is therefore ineffective for fund-manager input, not an extra risk-agent stage. Remove that UI control rather than promising additional notes or restoring portfolio-aware legacy risk narratives. Risk evidence is in the normal brief and whole-fund committee.
- Current warning copy hardcodes model names, fees and runtimes. Replace it with scope/purpose/AI-use guidance and request-specific manifest estimates. Fund review currently uses draft +3 risk seats+final, but labels should not make static model or provider-cost promises. Estimates are not provider spending caps.
- The final paid review must retain visible fresh names versus whole review scope, stages, costs/uncertainty and explicit consent. Scenario selection itself must fetch no manifest and open no dialog. Invalid selections need inline recovery; async Start needs loading/duplicate protection and draft changes must invalidate an in-flight or cached preview.

## Sources

- `static/index.html:324–392`: scenario table, flags and scope/date inputs.
- `static/app.js:1063–1202`: run loading, candidate list, selections and warning copy; `1274–1405`: manifest preparation/scenario dispatch; `1455–1518`: actual confirmation; `1550–1592`: scout manifest preparation.
- `server.py` `RunRequest`, `ScoutRequest`, `_build_run_manifest`, `_build_scout_manifest`, `/api/runs`, `/api/theme-scout`: authoritative existing semantics, estimates and confirmations.
- `run_analysis.py`: selected ticker refresh versus complete fund context and existing research-only flags.
- TradingAgents `addons/fund_manager/fund_manager.py:180–258`, current `build_context()`, main report discovery and macro/risk CLI args: risk-control no-op, safe research handoff and holding-only since cutoff.
- Existing `check_run_scenarios_offline.js`: executes real extracted handlers; must change from immediate-preview assumptions to draft-only assertions, then prove actual Start/Confirm mappings for all modes.
- UI/UX Pro Max local skill and quick-reference §§1/2/5/8: semantic labels, helper text, grouping, progressive disclosure, inline errors, submission feedback, keyboard/reduced-motion/responsive rules. Database matches verified for form labels and submit feedback. No relevant exact prefill/progressive match after retry; direct reference and user instruction own that decision. No unverified design-system output persisted.

## Conclusion

Use a purpose-first draft composer: choose preset → review mode-specific settings and scope → bottom Start run → existing authoritative manifest/paid-consent review → actual execution. Provide clear refresh/reuse/output descriptions, retain useful advanced settings, remove ineffective controls and preserve established visual tokens and backend execution behavior. Planner is preparing exact labels, state rules, preview and tasks. No production changes, model calls, data writes or checks executed for this planning discovery.

## Logs

- 2026-11-19 00:33 UTC — Recorded source-backed scenario semantics and current risk-control no-op; supplied planner with scope, cost and confirmation invariants.
