const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "static", "app.js"), "utf8");
const runStart = source.indexOf('$("#btnStartRun").addEventListener("click"');
const runEnd = source.indexOf("function isPendingPaid()", runStart);
const themeStart = source.indexOf("async function queueThemeRun(mode)");
const themeEnd = source.indexOf("/* ---------- agents ---------- */", themeStart);
assert.ok(runStart >= 0 && runEnd > runStart, "actual run and scenario handlers should exist");
assert.ok(themeStart >= 0 && themeEnd > themeStart, "actual theme scenario handlers should exist");

class Element {
  constructor(id) {
    this.id = id;
    this.checked = false;
    this.value = "";
    this.disabled = false;
    this.textContent = "";
    this.style = {};
    this.dataset = {};
    this.listeners = {};
    this.classList = { toggle() {}, add() {}, remove() {} };
  }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  click() {
    const event = { target: this, preventDefault() {} };
    for (const listener of this.listeners.click || []) promiseQueue.items.push(listener(event));
  }
  scrollIntoView() { this.scrolled = true; }
}

const ids = [
  "btnStartRun", "btnScreen", "btnScout", "tab-runs", "confirmText", "tickerGrid", "selNone",
  "optRunAgents", "optAnlOnly", "optNoLLM", "optWatchlist", "optRisk", "optNoMacro", "optDate", "optSince",
  "optScoutLlm", "scoutSectors", "scoutSectorCount",
];
const els = Object.fromEntries(ids.map((id) => [id, new Element(id)]));
const checkboxes = ["AAA", "BBB", "CCC"].map((value) => Object.assign(new Element(value), { value }));
const sectors = ["XLK", "XLV"].map((ticker) => Object.assign(new Element(ticker), {
  checked: true, dataset: { scoutSector: ticker },
}));
const allCalls = [];
const toast = [];
const tabs = [];
const state = {
  bookTickers: ["AAA", "BBB"],
  watchlist: [{ ticker: "CCC", origins: ["candidate"] }],
  pendingRun: null,
  pendingTheme: null,
  pendingRemove: null,
};
let confirmCount = 0;
const promiseQueue = { items: [] };

function $(selector) { return els[selector.slice(1)] || new Element(selector); }
function $$(selector) {
  if (selector === "#tickerGrid input:checked") return checkboxes.filter((input) => input.checked);
  if (selector === "#scoutSectors input[data-scout-sector]:checked") return sectors.filter((input) => input.checked);
  if (selector === "#scoutSectors input[data-scout-sector]") return sectors;
  return [];
}
function selectedTickers() { return checkboxes.filter((input) => input.checked).map((input) => input.value); }
function selectedScoutSectors() { return sectors.filter((input) => input.checked).map((input) => input.dataset.scoutSector); }
function updateRunWarn() {}
function showToast(message) { toast.push(message); }
function openConfirm() { confirmCount += 1; }
async function setTab(name) { tabs.push(name); }
function iconSvg() { return ""; }
function moneyLevel(value) { return value == null ? null : `$${Number(value).toFixed(2)}`; }
function api(endpoint, options) {
  const body = JSON.parse(options.body);
  allCalls.push({ endpoint, body });
  if (endpoint === "/api/runs/manifest") {
    return Promise.resolve({
      manifest_sha256: "offline-hash",
      manifest: {
        mode: body.analysis_only ? "ANL" : body.run_agents || body.include_watchlist ? "ANL+REV" : "REV",
        stages: [], fresh_analysis_tickers: body.tickers,
        portfolio_review_context_tickers: ["AAA", "BBB", "CCC"], portfolio_report_inputs: {},
        cost_estimate: { amount_usd: 0, note: "offline fixture" },
        spending_controls: { weekly_budget_enabled: false }, model_price_inventory: { rates: [] }, outputs: {},
      },
    });
  }
  if (endpoint === "/api/theme-scout/manifest") {
    return Promise.resolve({
      manifest_sha256: "offline-theme-hash",
      manifest: {
        model: { model: "offline-model", max_tokens: 1 }, model_scope: { selected_sector_etfs: [] },
        spending_controls: { weekly_budget_enabled: false }, cost_estimate: { amount_usd: 0, note: "offline fixture" },
      },
    });
  }
  throw new Error(`Unexpected API call: ${endpoint}`);
}
function runScenario(name) {
  const button = { dataset: { runScenario: name } };
  const event = { target: { closest(selector) { return selector === "[data-run-scenario]" ? button : null; } } };
  for (const listener of els["tab-runs"].listeners.click || []) promiseQueue.items.push(listener(event));
}
async function settle() {
  while (promiseQueue.items.length) {
    const pending = promiseQueue.items.splice(0);
    await Promise.all(pending);
  }
}
function select(tickers) { checkboxes.forEach((input) => { input.checked = tickers.includes(input.value); }); }
function lastCall(endpoint) { return allCalls.filter((call) => call.endpoint === endpoint).at(-1); }
els.selNone.addEventListener("click", () => { checkboxes.forEach((input) => { input.checked = false; }); });

