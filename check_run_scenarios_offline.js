const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = __dirname;
const appSource = fs.readFileSync(path.join(root, "static", "app.js"), "utf8");
const html = fs.readFileSync(path.join(root, "static", "index.html"), "utf8");
const RunDraft = require(path.join(root, "static", "run-draft.js"));
const styles = fs.readFileSync(path.join(root, "static", "styles.css"), "utf8");

assert.match(html, /run-draft\.js\?v=[^"']+/);
assert.ok(html.indexOf("run-draft.js") < html.indexOf("app.js"), "draft helper loads before app caller");
assert.match(appSource, /data-run-ticker="\$\{esc\(ticker\)\}"[^>]*value="\$\{esc\(ticker\)\}"/,
  "rendered ticker checkbox must have its explicit symbol value");
assert.match(styles, /#runComposer\s+\[hidden\]\s*\{\s*display:\s*none\s*!important;/,
  "conditional composer panels must honor hidden even when component styles set display");

// The actual scenario change handler only updates draft state and local UI.
class Element {
  constructor(id = "") {
    this.id = id;
    this.value = "";
    this.checked = false;
    this.disabled = false;
    this.textContent = "";
    this.listeners = {};
    this.hidden = false;
    this.attributes = {};
  }
  addEventListener(type, callback) { (this.listeners[type] ||= []).push(callback); }
  setAttribute(name, value) { this.attributes[name] = value; }
  removeAttribute(name) { delete this.attributes[name]; }
  closest(selector) { return selector === 'input[name="runScenario"]' ? this : null; }
  replaceChildren() {}
  focus() { this.focused = true; }
}

const scenarioFieldset = new Element("runScenarios");
const startButton = new Element("runStart");
const generic = new Map();
const bySelector = (selector) => {
  if (selector === "#runScenarios") return scenarioFieldset;
  if (selector === "#runStart") return startButton;
  if (!generic.has(selector)) generic.set(selector, new Element(selector));
  return generic.get(selector);
};
const ui = {
  state: { runDraft: RunDraft.create(), runDraftErrors: [] },
  apiCalls: [],
  tabs: [],
  dialogs: 0,
  renders: 0,
  results: [],
};
const scenarioStart = appSource.indexOf('$("#runScenarios").addEventListener("change"');
const scenarioEnd = appSource.indexOf('$("#runComposer").addEventListener("change"', scenarioStart);
assert.ok(scenarioStart >= 0 && scenarioEnd > scenarioStart, "scenario handler is present");
const scenarioContext = {
  $, $$: () => [], state: ui.state, RunDraft,
  clearRunValidation() {}, renderRunComposer() { ui.renders += 1; },
  renderRunResult(message) { ui.results.push(message); },
};
function $(selector) { return bySelector(selector); }
vm.runInNewContext(appSource.slice(scenarioStart, scenarioEnd), scenarioContext);
const selectScenario = (mode) => {
  const radio = new Element();
  radio.value = mode;
  const event = { target: { closest: (selector) => selector === "input[name='runScenario']" ? radio : null } };
  scenarioFieldset.listeners.change[0](event);
};
for (const mode of Object.keys(RunDraft.modes)) {
  const previous = { ...ui.state.runDraft };
  const requestsBefore = ui.apiCalls.length;
  const dialogsBefore = ui.dialogs;
  const tabsBefore = ui.tabs.length;
  selectScenario(mode);
  assert.equal(ui.state.runDraft.mode, mode, `${mode} becomes selected in local draft`);
  assert.equal(ui.apiCalls.length, requestsBefore, `${mode} selection makes no API request`);
  assert.equal(ui.dialogs, dialogsBefore, `${mode} selection opens no dialog`);
  assert.equal(ui.tabs.length, tabsBefore, `${mode} selection does not change tabs`);
  assert.deepEqual(ui.state.runDraft.tickers, previous.tickers, `${mode} selection preserves ticker selection`);
  assert.equal(ui.renders > 0, true, `${mode} selection rerenders the draft`);
}

// Pure request adapters keep each existing API schema explicit and omit inapplicable controls.
const eligibility = { NVDA: "holding", XLV: "candidate", XLP: "candidate" };
let draft = RunDraft.create();
draft = RunDraft.setOptions(draft, { dateMode: "custom", date: "2026-11-18", since: "2026-10-01", includeEconomicData: false });
draft = RunDraft.setTickerSelection(draft, ["NVDA", "XLV"], eligibility);
const research = RunDraft.request(RunDraft.setMode(draft, "analyze"), eligibility);
assert.equal(research.family, "runs");
assert.deepEqual(research.body.tickers, ["NVDA", "XLV"]);
assert.equal(research.body.run_agents, true);
assert.equal(research.body.include_watchlist, true);
assert.equal(research.body.analysis_only, true);
assert.equal(research.body.analysis_date, "2026-11-18");
assert.equal(research.body.since, "", "research-only excludes holding cutoff");
assert.equal(research.body.no_macro, false, "research-only excludes economic data option");
assert.equal(research.body.include_risk, false);

const combined = RunDraft.request(RunDraft.setMode(draft, "analyze-review"), eligibility);
assert.deepEqual(combined.body.tickers, ["NVDA", "XLV"]);
assert.equal(combined.body.since, "2026-10-01");
assert.equal(combined.body.no_macro, true);
const fund = RunDraft.request(RunDraft.setMode(draft, "fund"), eligibility);
assert.deepEqual(fund.body.tickers, [], "fund review sends no fresh ticker scope");
assert.equal(fund.body.since, "2026-10-01");
assert.equal(fund.body.include_watchlist, false);
const snapshot = RunDraft.request(RunDraft.setMode(draft, "snapshot"), eligibility);
assert.equal(snapshot.body.no_llm, true);
assert.deepEqual(snapshot.body.tickers, []);
assert.equal(snapshot.body.analysis_date, "2026-11-18");
const screen = RunDraft.request(RunDraft.setMode(draft, "screen"), eligibility);
assert.equal(screen.family, "theme-scout");
assert.equal(screen.body.mode, "screen");
assert.equal(screen.body.include_llm, false);
assert.equal(Object.hasOwn(screen.body, "analysis_date"), false);
const scout = RunDraft.request(RunDraft.setMode(draft, "scout"), eligibility);
assert.equal(scout.body.mode, "weekly");
assert.equal(scout.body.include_llm, true);
assert.deepEqual(scout.body.sectors, RunDraft.sectors.map((sector) => sector.ticker));

assert.ok(RunDraft.request(RunDraft.setMode(RunDraft.create(), "analyze"), {}).errors
  .some((error) => error.message === "Choose at least one ticker to research."));
assert.ok(RunDraft.request(RunDraft.setSectors(RunDraft.setMode(RunDraft.create(), "screen"), []), {}).errors
  .some((error) => error.field === "sectors"));
assert.ok(RunDraft.validate(RunDraft.setOptions(draft, { date: "2026-02-30" }), eligibility)
  .some((error) => error.field === "date"));
const missing = RunDraft.selectedSourceChanges(draft, { NVDA: "holding" });
assert.deepEqual(missing.missing, ["XLV"], "removed eligible names require review");
const moved = RunDraft.selectedSourceChanges(draft, { NVDA: "candidate", XLV: "candidate" });
assert.deepEqual(moved.changed, ["NVDA"], "holding/candidate changes require review");

(async () => {
// Intentional Start uses the correct manifest family and blocks duplicate preview requests.
const startStart = appSource.indexOf("async function startRunDraft()");
const startEnd = appSource.indexOf("function isPendingPaid()", startStart);
assert.ok(startStart >= 0 && startEnd > startStart, "Start handler is present");
const startState = { runDraft: RunDraft.create(), runDraftErrors: [] };
const startPreviews = [];
const startContext = {
  $, state: startState, RunDraft, runDraftPreviewGeneration: 0,
  runEligibility: () => ({ groups: eligibility }),
  clearRunValidation() { startState.runDraftErrors = []; },
  renderRunResult(message) { ui.results.push(message); },
  renderRunComposer() { ui.renders += 1; },
  showRunValidation(errors) { startState.runDraftErrors = errors; },
  showRunSubmissionError(message) { ui.results.push(`submission-error:${message}`); },
  previews: startPreviews,
  async prepareRunPreview(body, options) { startPreviews.push({ family: "runs", body, options }); },
  async prepareThemePreview(mode, includeLlm, sectors, options) { startPreviews.push({ family: "theme-scout", mode, includeLlm, sectors, options }); },
};
const startCode = `let runPreviewInFlight = false;\n${appSource.slice(startStart, startEnd)}`;
vm.runInNewContext(startCode, startContext);
const clickStart = () => startButton.listeners.click[0]({});
startContext.state.runDraft = RunDraft.setMode(RunDraft.create(), "analyze");
const invalidStart = clickStart();
assert.equal(startContext.state.runDraftErrors[0].message, "Choose at least one ticker to research.");
assert.equal(startContext.previews.length, 0, "invalid research does not request a manifest");
await invalidStart;

startContext.state.runDraft = RunDraft.setTickerSelection(startContext.state.runDraft, ["NVDA", "XLV"], eligibility);
const validStart = clickStart();
await validStart;
assert.equal(startContext.previews.at(-1).family, "runs");
assert.deepEqual(startContext.previews.at(-1).body.tickers, ["NVDA", "XLV"]);
assert.equal(startContext.previews.at(-1).options.draftRevision, startContext.state.runDraft.revision);
startContext.state.runDraft = RunDraft.setMode(startContext.state.runDraft, "scout");
const scoutStart = clickStart();
await scoutStart;
assert.equal(startContext.previews.at(-1).family, "theme-scout");
assert.equal(startContext.previews.at(-1).mode, "weekly");
assert.equal(startContext.previews.at(-1).includeLlm, true);

let releasePreview;
let pendingPreviewCalls = 0;
startContext.state.runDraft = RunDraft.create();
startContext.prepareRunPreview = () => {
  pendingPreviewCalls += 1;
  return new Promise((resolve) => { releasePreview = resolve; });
};
const firstStart = clickStart();
const secondStart = clickStart();
assert.equal(pendingPreviewCalls, 1, "duplicate Start is ignored while preview is in flight");
await secondStart;
assert.equal(typeof releasePreview, "function");
releasePreview();
await firstStart;

// Actual preview helpers discard both run-family responses after leaving and returning to Runs.
const previewStart = appSource.indexOf("function isCurrentRunDraftPreview(");
const previewEnd = appSource.indexOf("async function startRunDraft()", previewStart);
assert.ok(previewStart >= 0 && previewEnd > previewStart, "preview guards and helpers are present");
const pendingRequests = [];
const previewState = {
  tab: "runs", runDraft: { revision: 41 }, pendingRun: null, pendingTheme: null,
  pendingRemove: null,
};
let previewConfirmCount = 0;
let previewGeneration = 0;
const previewContext = {
  state: previewState, runDraftPreviewGeneration: previewGeneration,
  api(endpoint) {
    return new Promise((resolve) => pendingRequests.push({ endpoint, resolve }));
  },
  renderRunResult() {}, openConfirm() { previewConfirmCount += 1; },
  renderRunSubmissionError() {}, discardStaleRunDraftPreview(message) {
    if (previewState.tab === "runs") this.renderRunResult(message);
    return false;
  },
  isCurrentRunDraftPreview(revision, generation) {
    return previewState.tab === "runs" && previewState.runDraft.revision === revision
      && this.runDraftPreviewGeneration === generation;
  },
  showRunSubmissionError() {}, showToast() {}, moneyLevel() { return "$0.00"; },
  $() { return new Element(); },
  RunDraft,
};
vm.runInNewContext(appSource.slice(previewStart, previewEnd), previewContext);
// Run manifest held across a page switch and return must not open or stage confirmation.
const delayedRun = previewContext.prepareRunPreview({ tickers: ["NVDA"] }, { draftRevision: 41, previewGeneration: 0 });
assert.equal(pendingRequests.at(-1).endpoint, "/api/runs/manifest");
previewState.tab = "portfolio";
previewContext.runDraftPreviewGeneration += 1;
previewState.tab = "runs";
pendingRequests.at(-1).resolve({ manifest_sha256: "stale-run" });
assert.equal(await delayedRun, false);
assert.equal(previewState.pendingRun, null);
assert.equal(previewConfirmCount, 0);

// The scout manifest follows the same guard and leaves explicit Themes previews unaffected.
const delayedScout = previewContext.prepareThemePreview("weekly", true, ["XLK"], {
  draftRevision: 41, previewGeneration: 1,
});
assert.equal(pendingRequests.at(-1).endpoint, "/api/theme-scout/manifest");
previewState.tab = "agents";
previewContext.runDraftPreviewGeneration += 1;
previewState.tab = "runs";
pendingRequests.at(-1).resolve({ manifest_sha256: "stale-scout" });
assert.equal(await delayedScout, false);
assert.equal(previewState.pendingTheme, null);
assert.equal(previewConfirmCount, 0);

// A removed eligibility row remains selected and invalid until the user reselects/removes it.
const tickerRender = appSource.slice(appSource.indexOf("function renderRunTickerLists()"), appSource.indexOf("function renderRunTickerChanges()"));
assert.match(tickerRender, /data-run-ticker="\$\{esc\(ticker\)\}" data-run-source="\$\{group\}" value="\$\{esc\(ticker\)\}"/);

console.log("check_run_scenarios_offline: ok");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
