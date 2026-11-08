---
id: 20261108064826-docker-deployment-portfolio-import-scheduled-analysis-and-mobile-delivery
title: Docker deployment, portfolio import, scheduled analysis and mobile delivery
---

## Brief

Use the current development environment and existing Argus and TradingAgents checkouts for development and operation. Plan Linux-native dashboard-triggered analysis, Tiger Brokers Singapore portfolio import, and browser access from the user's Windows PC. Scheduling, Docker, a separate deployment, PostgreSQL, phone access and notifications are deferred. Assess existing flow readiness and preserve control over paid calls and sensitive holdings. No paid analysis during discovery.

## Discovery

Researcher: opmentix-researcher; repository inspection only, no live analysis or credentials inspected.

- Argus is a single-user local dashboard. `server.py` resolves TradingAgents via `TRADINGAGENTS_ROOT`, reads its `data` directory, and starts portfolio runs via `addons/fund_manager/run_portfolio.ps1` using PowerShell; theme scouting also invokes PowerShell. Host filtering and a per-process confirmation token protect a loopback-oriented service. Run metadata and logs are local; background subprocess launching has no durable scheduling or mutual exclusion. See `server.py` and `README.md`.
- TradingAgents has a `Dockerfile` and `docker-compose.yml`. Its portfolio wrapper `addons/fund_manager/run_portfolio.ps1` orchestrates preflight, optional ticker analyses, and fund-manager analysis with cost-ledger checks; `addons/fund_manager/run_native.py` provides a Python path for part of the flow. The end-to-end orchestration is Windows/PowerShell dependent. Its availability is evidence of a workflow, not proof of successful Linux execution or investment decision quality. Verify the complete flow and outputs with a controlled test before calling it deployment-ready.
- The projects share files, not an independent network API. A preliminary direction is one deployment containing both codebases, with a reproducible image incorporating the necessary TradingAgents runtime and Argus, persistent data and run volumes, and a host cron or systemd timer invoking a dedicated Linux entry point. Avoid Docker-in-Docker and exposing the Docker socket. Validate dependency compatibility and whether a separate worker service is justified; separate images are not required simply because there are two repositories.
- The portfolio book uses `data/my_book.json`; no Tiger integration was found. Tiger's [official quickstart](https://docs-en.itigerup.com/docs/quickstart) describes position queries and authentication, while its [Singapore statement guide](https://sgp.itiger.com/sg/help/detail/statement) describes statements with open positions. Confirm actual Singapore account eligibility, permissions and export format before choosing API versus file import. The SDK can also trade; do not assume position access is permission-separated. Import must preview changes, handle currencies, fractional quantities and unsupported instruments, and avoid silently overwriting manual data or accepting incomplete snapshots.
- [Telegram Bot API](https://core.telegram.org/bots/api) can send messages to a chosen chat; the user must initiate the bot conversation. Its official bot API does not support [secret chats](https://core.telegram.org/api/bots/ids), so send minimal status and a secure link rather than sensitive holdings by default. [ntfy](https://docs.ntfy.sh/) is a push alternative with authentication and self-hosting, but adds a service or third-party dependency. Email is another option. Compare privacy, reliability, setup and phone experience before choosing.
- Default security direction: keep Argus off the public Internet, with phone access through a private VPN or similarly authenticated encrypted access. Current Host validation and local-origin assumptions must be examined and deliberately adapted; Docker port binding alone is not authentication. Keep credentials out of images and logs; use restricted runtime secrets. [Docker Compose production guidance](https://docs.docker.com/compose/how-tos/production/) and [secrets guidance](https://docs.docker.com/compose/how-tos/use-secrets/) describe relevant mechanisms.
- Scheduler design must cover timezone/market calendar, opt-in paid spending limits, duplicate/overlap prevention shared with manual runs, restart recovery, failure notification, and a test mode without provider charges. Persist reports and run state; document backup, restore and upgrades. Existing code does not establish these properties.

- Updated scope: Linux runs as a VirtualBox guest on the user's Windows PC. Prefer NAT port forwarding bound to Windows loopback, subject to validating Docker-to-guest connectivity and Argus Host/origin checks; access from a Windows browser using localhost. Do not assume guest loopback is reachable from VirtualBox NAT or publish the app on the LAN. Host shutdown, sleep, or guest shutdown prevents scheduled work; define missed-run behavior and startup instructions. Phone access and notification integrations are deferred; surface run/failure status in the dashboard and logs.
- Persistence recommendation: keep the existing shared file-based data contract (`data/my_book.json`, watchlist, reports, cache and run metadata) in persistent storage mounted by the relevant processes, with consistent file permissions, backup/restore, atomic updates and cross-process locking as required. `server.py` and TradingAgents fund-manager code read these files directly. PostgreSQL in Compose would be possible but would require an explicit migration of both consumers and a recovery plan; adding an unused database does not make existing files durable. Revisit if transactional shared writes, query needs or concurrency justify migration.
- Tiger authentication: [Tiger's authentication documentation](https://docs-en.itigerup.com/docs/authentication) describes OAuth2 for individuals with account/permission selection and separately authorized trade operations; authorization lasts up to 15 days. Prefer testing selected account and query-only permissions if available; verify positions access and renewal behavior with the user's account. Signature credentials inherit enabled Tiger ID permissions and cannot be scoped per application. Never request the user to send keys or tokens in chat.

Latest user direction supersedes earlier packaging assumptions: develop and run in this existing environment and use `/home/dev/projects/trading/TradingAgents` directly. Prefer native Linux process invocation, an appropriate local scheduler and the current file-based data contract; no Docker, inter-container worker or PostgreSQL is needed for the initial scope. Establish browser connectivity from Windows for the actual environment rather than assuming a new VM or network topology. Confirm Linux workflow, process supervision, safe scheduled/manual concurrency, backup location outside this environment, and safeguards for real data while developing. The host and environment must be running for scheduled work.

The user wants Argus accessible like the harness dashboard on `192.168.1.115`, using the bridged LAN interface, on a separate available port. Verify the actual interface and address, browser access and firewall exposure. Argus currently restricts hosts and is designed for loopback; design explicit LAN access controls and protect sensitive reads and state-changing or paid endpoints, including origin/CSRF checks, instead of simply disabling existing protections. Account for address changes and communicate the trust implications of LAN exposure.

Latest scope revision: analysis is triggered manually from the Argus dashboard only. Earlier scheduler, cron, timer, catch-up and scheduled-run requirements are deferred; preserve safeguards against overlapping manual runs and conflicting portfolio writes.

Open decisions: schedules, markets, symbols and spend limits; actual Tiger Singapore account/API permissions or representative redacted export; treatment of unsupported securities and manually maintained positions. Credentials or an export are not required merely to start design.

## Plan

Planner: opmentix-planner. Use the current environment and existing TradingAgents checkout; no Docker or database. Retain existing Windows behavior where practical.

- Establish native execution and shared run safety
  - run_analysis.py: invoke TradingAgents preflight, native agent, fund manager and theme scout with explicit data, cache and result paths and headless settings; reuse existing cost checks.
  - server.py: use the common runner for dashboard jobs, maintain paid confirmation and coordinate overlapping manual jobs and conflicting portfolio writes with cross-process locking and atomic run metadata.
  - check_offline.py: verify stage order, report paths, exclusion, failure handling and recovery using temporary fixtures and stubbed calls. No-LLM must mean zero paid calls for every option combination; preflight or budget failure prevents all later paid stages.

- Provide deliberate LAN access and native operations
  - server.py: retain Host and same-origin validation and protect sensitive reads and all mutations, including watchlist endpoints. Choose a suitable authentication and transport policy before exposing the bridged interface; reusable passwords over plain HTTP are insufficient.
  - start.sh: provide a Linux startup path binding the verified address and port with one worker and no reload.
  - README.md: document startup, access, trust boundaries and operation. Test authorized browser access at 192.168.1.115 and reject unauthorized requests and foreign hosts and origins; Windows browser access may require user assistance.

- Add safe Tiger portfolio import
  - tiger_import.py: implement one agreed authentication method and read-only account snapshot retrieval; protect credentials outside the repository and do not expose order placement.
  - server.py: provide preview and explicit apply, validating snapshot completeness, source time, currency, quantities and instrument types. Reject unsupported or mixed-currency holdings because the existing book has one currency and no FX conversion. Apply under the shared lock with version check, backup and atomic replacement; never silently clear on an empty or partial response.
  - static/app.js: present a minimal review of supported and rejected positions before application.
  - check_offline.py: exercise fractional positions, duplicates, unsupported instruments, mixed currencies, missing data, failed responses, stale previews and restoration. Confirm actual account schema using a user-assisted read-only live test before any real application.

- Document and verify operation and recovery
  - README.md: document data and secrets paths, spend limitations, manual operation, upgrade and backups outside the VM. Explain that the existing cost ledger is an estimate, not a provider-enforced hard limit.
  - .gitignore: exclude any newly introduced local secrets and runtime artifacts.
  - check_offline.py: use isolated temporary roots, verify process restarts preserve report/history access, and rehearse restoring a backup without changing real data.

Decisions before enabling affected operations: LAN authentication/transport; Tiger authorization and account scope; import merge/replace policy; backup destination. Paid runs require explicit confirmation. Scheduling, phone access, notifications and trading orders remain out of scope.

## Implementation

User selected trusted LAN without login, Tiger OAuth query-only, and replacement after preview. No scheduler is included. Native runner, LAN launcher and Tiger preview/apply are in progress. No live broker or paid calls made.

The developer fixed overlapping watchlist/holding selection; the reviewer confirmed it and ran isolated Tiger, runner, budget and UI checks. With user-installed dependencies, the developer also passed `.venv/bin/python check_offline.py`, runner, budget and Tiger fixtures, JavaScript checks and `git diff --check`. Live Tiger, paid analysis and Windows browser access remain unverified.

### Review loop

- round 1
  - reviewer: opmentix-reviewer
  - result: findings
  - tests: not-run
  - findings: incorrect report path; credentials missing from subprocess environment; watchlist preflight gap; Tiger import absent; stale running status after restart; buffered logs; scout incorrectly dependent on portfolio preflight. Developer reported fixes and fixture checks; independent reassessment pending.
- round 2
  - reviewer: opmentix-reviewer
  - result: findings
  - tests: not-run
  - findings: runner entry point failed; multi-currency or missing Tiger cash could be erased; Tiger market identity discarded; concurrent run metadata writes race; account changes leave wrong preview active; Tiger setup uses wrong Python environment; no-paid test checks wrong marker. Developer fixing; live Tiger and full dashboard tests remain unverified.
- round 3
  - reviewer: opmentix-reviewer
  - result: findings
  - tests: passed
  - findings: stale in-flight preview can apply the wrong account; short positions unsupported by downstream calculation; selected tickers improperly restrict fund-manager preflight. Developer fixing.
- round 4
  - reviewer: opmentix-reviewer
  - result: findings
  - tests: passed
  - findings: global Tiger cash may conceal mixed currencies; OAuth loopback callback targets wrong host; historical analysis checks wrong spending week; watchlist-only run behavior regressed. Developer fixing.
- round 5
  - reviewer: opmentix-reviewer
  - result: findings
  - tests: passed
  - findings: Prime account with missing per-currency data falls back to aggregate cash and could conceal mixed currencies; developer fixing. Full FastAPI integration tests remain unavailable in system Python.
- round 6
  - reviewer: opmentix-reviewer
  - result: blocked
  - tests: passed
  - findings: watchlist-only runs without ticker filters can also run paid analysis for holdings duplicated on the watchlist; deduplicate candidates before paid execution. The independent review loop has exceeded five rounds with unresolved findings.
  - blocker: review has not converged within the harness review-loop bound; do not use paid runs or request advancement until the finding is fixed and a later independent review is clean. Full FastAPI integration and live Tiger tests remain unverified.
- round 7
  - reviewer: opmentix-reviewer
  - result: clean
  - tests: passed
  - findings: none



## Review

Formal independent review (opmentix-reviewer) initially found missing TradingAgents runtime dependencies and Tiger Prime segment cash omission. The developer added a reproducible runtime setup and a real no-paid preflight check, and made Prime cash validation fail closed for non-securities segments without complete per-currency data. A re-review identified a zero-aggregate edge case, which was fixed and tested. Final independent review: no remaining actionable findings. Offline dashboard, runner, budget, Tiger and UI tests passed. Live Tiger, paid analysis and Windows browser access remain unverified.

Subsequent manual tests: user accessed dashboard from Windows, authorized Tiger and applied the reviewed stock-only import; a snapshot run succeeded after fixing the BRK.B to BRK-B import mapping. User accepted stock-only Tiger scope and deferred paid analysis to a later plan. An isolated backup/restore rehearsal archived TradingAgents data and Argus runs while no run was active, restored to a temporary directory, matched SHA-256 hashes for 21 files, and parsed the restored portfolio and latest snapshot. Temporary archive removed; no durable off-VM backup exists yet. Target allocation configuration needs separate user-led planning.

Independent verifier pre-acceptance checks: `.venv/bin/python check_offline.py`, `check_runner_offline.py`, `check_runner_budget_offline.py`, `check_tiger_offline.py`, `node check_tiger_ui_offline.js`, `git diff --check`, and `./check_tradingagents_runtime.sh` passed. The runtime check used actual TradingAgents imports and an isolated no-paid preflight. User observed successful live Tiger stock-only import and browser access; verifier did not independently access the account. Paid analysis is explicitly deferred; durable off-VM backup remains outstanding. Curator updated the project guide to reflect the current Linux and Tiger workflows.


## Acceptance

Independent verifier: opmentix-verifier. Evidence audit completed after entry into Acceptance; prior offline checks and user-reported manual tests were reviewed without re-accessing the user's account.

- Native Linux manual execution: passed offline runner, budget and dashboard checks and real TradingAgents isolated session-only preflight; user completed a free dashboard snapshot after the BRK-B mapping fix. Paid analysis is intentionally deferred to a later plan, not tested.
- LAN access: user accessed the dashboard from Windows at 192.168.1.115:8787. Trusted LAN without login is the user's explicit choice; host and origin checks remain.
- Tiger import: user authorized OAuth and applied a reviewed stock-only snapshot. Failed non-stock category queries are disclosed; unsupported/mixed-currency stocks and incomplete stock data block replacement. Singapore stock mapping remains unsupported and the user accepted the present stock-only scope. Verifier did not independently access the live account.
- Persistence and recovery: temporary archive and restore passed SHA-256 comparison of 21 files, and restored portfolio and latest snapshot were readable. Partial: no durable off-VM backup destination or scheduled backup exists; record as follow-up rather than claiming it is configured.
- Documentation and curation: project guide and README document current runtime, operation and Tiger setup. opmentix-curator confirmed no further durable update is required. Allocation target redesign is separate future work.


## Logs

- 2026-11-08 16:25 UTC — Recorded independent acceptance evidence, partial backup status and agreed deferred work; curator confirmed guide current.
- 2026-11-08 06:50 — Created discovery with repository research, source-backed options, preliminary architecture and unresolved decisions.
- 2026-11-08 07:28 — Recorded Windows/VirtualBox deployment, deferred phone access, file persistence rationale and Tiger OAuth permissions research.
- 2026-11-08 07:45 — Changed initial scope to development and operation in the existing environment with native Linux invocation; deferred containers and database.
- 2026-11-08 07:47 — Recorded bridged LAN access at 192.168.1.115 and the need for explicit access protections.
- 2026-11-08 08:00 — Added planner's file-level implementation sequence, acceptance tests, no-cost guarantee and Tiger currency constraints.
- 2026-11-08 08:39 — Deferred scheduling and restricted analysis triggers to the dashboard; retained manual concurrency safeguards.
- 2026-11-08 09:00 — Recorded implementation choices and independent review findings for correction.
- 2026-11-08 09:30 — Recorded blocked review loop after a sixth round identified unexpected paid watchlist analysis.
- 2026-11-08 10:40 — Corrected watchlist overlap, passed full offline checks with installed FastAPI, and recorded a clean independent follow-up.
- 2026-11-08 12:00 — Formal review identified missing TradingAgents runtime setup and unaccounted Prime segment cash; fixes in progress.
- 2026-11-08 12:10 — Installed TradingAgents dependencies, verified actual no-paid preflight, corrected Prime segment validation and recorded clean formal re-review.
- 2026-11-08 15:55 — Recorded user-accepted Tiger scope, deferred paid testing and successful isolated 21-file backup/restore rehearsal; durable external backup remains open.
- 2026-11-08 16:02 — Recorded independent offline verification and project guide curation ahead of the acceptance gate.
