// Exercise the same pure renderer used by the Fund Manager table, without a DOM
// or broker/model access.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
require("./static/formatters.js");
require("./static/fund-trade-render.js");

const render = globalThis.argusRenderFundTrades;
assert.equal(typeof render, "function");
const format = {
  esc: (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]),
  qty: globalThis.argusFormatters.quantity,
  price: (value) => value == null ? "—" : `$${Number(value).toFixed(2)}`,
  moneyLevel: globalThis.argusFormatters.moneyLevel,
  actionClass: (value) => String(value || "").toLowerCase().includes("sell") ? "ar-loss" : "ar-gain",
  ratingMarkup: (value) => value ? `<span>${String(value)}</span>` : "—",
};

const rows = render([
  { status: "accepted", account_label: "Tiger · One", ticker: "AAA", action: "buy", requested_shares: 10, effective_shares: 10, calc_price: 100, fee_usd: 3, cash_delta_usd: -1003, reason: "Within policy", rationale: "Accepted" },
  { status: "adjusted", account_label: "Moomoo SG", ticker: "BBB", action: "sell", requested_shares: 10, effective_shares: 15, calc_price: 100, fee_usd: 3, cash_delta_usd: 1497, reason: "Full exit to avoid small residual", availability_caveat: "All available shares", rationale: "Adjusted" },
  { status: "rejected", account_label: "Moomoo SG", ticker: "CCC", action: "buy", requested_shares: 4, effective_shares: 0, calc_price: 250, fee_usd: 0, cash_delta_usd: 0, reason: "USD cash unknown", rationale: "Rejected" },
], format);
assert.match(rows, /accepted/);
assert.match(rows, /adjusted/);
assert.match(rows, /rejected/);
assert.match(rows, /Tiger · One/);
assert.match(rows, /10<\/td>/);
assert.match(rows, /15<\/td>/);
assert.match(rows, /\$3\.00/);
assert.match(rows, /−\$1,003\.00/);
assert.match(rows, /USD cash unknown/);
assert.match(rows, /All available shares/);

