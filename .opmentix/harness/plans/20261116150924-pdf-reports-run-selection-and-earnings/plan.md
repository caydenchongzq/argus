---
id: 20261116150924-pdf-reports-run-selection-and-earnings
title: PDF reports, run selection and earnings-aware watchlist
---

Diagrams: a mermaid block for a flow or design, then a table with columns Component and Description.

## Brief

Add PDF exports for fund manager and theme scout, combined book/watchlist selection in Runs, and earnings visibility and report freshness cues in the watchlist.

## Discovery

Researcher: Runs combines book and saved candidate tickers, with separate exclusive book and watchlist selectors. Watchlist merges book and candidates but has no earnings fields. Theme scout provides upcoming day offsets; fund manager reduces earnings timestamps to dates. Neither supports reliable same-day report freshness comparison. Reports expose generated metadata and file modification time. The report producer writes naive local generated times, so their timezone must not be assumed. Fund manager supports historical selection; theme scout displays its latest report. Both render sanitized Markdown. Sources: server.py, static/app.js, static/index.html, and sibling TradingAgents addons/theme_scout/theme_scout.py, addons/fund_manager/fund_manager.py and tradingagents/reporting.py. Earnings data must retain event time and timezone and show unknown where unavailable. Browser print-to-PDF can reuse rendered report content without a new dependency.

<!-- Host: integrate opmentix-researcher sources, findings, uncertainties, and optional research.md link. Before research-only closure, record the curator handoff. -->

## Plan

- [x] T1: Preserve earnings event timestamps and report generation timestamps, including unknown legacy times.
  - /home/dev/projects/trading/TradingAgents/addons/fund_manager/fund_manager.py: retain compatible earnings fields and last and next events.
  - /home/dev/projects/trading/TradingAgents/tradingagents/reporting.py: emit timezone-aware generation times.
  - /home/dev/projects/trading/TradingAgents/addons/fund_manager/check_offline.py: cover timestamp behavior with fixtures.
- [x] T2: Enrich watchlist with earnings and ticker-report freshness.
  - server.py: join available data and compare only reliable timestamps.
  - check_offline.py: exercise missing and stale data without fabricated precision.
- [x] T3: Show earnings and prepare refresh runs.
  - static/index.html: add earnings columns and selection controls.
  - static/app.js: display earnings, flag stale reports, and hand selection to a confirmed analysis plus review.
  - static/styles.css: style warnings accessibly.
- [x] T4: Select all book and watchlist in Runs.
  - static/index.html: add select all control.
  - static/app.js: select the deduplicated union.
  - check_run_scenarios_offline.js: verify selection and manifest scope.
- [x] T5: Export fund manager and theme scout reports.
  - static/index.html: add report export controls.
  - static/app.js: print the displayed report, including selected fund-manager history.
  - static/styles.css: format report-only output for saving as PDF.

Acceptance: both reports print complete, readable current content; selection covers the deduplicated union; watchlist shows available earnings and unknown states; upcoming events within five days and reports predating completed events are labeled; selected stocks transfer to a confirmed analysis-plus-review run; existing sanitization and side-effect guards remain intact. Use fixture checks and browser print inspection where available. Historical timestamps of uncertain timezone remain uncertain. Keep an overdue report flagged until refreshed. Earnings data should include available EPS values, without inventing missing data.

<!-- Host: integrate opmentix-planner tasks and checkable acceptance criteria. Use `- [x] T1: Task name` with indented file notes. Keep IDs stable; add review changes with the next unused ID, and mark `[x]` when each task is complete. -->

## Implementation

Initial backend and UI implementation completed; focused Argus and sibling offline checks passed. Independent review identified issues being fixed before another review.

### Review loop

- round 1
  - reviewer: opmentix-reviewer
  - result: findings
  - tests: passed
  - findings: Watchlist handoff skipped fund-manager review; missing earnings could appear updated; date-only earnings were hidden; EPS values from different events were mixed; print tables could overflow; earnings snapshot age was not visible. Developers are correcting all findings.

<!-- Host: integrate opmentix-developer changes/tests and each independent opmentix-reviewer round under ### Review loop. Preserve unresolved findings and blockers. -->

- round 2
  - reviewer: opmentix-reviewer
  - result: findings
  - tests: passed
  - findings: Last-event missing estimate could fall back to next-event estimate; rollover discarded available actual EPS from a same-day event. Fixes in progress. Earlier findings addressed.

- round 3
  - reviewer: opmentix-reviewer
  - result: findings
  - tests: passed
  - findings: Live event classification incorrectly depended on analysis date; passed date-only event was dropped and an older event could be reported updated. Fixes in progress.

- round 4
  - reviewer: opmentix-reviewer
  - result: findings
  - tests: passed
  - findings: Date-only live calendar events still grouped by analysis date, potentially hiding the next event. Fix in progress.

- round 5
  - reviewer: opmentix-reviewer
  - result: clean
  - tests: passed
  - findings: none

## Review

Independent opmentix-reviewer reviewed the complete change across five rounds; all reported findings were fixed and the final review was clean. Browser print preview could not be inspected because no browser binary is available.

<!-- Host: integrate independent reviewer evidence, then advance to Acceptance. -->

## Acceptance

Independent opmentix-verifier: report export targets and selected history, sanitized rendering, select-all deduplication, watchlist freshness and uncertainty, EPS pairing, exact selected handoff with confirmation, and sibling timestamp fixtures passed. Commands: node check_watchlist_export_ui_offline.js; node check_run_scenarios_offline.js; .venv/bin/python check_offline.py; TradingAgents .venv/bin/python addons/fund_manager/check_offline.py; Python compilation. Five-day rendering logic was inspected but its boundary was not separately exercised. Actual PDF print layout remains unverified because no browser is available. Earnings depend on the latest fund-manager snapshot and source availability.

Curator updated .opmentix/harness/knowledge/project-guide.md with earnings snapshot and precision constraints, PDF export workflow, and UI check command; no separate entry needed.

<!-- Host: integrate opmentix-verifier results for each criterion from a session independent of the developer. Before closure, record opmentix-curator updates or a reason no durable update is needed. -->

## Logs

- 2026-11-16 15:50 UTC — Recorded independent acceptance evidence and curation.

- 2026-11-16 15:48 UTC — Recorded public review evidence.

- 2026-11-16 15:47 UTC — Recorded clean fifth independent review.

- 2026-11-16 15:45 UTC — Recorded fourth review finding.

- 2026-11-16 15:41 UTC — Recorded third review findings.

- 2026-11-16 15:38 UTC — Recorded second review findings.

- 2026-11-16 15:24 UTC — Recorded first independent review and fixes in progress.

- 2026-11-16 15:11 UTC — Added planner recommendations and acceptance criteria.
- 2026-11-16 15:10 UTC — Recorded discovery and existing data limitations.
