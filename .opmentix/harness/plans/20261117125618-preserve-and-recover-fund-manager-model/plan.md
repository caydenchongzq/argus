---
id: 20261117125618-preserve-and-recover-fund-manager-model
title: Preserve and recover fund manager model responses
---

Diagrams: a mermaid block for a flow or design, then a table with columns Component and Description.

## Brief

Preserve fund-manager model responses, make incomplete reviews visible, and allow safe local reprocessing without another paid call.

## Discovery

Researcher verified the November 17 run exited successfully despite absent structured draft, risk debate, final plan and trade checks. Its text fallback survives in raw_text_fallbacks but is absent from the Markdown, which incorrectly claims --no-llm. An earlier malformed JSON response was discarded and its returned usage was not recorded because parsing preceded cost accounting. The runner maps nonzero exits to failed. A completed provider response must be persisted before parsing and costed, including if later processing fails. Do not recover missing response content by guesswork or treat raw prose as validated advice. Sources: TradingAgents addons/fund_manager/fund_manager.py, addons/cost_ledger.py, Argus run_analysis.py, server.py, and saved November 17 run/report artifacts. Existing artifacts must remain untouched.

<!-- Host: integrate opmentix-researcher sources, findings, uncertainties, and optional research.md link. Before research-only closure, record the curator handoff. -->

## Plan

- [x] T1: Persist responses and known usage before parsing or retrying.
  - /home/dev/projects/trading/TradingAgents/addons/fund_manager/fund_manager.py: checkpoint every provider response, metadata and parse errors safely; stop further calls if evidence cannot be saved; record returned usage even when parsing fails.
  - /home/dev/projects/trading/TradingAgents/addons/cost_ledger.py: reuse ledger and add identity only if required for idempotence.
- [x] T2: Parse and reprocess responses safely.
  - /home/dev/projects/trading/TradingAgents/addons/fund_manager/fund_manager.py: share bounded, unambiguous parsing and schema checks with recovery; preserve existing deterministic trade validation.
  - /home/dev/projects/trading/TradingAgents/addons/fund_manager/reprocess_response.py: provide offline recovery into a separate traceable artifact without paid calls, modifying originals or promoting prose into trades.
- [x] T3: Preserve incomplete reports and expose correct outcomes.
  - /home/dev/projects/trading/TradingAgents/addons/fund_manager/fund_manager.py: save available work and explicit outcome on failure, label raw output unvalidated, distinguish intentional no-LLM snapshot, and exit nonzero for incomplete paid review.
  - run_analysis.py: propagate incomplete fund review through existing failed status.
  - server.py: expose explicit and inferred legacy outcomes plus raw output, retaining backward compatibility.
  - static/app.js: show incomplete status and sanitized unvalidated draft separately from trade results.
  - static/index.html: add raw output presentation and update script version.
- [x] T4: Verify recovery and regressions offline.
  - /home/dev/projects/trading/TradingAgents/addons/fund_manager/check_offline.py: cover rejected/invalid/text responses, attempt preservation, schema checks, later-stage and storage failures, and usage tracking.
  - check_offline.py: verify legacy November 17-style fallback and successful report compatibility.
  - check_runner_offline.py: verify incomplete run status.
  - check_fund_manager_ui_offline.js: verify raw output is sanitized and never promoted to validated trade rows.

Acceptance: all returned responses and known usage survive parse failures and later stage failures; completed and intentional snapshot behavior remains correct; incomplete review saves evidence and yields failed run; unvalidated output is clearly separated from structured decisions; existing November 17 text fallback is visible without modifying original files; local reprocessing is traceable and cannot perform paid calls or overwrite originals; no unavailable response is invented. Run fixture checks without network, credentials, broker access or paid runs.

<!-- Host: integrate opmentix-planner tasks and checkable acceptance criteria. Use `- [x] T1: Task name` with indented file notes. Keep IDs stable; add review changes with the next unused ID, and mark `[x]` when each task is complete. -->