const allRejected = render([
  { status: "rejected", ticker: "BAD", action: "buy", requested_shares: 1, effective_shares: 0, fee_usd: 0, cash_delta_usd: 0, reason: "<script>alert(1)</script>" },
], format);
assert.match(allRejected, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
assert.doesNotMatch(allRejected, /<script>/);
assert.match(render([], format), /No trades in this run/);
const fractionalExits = render([
  { status: "adjusted", ticker: "F1", action: "sell", requested_shares: 0.00001, effective_shares: 0.00005 },
], format);
assert.match(fractionalExits, /0\.00001<\/td>/);
assert.match(fractionalExits, /0\.00005<\/td>/);

// Reports created before validation have only the original fields. Null fields
// remain unavailable instead of becoming zero, and their text is escaped.
const legacy = render([{ ticker: "OLD", action: "hold", shares: 2, rationale: "<legacy>" }], format);
assert.match(legacy, /<td>—<\/td>/);
assert.match(legacy, /<td class="ar-num">2<\/td>/);
assert.match(legacy, /&lt;legacy&gt;/);
assert.match(legacy, /<td class="ar-num">—<\/td>/);

const contract = render([
  { status: "deferred", account_id: "A1", ticker: "AAA", action: "buy", requested_shares: 8,
    target_shares: 20, effective_shares: 0, execution_intent: "deferred", review_horizon: "6 months",
    condition: "Close above $100", change_reason: "Wait for evidence", sizing_rationale: "Build toward target" },
], format);
assert.match(contract, /deferred/);
assert.match(contract, /20<\/td>/);
assert.match(contract, /6 months/);
assert.match(contract, /Close above \$100/);
assert.match(contract, /Build toward target/);

const app = fs.readFileSync("static/app.js", "utf8");
const policySummary = globalThis.argusRenderTradePolicy({
  fee_per_order_usd: 5, min_buy_notional_usd: 2000, min_residual_notional_usd: 1500,
}, format);
assert.match(policySummary, /\$5\.00 per order/);
assert.match(policySummary, /minimum buy \$2,000\.00/);
assert.match(policySummary, /residual guideline \$1,500\.00/);
assert.equal(globalThis.argusRenderTradePolicy(null, format), "");
assert.match(app, /argusRenderTradePolicy\(data\.trade_policy/);
assert.match(app, /data\.validated_trades \|\| data\.trades \|\| \[\]/);
assert.match(app, /argusRenderFundTrades\(trades/);
assert.match(app, /review_outcome === "incomplete"/);
assert.match(app, /fmUnvalidatedCard/);
const rawStart = app.indexOf("function renderUnvalidatedOutputs(");
const rawEnd = app.indexOf("async function exportReportPdf", rawStart);
assert.ok(rawStart >= 0 && rawEnd > rawStart, "unvalidated output should use a dedicated safe renderer");
const rawFixture = { sanitizedBeforeReturn: false };
vm.runInNewContext(`${app.slice(rawStart, rawEnd)}\nglobalThis.result = renderUnvalidatedOutputs([{ label: "model", mode: "text", content: "raw" }], { esc: String, marked: { parse: () => "<img src=x onerror=alert(1)><script>alert(2)</script><p>safe</p>" }, DOMPurify: { sanitize(html) { globalThis.sanitizedBeforeReturn = true; return html.replace(/<script>[\\s\\S]*?<\\/script>/gi, "").replace(/ onerror=[^ >]*/gi, ""); } } });`, rawFixture);
assert.equal(rawFixture.sanitizedBeforeReturn, true);
assert.doesNotMatch(rawFixture.result, /<script|onerror=/i, "raw model HTML must be sanitized before insertion");
assert.match(rawFixture.result, /<p>safe<\/p>/);
assert.match(app, /renderUnvalidatedOutputs\(rawOutputs, \{ esc, marked, DOMPurify \}\)/);
assert.match(app, /unvalidated_outputs/);
assert.match(app, /raw model output|raw model output/i);
assert.match(app, /argusRenderFundContext\(/);
const fundContext = globalThis.argusRenderFundContext({
  baseline_status: "matched", prior_run_id: "2026-11-14/run-1", prior_report_date: "2026-11-14",
  prior_decision_summary: "<earlier rationale>", prior_cash_decision: { target_cash_pct: 10 },
  prior_objections: ["wait for earnings"], prior_changes_vs_draft: ["reduced first tranche"],
  comparisons: [{ account_id: "A1", ticker: "AAA", observed_shares: 5, prior_observed_shares: 4,
    quantity_change: 1, prior_proposed_shares: 2, prior_intent: "current", execution_attribution: "unknown",
    current_research_status: "fresh" }],
}, [{ ticker: "BBB", disposition: "reviewed", research_status: "legacy", source_profile: "unknown",
  evidence_date: "2026-11-14", rationale: "<legacy>" }], [{ account_id: "A1", ticker: "AAA", observed_shares: 5,
  hypothetical_after_shares: 6, target_shares: 8, target_gap_shares: 2, position_status: "partial",
  validation_status: "accepted" }], { esc: format.esc });
assert.match(fundContext, /Previously observed/);
assert.match(fundContext, /&lt;earlier rationale&gt;/);
assert.match(fundContext, /wait for earnings/);
assert.match(fundContext, /reduced first tranche/);
assert.match(fundContext, /unknown/);
assert.match(fundContext, /&lt;legacy&gt;/);
assert.doesNotMatch(fundContext, /<legacy>/);
assert.match(fundContext, /Hypothetical after/);
assert.match(fundContext, /legacy/);
assert.match(fs.readFileSync("static/index.html", "utf8"), /fund-context-1/);

console.log("argus fund manager UI offline check: ok (statuses, explicit empty, legacy, nulls, escaped text)");
