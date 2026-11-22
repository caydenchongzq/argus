const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = __dirname;
const source = fs.readFileSync(path.join(root, "static", "app.js"), "utf8");
const styles = fs.readFileSync(path.join(root, "static", "styles.css"), "utf8");
const RunDraft = require(path.join(root, "static", "run-draft.js"));

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
  replaceChildren() {}
}

const ids = [
  "wlTable", "wlRefreshSelected", "runStart", "runTickerScope", "runStartHelp", "tab-runs", "tab-fund", "tab-themes", "fmExportPdf", "themeExportPdf", "repExportPdf", "confirmText",
];
const elements = Object.fromEntries(ids.map((id) => [id, new Element(id)]));
const tickerInputs = ["AAPL", "MSFT"].map((value) => Object.assign(new Element(value), { value, checked: false }));
const state = {
  refreshTickers: ["AAPL"], flags: { IncludeWatchlist: true },
  bookTickers: [], watchlist: [{ ticker: "AAPL", origins: ["candidate"] }],
  runDraft: RunDraft.create(), runDraftErrors: [], tab: "watchlist",
  pendingRun: null, pendingTheme: null, pendingRemove: null,
};
const tick = [];
const messages = [];
const $ = (selector) => (elements[selector.slice(1)] ||= new Element(selector.slice(1)));
const $$ = () => [];
const handoffStart = source.indexOf("function syncRefreshButton()");
const handoffEnd = source.indexOf("function statusMarkup(status)", handoffStart);
const startFunction = source.indexOf("async function startRunDraft()");
const startHandlerEnd = source.indexOf("function isPendingPaid()", startFunction);
assert.ok(handoffStart >= 0 && handoffEnd > handoffStart, "watchlist refresh handoff handler should exist");
assert.ok(startFunction >= 0 && startHandlerEnd > startFunction, "run draft Start handler should exist");

const manifestCalls = [];
let navigationGeneration = 0;
const context = {
  $, $$, state, RunDraft, runDraftPreviewGeneration: 0, pageNavigationGeneration: 0,
  async setTab(name) { tick.push(name); state.tab = name; navigationGeneration += 1; context.pageNavigationGeneration = navigationGeneration; },
  runEligibility() { return { holdings: [], candidates: ["AAPL"], groups: { AAPL: "candidate" } }; },
  renderRunTickerLists() {},
  renderRunComposer() {},
  clearRunValidation() { state.runDraftErrors = []; },
  syncRefreshButton() {},
  showRunSubmissionError(message) { messages.push(message); },
  showRunValidation(errors) { state.runDraftErrors = errors; },
  renderRunResult(message) { messages.push(message); },
  showToast(message) { messages.push(message); },
  async prepareRunPreview(body, options) { manifestCalls.push({ family: "runs", endpoint: "/api/runs/manifest", body, options }); },
  async prepareThemePreview(mode, includeLlm, sectors, options) { manifestCalls.push({ family: "theme-scout", mode, includeLlm, sectors, options }); },
  openConfirm() {},
  iconSvg() { return ""; },
  moneyLevel(value) { return value == null ? null : `$${Number(value).toFixed(2)}`; },
  moneyCost(value) { return `$${Number(value || 0).toFixed(2)}`; },
  esc(value) { return String(value ?? ""); },
  promiseQueue: { items: [] },
};
vm.runInNewContext(source.slice(handoffStart, handoffEnd), context);
vm.runInNewContext(source.slice(startFunction, startHandlerEnd), context);

(async () => {
  await elements.wlRefreshSelected.listeners.click[0]();
  assert.deepEqual(tick, ["runs"], "selected earnings refreshes should navigate to Runs");
  assert.deepEqual(state.runDraft.tickers, ["AAPL"], "handoff should select only stale ticker(s)");
  assert.equal(state.runDraft.mode, "analyze-review", "handoff keeps the whole portfolio review enabled");
  assert.equal(elements.runStart.scrolled, true, "handoff should direct the user to Start run");
  assert.match(elements.runResult.textContent, /choose Start run to prepare/i, "handoff should make clear that review must be prepared");
  await elements.runStart.listeners.click[0]({});
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
  const exportContext = { $, state, document, URL, fetch, setTimeout() {}, showToast: context.showToast };
  vm.runInNewContext(`${source.slice(printStart, printEnd)}\nglobalThis.exportReportPdf = exportReportPdf;`, exportContext);
  await exportContext.exportReportPdf("fund");
  await exportContext.exportReportPdf("themes");
  await exportContext.exportReportPdf("stock");
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