## Implementation

Initial producer and dashboard work completed with offline fixtures; review findings are being addressed.

### Review loop

- round 1
  - reviewer: opmentix-reviewer
  - result: findings
  - tests: passed
  - findings: Sanitize before DOM insertion; save reports on validation errors; support Windows locking; retain prior risk views; reconcile journaled cost after crashes; distinguish paid failures from snapshots; avoid raw data in history; hash actual recovery source; reject nested JSON fragments. Fixes in progress.

<!-- Host: integrate opmentix-developer changes/tests and each independent opmentix-reviewer round under ### Review loop. Preserve unresolved findings and blockers. -->

- round 2
  - reviewer: opmentix-reviewer
  - result: findings
  - tests: passed
  - findings: Reconcile orphaned journal costs before budget checks with original timestamps; reject non-finite numbers; associate validation failures with exact attempt; expose schema-valid but unvalidated response on ledger failure. Fixes in progress.

- round 3
  - reviewer: opmentix-reviewer
  - result: findings
  - tests: passed
  - findings: Fail closed on corrupted journals; reconcile all budget previews; support journal-only recovery; reject exponent-overflow nonfinite values. Fixes in progress.

- round 4
  - reviewer: opmentix-reviewer
  - result: findings
  - tests: passed
  - findings: Existing corrupted attempt ledger file could be trusted by filename and conceal known cost. Fix in progress.

- round 5
  - reviewer: opmentix-reviewer
  - result: findings
  - tests: passed
  - findings: Pricing changes break ledger replay; dashboard can miss actual spend reconciliation error. Fixes in progress.

- round 6
  - reviewer: opmentix-reviewer
  - result: clean
  - tests: passed
  - findings: none

## Review

Independent opmentix-reviewer reviewed all changes, tracked findings through five rounds, and confirmed a clean subsequent review after fixes. Mocked provider, recovery, ledger and UI checks passed; live provider behavior remains unverified.

<!-- Host: integrate independent reviewer evidence, then advance to Acceptance. -->

## Acceptance

Independent opmentix-verifier passed criteria with mocked responses and isolated fixtures: response preservation and usage, failed incomplete versus successful snapshot, validation boundaries, crash recovery and idempotent cost reconciliation, legacy fallback, local reprocessing and strict parsing/UI safety. Checks: Argus check_offline.py, check_runner_offline.py, check_runner_budget_offline.py, check_fund_manager_ui_offline.js; TradingAgents check_response_recovery.py, fund_manager/check_offline.py, check_trade_validation.py, check_cost_ledger.py. Existing November 17 report inspected read-only: incomplete, one unvalidated response, zero validated trades. No paid calls, broker calls or original report writes. Live provider behavior remains unverified. After the active-run check Argus service restarted; live API returned incomplete with one unvalidated output for the November 17 report.

Curator updated .opmentix/harness/knowledge/project-guide.md with recovery, cost reconciliation and command guidance; no additional entry needed.

<!-- Host: integrate opmentix-verifier results for each criterion from a session independent of the developer. Before closure, record opmentix-curator updates or a reason no durable update is needed. -->

## Logs

- 2026-11-17 15:00 UTC — Recorded independent acceptance, curation and live read-only dashboard verification.

- 2026-11-17 14:57 UTC — Recorded independent review evidence.

- 2026-11-17 14:56 UTC — Recorded clean independent review and passing focused checks.

- 2026-11-17 14:49 UTC — Recorded fifth independent review findings.

- 2026-11-17 14:44 UTC — Recorded fourth independent review finding.

- 2026-11-17 14:36 UTC — Recorded third independent review findings.

- 2026-11-17 14:24 UTC — Recorded second independent review findings.

- 2026-11-17 14:09 UTC — Recorded first independent review and fixes.

- 2026-11-17 12:58 UTC — Recorded research, proposed tasks and acceptance criteria.
