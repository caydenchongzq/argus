// Credential-free checks for the account-scoped import UI contract.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
require("./static/formatters.js");
require("./static/tiger-preview-guard.js");
require("./static/portfolio-holdings-render.js");

const current = globalThis.argusBrokerPreviewIsCurrent;
assert.equal(typeof current, "function");
assert.equal(current(2, 2, "acct-b", "acct-b", "acct-b", true), true);
assert.equal(current(1, 2, "acct-a", "acct-b", "acct-a", true), false);
assert.equal(current(2, 2, "acct-b", "acct-b", "acct-a", true), false);
assert.equal(current(2, 2, "acct-b", "acct-b", "acct-b", false), false);

const html = fs.readFileSync("static/index.html", "utf8");
const app = fs.readFileSync("static/app.js", "utf8");
const previewGuard = fs.readFileSync("static/tiger-preview-guard.js", "utf8");
assert.match(html, /id="brokerType"[\s\S]*value="moomoo"/);
assert.match(html, /name="legacyChoice" value="false"/);
assert.match(html, /name="legacyChoice" value="true"/);
assert.match(app, /\/api\/\$\{broker\}\/preview/);
assert.match(html, /<script src="\/static\/tiger-preview-guard\.js\?v=broker-preview-guard-2"><\/script>/);
assert.match(previewGuard, /globalThis\.argusBrokerPreviewIsCurrent\s*=/);
assert.match(app, /argusBrokerPreviewIsCurrent/);
assert.match(app, /replace_legacy/);
assert.match(app, /Unknown USD cash/);
assert.doesNotMatch(html, /AI sub-themes|Sub-theme/);
assert.doesNotMatch(app, /ai_subthemes|sub_theme|wlSubTable|wlSub/);

// Run the production preview renderer and Fetch handler with a DOM-sized fixture.
const syncApplyDefinition = app.match(/function syncBrokerApply\(\)\s*\{[\s\S]*?\n\}/)?.[0];
const renderPreviewDefinition = app.match(/function renderBrokerPreview\(preview\)\s*\{[\s\S]*?\n\}/)?.[0];
const currentBrokerDefinition = app.match(/function currentBroker\(\)\s*\{[\s\S]*?\n\}/)?.[0];
const fetchHandler = app.match(/\$\("#brokerFetch"\)\.addEventListener\("click", async \(\) => \{[\s\S]*?\n\}\);/)?.[0];
assert.ok(syncApplyDefinition && renderPreviewDefinition && currentBrokerDefinition && fetchHandler, "production preview functions should be extractable");
const fetchCallback = fetchHandler.match(/addEventListener\("click", (async \(\) => \{[\s\S]*\})\);$/)?.[1];
assert.ok(fetchCallback, "production Fetch preview callback should be extractable");

const elements = new Map();
function element(id) {
  if (!elements.has(id)) elements.set(id, {
    textContent: "", innerHTML: "", value: "", checked: false, disabled: false, open: true,
    dataset: {}, classes: new Set(),
    classList: {
      toggle(name, force) { force ? this.owner.classes.add(name) : this.owner.classes.delete(name); },
    },
    querySelector() { return { textContent: "" }; },
  });
  const result = elements.get(id);
  result.classList.owner = result;
  return result;
}
const fixturePreview = {
  account_key: "acct-preview", account_label: "Fixture account", fetched_at: "2026-11-15T00:00:00Z",
  position_count: 1, positions: [{ ticker: "XYZ", quantity: 1.25, average_price: 80 }],
  cash: 42.5, currency: "USD", can_apply: true, warnings: [], excluded: [], issues: [], rejected: [],
  replaces_existing_account: false, replace_legacy_choice_required: false,
};
let requestedPath;
const context = {
  state: { tigerPreviewRequestId: 0, tigerPreview: null },
  document: { querySelector: () => null },
  $(selector) { return element(selector.slice(1)); },
  esc: globalThis.argusFormatters.escape,
  qty: globalThis.argusFormatters.quantity,
  price: (value) => value == null ? "—" : `$${Number(value).toFixed(2)}`,
  moneyLevel: globalThis.argusFormatters.moneyLevel,
  api: async (path) => { requestedPath = path; return fixturePreview; },
  showToast: () => {},
  argusBrokerPreviewIsCurrent: globalThis.argusBrokerPreviewIsCurrent,
};
vm.runInNewContext(`${currentBrokerDefinition}\n${syncApplyDefinition}\n${renderPreviewDefinition}`, context);
element("brokerType").value = "tiger";
element("brokerAccount").value = "acct-preview";
element("brokerImportModal").open = true;
const fetchPreview = vm.runInNewContext(`(${fetchCallback})`, context);
fetchPreview().then(() => {
  assert.equal(requestedPath, "/api/tiger/preview");
  assert.match(element("brokerPreviewBody").innerHTML, /XYZ/);
  assert.match(element("brokerPreviewBody").innerHTML, /\$42\.50/);
  assert.equal(context.state.tigerPreview, fixturePreview);
  assert.equal(element("brokerApply").disabled, true, "apply waits for stock-only acknowledgement");
  element("brokerStockOnly").checked = true;
  vm.runInNewContext("syncBrokerApply()", context);
  assert.equal(element("brokerApply").disabled, false, "apply enables after required acknowledgement");
}).catch((error) => {
  console.error(error);
  process.exitCode = 1;
});