vm.runInNewContext(`${source.slice(runStart, runEnd)}\n${source.slice(themeStart, themeEnd)}`, {
  $, $$, state, api, openConfirm, showToast, setTab, selectedTickers, selectedScoutSectors, updateRunWarn,
  iconSvg, moneyLevel, promiseQueue,
});

// Snapshot requests a no-LLM manifest with no selected symbols and opens confirmation.
runScenario("snapshot");
settle().then(async () => {
  let request = lastCall("/api/runs/manifest").body;
  assert.equal(request.no_llm, true);
  assert.equal(request.run_agents, false);
  assert.deepEqual(request.tickers, []);
  assert.equal(request.no_macro, false);
  assert.equal(request.analysis_date, "");
  assert.equal(request.since, "");
  assert.equal(confirmCount, 1);

  // Fund-manager-only review carries no fresh ticker scope.
  els.optNoMacro.checked = true;
  els.optDate.value = "2020-01-01";
  els.optSince.value = "2019-01-01";
  runScenario("fund");
  await settle();
  request = lastCall("/api/runs/manifest").body;
  assert.equal(request.no_llm, false);
  assert.equal(request.run_agents, false);
  assert.equal(request.include_watchlist, false);
  assert.deepEqual(request.tickers, []);
  assert.equal(request.no_macro, false);
  assert.equal(request.analysis_date, "");
  assert.equal(request.since, "");

  // Analysis-only preserves the user's explicit ticker set and derives held/candidate scope.
  select(["BBB", "CCC"]);
  runScenario("analyze");
  await settle();
  request = lastCall("/api/runs/manifest").body;
  assert.equal(request.analysis_only, true);
  assert.equal(request.run_agents, true);
  assert.equal(request.include_watchlist, true);
  assert.deepEqual(request.tickers, ["BBB", "CCC"]);

  // Combined run preserves exactly the selection and enables the corresponding sources.
  select(["CCC"]);
  runScenario("analyze-review");
  await settle();
  request = lastCall("/api/runs/manifest").body;
  assert.equal(request.analysis_only, false);
  assert.equal(request.run_agents, false);
  assert.equal(request.include_watchlist, true);
  assert.deepEqual(request.tickers, ["CCC"]);

  // Missing selection cannot request a manifest or open a confirmation.
  const previousCalls = allCalls.length;
  const previousConfirms = confirmCount;
  select([]);
  runScenario("analyze");
  await settle();
  assert.equal(allCalls.length, previousCalls);
  assert.equal(confirmCount, previousConfirms);
  assert.ok(toast.some((message) => message.includes("Select one or more tickers")));

  // Screen is a free screen preview; scout requests one paid model call and both confirm.
  runScenario("screen");
  await settle();
  request = lastCall("/api/theme-scout/manifest").body;
  assert.equal(request.mode, "screen");
  assert.equal(request.include_llm, false);
  assert.equal(confirmCount, previousConfirms + 1);

  runScenario("scout");
  await settle();
  request = lastCall("/api/theme-scout/manifest").body;
  assert.equal(request.mode, "weekly");
  assert.equal(request.include_llm, true);
  assert.equal(request.single_call, true);
  assert.deepEqual(request.sectors, ["XLK", "XLV"]);
  assert.equal(confirmCount, previousConfirms + 2);

  assert.ok(tabs.includes("themes"));
  assert.equal(allCalls.some((call) => !call.endpoint.endsWith("/manifest")), false, "the harness must not launch a run");
  console.log("check_run_scenarios_offline: ok");
}).catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
