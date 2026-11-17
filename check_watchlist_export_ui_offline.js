const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = __dirname;
const source = fs.readFileSync(path.join(root, "static", "app.js"), "utf8");
const styles = fs.readFileSync(path.join(root, "static", "styles.css"), "utf8");

class Element {
  constructor(id) {
    this.id = id;
    this.listeners = {};
    this.dataset = {};
    this.disabled = false;
    this.textContent = "";
    this.classList = { toggle() {}, add() {}, remove() {} };
  }
  addEventListener(type, listener) { (this.listeners[type] ||= []).push(listener); }
  closest() { return { classList: this.classList }; }
  scrollIntoView() { this.scrolled = true; }
}

const ids = [
  "wlTable", "wlRefreshSelected", "btnStartRun", "tab-runs", "tab-fund", "tab-themes", "fmExportPdf", "themeExportPdf", "repExportPdf", "confirmText",
  "optRunAgents", "optAnlOnly", "optNoLLM", "optWatchlist", "optRisk", "optNoMacro", "optDate", "optSince",
];
const elements = Object.fromEntries(ids.map((id) => [id, new Element(id)]));
const tickerInputs = ["AAPL", "MSFT"].map((value) => Object.assign(new Element(value), { value, checked: false }));
const state = {
  refreshTickers: ["AAPL"], flags: { IncludeWatchlist: true },
  bookTickers: [], watchlist: [{ ticker: "AAPL", origins: ["candidate"] }],
  pendingRun: null, pendingTheme: null, pendingRemove: null,
};
const tick = [];
const messages = [];
const $ = (selector) => elements[selector.slice(1)];
const $$ = (selector) => selector === "#tickerGrid input" ? tickerInputs : [];
const selectedTickers = () => tickerInputs.filter((input) => input.checked).map((input) => input.value);
const handoffStart = source.indexOf("function syncRefreshButton()");
const handoffEnd = source.indexOf("function selectedScoutSectors()", handoffStart);
const runStart = source.indexOf('$("#btnStartRun").addEventListener("click"');
const runEnd = source.indexOf("function isPendingPaid()", runStart);
assert.ok(handoffStart >= 0 && handoffEnd > handoffStart, "watchlist refresh handoff handler should exist");
assert.ok(runStart >= 0 && runEnd > runStart, "run manifest handler should exist");

const manifestCalls = [];
const context = {
  $, $$, state,
  async setTab(name) { tick.push(name); },
  selectedTickers,
  updateRunWarn() {},
  showToast(message) { messages.push(message); },
  api(endpoint, options) {
    const body = JSON.parse(options.body);
    manifestCalls.push({ endpoint, body });
    return Promise.resolve({
      manifest_sha256: "offline-refresh-hash",
      manifest: {
        mode: body.include_watchlist ? "ANL+REV" : "REV", stages: [],
        fresh_analysis_tickers: body.tickers, portfolio_review_context_tickers: ["AAPL"],
        portfolio_report_inputs: {}, cost_estimate: { amount_usd: 0 },
        spending_controls: { weekly_budget_enabled: false }, model_price_inventory: { rates: [] }, outputs: {},
      },
    });
  },
  openConfirm() {},
  openConfirm() {},
  iconSvg() { return ""; },
  moneyLevel(value) { return value == null ? null : `$${Number(value).toFixed(2)}`; },
  moneyCost(value) { return `$${Number(value || 0).toFixed(2)}`; },
  esc(value) { return String(value ?? ""); },
  promiseQueue: { items: [] },
};
vm.runInNewContext(`${source.slice(runStart, runEnd)}\n${source.slice(handoffStart, handoffEnd)}`, context);

(async () => {
  await elements.wlRefreshSelected.listeners.click[0]();
  assert.deepEqual(tick, ["runs"], "selected earnings refreshes should navigate to Runs");
  assert.deepEqual(tickerInputs.filter((input) => input.checked).map((input) => input.value), ["AAPL"], "handoff should select only stale ticker(s)");
  assert.equal(elements.optAnlOnly.checked, false, "handoff must keep portfolio review enabled");
  assert.equal(elements.optWatchlist.checked, true, "candidate refresh should enable watchlist analysis");
  assert.equal(elements.btnStartRun.scrolled, true, "handoff should direct the user to the confirmation action");
  assert.match(messages[0], /confirm to start/i, "handoff should tell the user that confirmation is still required");
  await elements.btnStartRun.listeners.click[0]({});
  assert.equal(manifestCalls.length, 1, "handoff should prepare a manifest without starting a run");
  assert.equal(manifestCalls[0].endpoint, "/api/runs/manifest");
  assert.equal(manifestCalls[0].body.analysis_only, false, "manifest should include the fund-manager review stage");
  assert.equal(manifestCalls[0].body.run_agents, false, "candidate-only selection should not request book agents");
  assert.equal(manifestCalls[0].body.include_watchlist, true, "manifest should include candidate analysis");
  assert.deepEqual(manifestCalls[0].body.tickers, ["AAPL"]);
  assert.equal(manifestCalls[0].body.confirm, false, "manifest request should remain preview-only until confirmation");

  const printStart = source.indexOf("async function exportReportPdf(kind)");
  const printEnd = source.indexOf('$("#fmDate").addEventListener', printStart);
  assert.ok(printStart >= 0 && printEnd > printStart, "report export handlers should exist");
  const requests = [], downloads = [];
  state.fund = { markdown: "# Selected historical fund report" };
  state.themeReport = { markdown: "# Latest theme report" };
  state.stockReport = { markdown: "# Selected stock report", meta: { ticker: "TEST" } };
  const document = { createElement() { return { click() { downloads.push(this.download); } }; } };
  const URL = { createObjectURL() { return "blob:test"; }, revokeObjectURL() {} };
  const fetch = async (url, options) => { requests.push({ url, body: JSON.parse(options.body) }); return { ok: true, async blob() { return {}; } }; };
  vm.runInNewContext(source.slice(printStart, printEnd), { $, state, document, URL, fetch, setTimeout() {}, showToast: context.showToast });
  await elements.fmExportPdf.listeners.click[0]();
  await elements.themeExportPdf.listeners.click[0]();
  await elements.repExportPdf.listeners.click[0]();
  assert.deepEqual(requests.map((r) => r.body.markdown), [state.fund.markdown, state.themeReport.markdown, state.stockReport.markdown], "export must send the displayed report markdown");
  assert.deepEqual(downloads, ["fund-manager-report.pdf", "theme-scout-report.pdf", "TEST-report.pdf"]);
  assert.equal(requests[0].url, "/api/report-pdf");
  assert.match(source, /renderMarkdown\(\$\("#fmMd"\), data\.markdown \|\| ""\)/, "fund report display retains sanitized rendering");
  const epsStart = source.indexOf("function earningsEpsValues(");
  const epsEnd = source.indexOf("function formatDateTime(", epsStart);
  assert.ok(epsStart >= 0 && epsEnd > epsStart, "event-specific EPS mapping should exist");
  const epsFixture = {};
  vm.runInNewContext(`${source.slice(epsStart, epsEnd)}\nglobalThis.result = earningsEpsValues({ reported_eps: 1.2, estimated_eps: null }, { estimated_eps: 4.5 }, { reported_eps: 1.2, estimated_eps: 4.5 });`, epsFixture);
  assert.equal(epsFixture.result.lastEstimated, null, "next-quarter estimate must not appear on the completed earnings event");
  assert.equal(epsFixture.result.nextEstimated, 4.5, "next-quarter estimate should remain visible on the upcoming event");
  process.stdout.write("check_watchlist_export_ui_offline: ok\n");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