const holdingsFormat = {
  esc: globalThis.argusFormatters.escape,
  qty: globalThis.argusFormatters.quantity,
  price: (value) => value == null ? "—" : `$${Number(value).toFixed(2)}`,
  moneyLevel: globalThis.argusFormatters.moneyLevel,
  moneyChange: (value) => value == null ? null : { text: globalThis.argusFormatters.moneyLevel(value), dir: value < 0 ? "loss" : "gain", arrow: value < 0 ? "▼" : "▲" },
  pctChange: (value) => value == null ? null : { text: `${Number(value).toFixed(1)}%`, dir: value < 0 ? "loss" : "gain", arrow: value < 0 ? "▼" : "▲" },
  deltaHtml: (value) => value ? value.text : "—",
  pctLevel: (value) => value == null ? "—" : `${value}%`,
};
const sampleBook = { positions: [{
  ticker: "XYZ", name: "Example", quantity: 15, average_price: 106.67,
  price: 130, market_value: 1950, instrument_type: "Stock", sleeve: "swing",
  account_positions: [
    { account_id: "tiger-1", quantity: 10, average_price: 100, sellable_quantity: 10 },
    { account_id: "moomoo-1", quantity: 5, average_price: 120, sellable_quantity: 4 },
  ],
}] };
const allHoldings = globalThis.argusRenderPortfolioHoldings(sampleBook, "all", holdingsFormat);
const tigerHoldings = globalThis.argusRenderPortfolioHoldings(sampleBook, "tiger-1", holdingsFormat);
const moomooHoldings = globalThis.argusRenderPortfolioHoldings(sampleBook, "moomoo-1", holdingsFormat);
assert.match(allHoldings, /15<\/td>/);
assert.match(allHoldings, /\$1,950\.00/);
assert.match(tigerHoldings, /10<\/td>/);
assert.match(tigerHoldings, /10<\/td>\s*<td class="ar-num">\$100\.00/);
assert.match(tigerHoldings, /\$1,300\.00/);
assert.match(tigerHoldings, /\$300\.00/);
assert.match(moomooHoldings, /5<\/td>/);
assert.match(moomooHoldings, /4<\/td>\s*<td class="ar-num">\$120\.00/);
assert.match(moomooHoldings, /\$650\.00/);
assert.match(moomooHoldings, /\$50\.00/);
const unknownAccount = globalThis.argusRenderPortfolioAccounts([{
  account_id: "moomoo-unknown", broker: "moomoo", label: "Moomoo", cash: null,
  cash_known: false, holdings_value: null, total_market_value: null, fetched_at: "now",
}], holdingsFormat);
assert.match(unknownAccount, /Unknown/);
assert.match(unknownAccount, /—/);
assert.doesNotMatch(unknownAccount, /null|\$0\.00/);
assert.match(html, /id="pfAccountFilter"><option value="all">All accounts<\/option>/);

console.log("argus broker UI offline check: ok (preview rendering, confirmation, account guard, legacy binding, null cash)");
