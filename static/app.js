/* Argus frontend. Rendering uses the brand system; API behaviour is unchanged. */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const SPRITE = "/static/argus-brand/assets/icons/argus-icons.svg";
const MINUS = "\u2212";
const RunDraft = globalThis.ArgusRunDraft;
let runDraftPreviewGeneration = 0;

const state = {
  tab: "portfolio",
  portfolio: null,
  portfolioAccountId: "all",
  watchlist: [],
  refreshTickers: [],
  watchlistProposal: null,
  reports: [],
  latestByTicker: {},
  fund: null,
  themeReport: null,
  runs: [],
  flags: {},
  selectedReport: null,
  stockReport: null,
  selectedRun: null,
  runScopeRows: {},
  runDraft: RunDraft.create(),
  runDraftErrors: [],
  pendingTheme: null,
  pendingRemove: null,
  logOffset: 0,
  logText: "",
  logTimer: null,
  chart: null,
  bookTickers: [],
  pendingRun: null,
  runReviewFocusOnClose: false,
  tigerPreview: null,
  tigerPreviewRequestId: 0,
  pendingAgentSave: false,
  pendingSettingsSave: false,
  settings: null,
  token: null,
  agentDoc: null,
  agentDraft: {},
  agentSelected: null,
  agentTab: "preview",
  agentQuery: "",
  agentModifiedOnly: false,
  agentLoading: false,
  agentError: "",
  agentCloseMode: null,
};

let closingFromConfirm = false;

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;",
  }[c]));
}

function iconSvg(name, cls = "ar-btn__icon") {
  return `<svg class="${cls}" aria-hidden="true"><use href="${SPRITE}#${name}"/></svg>`;
}

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function looksNumeric(text) {
  const t = String(text || "").replace(/\s+/g, " ").trim();
  if (!t || t === "—" || t === "-" || t === "–") return false;
  return /^[+\u2212−-]?(?:US)?\$?\d{1,3}(?:,\d{3})*(?:\.\d+)?%?$/.test(t)
    || /^[+\u2212−-]?\d+(?:\.\d+)?%?$/.test(t);
}

function renderMarkdown(el, md) {
  if (!md) {
    el.innerHTML = "<p class='ar-muted'>No markdown report</p>";
    return;
  }
  if (!window.marked || !window.DOMPurify) {
    el.textContent = md;
    return;
  }
  el.innerHTML = DOMPurify.sanitize(marked.parse(md), { USE_PROFILES: { html: true } });
  el.querySelectorAll("table").forEach((table) => {
    const wrap = document.createElement("div");
    wrap.className = "ar-md-table";
    table.parentNode.insertBefore(wrap, table);
    wrap.appendChild(table);
    table.querySelectorAll("th, td").forEach((cell) => {
      const text = (cell.textContent || "").replace(/\s+/g, " ").trim();
      if (looksNumeric(text)) cell.classList.add("ar-num");
      else if (cell.tagName === "TD" && text.length > 48) cell.classList.add("ar-md-prose");
    });
  });
}

function groupThousands(digits) {
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

function moneyAbs(n, abbreviate) {
  const abs = Math.abs(Number(n));
  if (abbreviate && abs >= 1000000) {
    const millions = abs / 1000000;
    return `$${millions.toFixed(2)}M`;
  }
  const [whole, frac] = abs.toFixed(2).split(".");
  return `$${groupThousands(whole)}.${frac}`;
}

function moneyLevel(n, abbreviate = false) {
  return globalThis.argusFormatters.moneyLevel(n, abbreviate);
}

function moneyChange(n, abbreviate = false) {
  if (n == null || Number.isNaN(Number(n))) return null;
  const v = Number(n);
  const body = moneyAbs(v, abbreviate);
  if (v > 0) return { text: `+${body}`, dir: "gain", arrow: "▲" };
  if (v < 0) return { text: `${MINUS}${body}`, dir: "loss", arrow: "▼" };
  return { text: body, dir: "flat", arrow: "■" };
}

function pctLevel(n, digits = 1) {
  if (n == null || Number.isNaN(Number(n))) return "—";
  return `${Number(n).toFixed(digits)}%`;
}

function pctChange(n, digits = 2) {
  if (n == null || Number.isNaN(Number(n))) return null;
  const v = Number(n);
  const abs = Math.abs(v).toFixed(digits);
  if (v > 0) return { text: `+${abs}%`, dir: "gain", arrow: "▲" };
  if (v < 0) return { text: `${MINUS}${abs}%`, dir: "loss", arrow: "▼" };
  return { text: `${(0).toFixed(digits)}%`, dir: "flat", arrow: "■" };
}

function deltaHtml(part) {
  if (!part) return `<span class="ar-subtle">—</span>`;
  return `<span class="ar-delta ar-delta--${part.dir}">${esc(part.text)} <span class="ar-delta__arrow">${part.arrow}</span></span>`;
}

function price(n) {
  if (n == null || Number.isNaN(Number(n))) return "—";
  const v = Number(n);
  const digits = v !== 0 && Math.abs(v) < 1 ? 4 : 2;
  const abs = Math.abs(v).toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
  const body = `$${abs}`;
  return v < 0 ? `${MINUS}${body}` : body;
}

function qty(n) {
  return globalThis.argusFormatters.quantity(n);
}

function ratingClass(r) {
  const x = (r || "").toLowerCase();
  if (x.includes("sell")) return "ar-rating ar-rating--sell";
  if (x.includes("underweight")) return "ar-rating ar-rating--underweight";
  if (x.includes("overweight")) return "ar-rating ar-rating--overweight";
  if (x.includes("buy")) return "ar-rating ar-rating--buy";
  return "ar-rating ar-rating--hold";
}

function ratingMarkup(r) {
  if (!r) return `<span class="ar-subtle">—</span>`;
  return `<span class="${ratingClass(r)}">${esc(r)}</span>`;
}

function actionClass(action) {
  const x = (action || "").toLowerCase();
  if (x.includes("sell") || x.includes("trim") || x.includes("reduce")) return "ar-loss";
  if (x.includes("buy") || x === "add") return "ar-gain";
  return "ar-flat";
}

function formatSessionDate(iso) {
  if (!iso) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso));
  if (!m) return String(iso);
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${days[d.getDay()]} ${d.getDate()} ${months[d.getMonth()]}`;
}

function showToast(message, kind = "info") {
  const stack = $("#toasts");
  if (!stack) return;
  const el = document.createElement("div");
  el.className = `ar-toast ar-toast--${kind}`;
  el.setAttribute("role", kind === "danger" ? "alert" : "status");
  const icon = kind === "danger" ? "circle-x" : kind === "warn" ? "triangle-alert" : kind === "ok" ? "circle-check" : "info";
  el.innerHTML = `${iconSvg(icon, "ar-icon")}<div class="ar-toast__body"><div class="ar-toast__text"></div></div>
    <button type="button" class="ar-btn ar-btn--sm ar-btn--ghost" aria-label="Dismiss" data-tooltip="Dismiss">${iconSvg("x")}<span class="ar-btn__label">Dismiss</span></button>`;
  el.querySelector(".ar-toast__text").textContent = message;
  el.querySelector("button").addEventListener("click", () => el.remove());
  stack.appendChild(el);
  if (kind !== "danger") setTimeout(() => { el.remove(); }, 5000);
}

async function api(path, opts = {}) {
  const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
  if (state.token) headers["X-Argus-Confirm"] = state.token;
  const res = await fetch(path, { ...opts, headers });
  const text = await res.text();
  let data;
  try { data = text ? JSON.parse(text) : null; } catch { data = { detail: text }; }
  if (!res.ok) {
    const msg = data?.detail || res.statusText;
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return data;
}

async function loadSettings() {
  const settings = await api("/api/settings");
  state.settings = settings;
  $("#settingsBudgetEnabled").checked = !!settings.weekly_budget_enabled;
  $("#settingsBudgetUsd").value = settings.weekly_budget_usd ?? 25;
  $("#settingsMaxCandidates").value = settings.max_candidates ?? "";
  $("#settingsMaxSector").value = settings.max_stocks_per_sector ?? "";
  const limits = [
    settings.max_candidates == null ? "unlimited saved candidates" : `${settings.max_candidates} saved candidates`,
    settings.max_stocks_per_sector == null ? "unlimited stocks per sector" : `${settings.max_stocks_per_sector} stocks per sector`,
  ].join("; ");
  const cooldown = settings.cooldown_days == null ? "14-day" : `${settings.cooldown_days}-day`;
  $("#settingsStatus").textContent = `Weekly spending check ${settings.weekly_budget_enabled ? `enabled at $${Number(settings.weekly_budget_usd).toFixed(2)}` : "disabled"}; ${limits}; ${cooldown} cooldown. Weekly add and drop caps are unlimited.`;
}

function nullableNumber(id) {
  const value = $(id).value.trim();
  return value === "" ? null : Number(value);
}

function requestSettingsSave() {
  const amount = Number($("#settingsBudgetUsd").value);
  if (!Number.isFinite(amount) || amount < 0) {
    showToast("Enter a valid weekly amount.", "warning");
    return;
  }
  state.pendingRun = null;
  state.pendingTheme = null;
  state.pendingRemove = null;
  state.pendingAgentSave = false;
  state.pendingSettingsSave = true;
  const weekly = $("#settingsBudgetEnabled").checked ? "enabled" : "disabled";
  $("#confirmText").textContent = `Save these policy settings? The weekly spending check will be ${weekly}; the $${amount.toFixed(2)} allowance is kept for later if disabled. New watchlist additions use the limits shown. Existing candidates will stay saved. No model is called.`;
  openConfirm();
}

async function persistSettings() {
  const body = {
    weekly_budget_enabled: $("#settingsBudgetEnabled").checked,
    weekly_budget_usd: Number($("#settingsBudgetUsd").value),
    max_candidates: nullableNumber("#settingsMaxCandidates"),
    max_stocks_per_sector: nullableNumber("#settingsMaxSector"),
  };
  await api("/api/settings", { method: "PUT", body: JSON.stringify(body) });
  await loadSettings();
  showToast("Policy settings saved.", "ok");
}

$("#settingsSave").addEventListener("click", requestSettingsSave);

/* ---------- theme ---------- */
function syncChromeToggles() {
  const choice = document.documentElement.getAttribute("data-theme") || "system";
  $$("[data-theme-set]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.themeSet === choice)));
  const density = document.documentElement.getAttribute("data-density") || "comfortable";
  $$("[data-density-set]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.densitySet === density)));
}

function repaintChart() {
  if (state.tab === "portfolio" && state.portfolio) renderWeightsChart(state.portfolio);
}

$("#themeToggle").addEventListener("click", (e) => {
  const b = e.target.closest("[data-theme-set]");
  if (!b || !window.argusSetTheme) return;
  window.argusSetTheme(b.dataset.themeSet);
  syncChromeToggles();
  repaintChart();
});

$("#densityToggle").addEventListener("click", (e) => {
  const b = e.target.closest("[data-density-set]");
  if (!b || !window.argusSetDensity) return;
  window.argusSetDensity(b.dataset.densitySet);
  syncChromeToggles();
  if (state.chart) state.chart.resize();
});

matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
  if (!document.documentElement.hasAttribute("data-theme")) repaintChart();
});

/* ---------- tabs ---------- */
async function setTab(name) {
  if (state.tab === "runs" && name !== "runs") runDraftPreviewGeneration += 1;
  state.tab = name;
  $$("#nav .ar-tab").forEach((b) => {
    const on = b.dataset.tab === name;
    b.setAttribute("aria-selected", on ? "true" : "false");
  });
  $$(".ar-page").forEach((t) => t.classList.toggle("hidden", t.id !== `tab-${name}`));
  try {
    if (name === "portfolio") await loadPortfolio();
    if (name === "watchlist") await loadWatchlist();
    if (name === "reports") await loadReports();
    if (name === "fund") await loadFund();
    if (name === "themes") await loadThemes();
    if (name === "runs") await loadRuns();
  if (name === "agents") { await loadAgents(); await loadSettings(); }
  } catch (e) {
    showToast(e.message, "danger");
  }
}

$("#nav").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-tab]");
  if (b) setTab(b.dataset.tab);
});

/* ---------- health ---------- */
async function loadHealth() {
  const pill = $("#healthPill");
  try {
    const h = await api("/api/health");
    pill.className = `ar-badge ${h.data_ok ? "ar-badge--ok" : "ar-badge--warn"}`;
    pill.innerHTML = `<span class="ar-badge__dot"></span> ${h.data_ok ? "Connected" : "Data missing"}`;
  } catch (e) {
    pill.className = "ar-badge ar-badge--danger";
    pill.innerHTML = `<span class="ar-badge__dot"></span> Offline`;
  }
}

/* ---------- portfolio ---------- */
function setHeaderAsOf(data) {
  const el = $("#headerAsOf");
  const when = formatSessionDate(data.prices_as_of);
  if (!when) {
    el.textContent = "Cost basis only · no prices yet";
    return;
  }
  const stale = data.book_newer_than_stats
    ? ` <span class="ar-badge ar-badge--warn" data-tooltip="As of ${esc(data.prices_as_of)}" tabindex="0">⚠ Stale</span>`
    : "";
  el.innerHTML = `Data as of ${esc(when)} · US session${stale}`;
}

async function loadPortfolio() {
  const data = await api("/api/portfolio");
  state.portfolio = data;
  state.bookTickers = (data.positions || []).map((p) => p.ticker);
  setHeaderAsOf(data);
  const cashKnown = data.cash_known !== false && data.cash != null;
  const accounts = data.accounts || [];
  const unknownCashAccounts = accounts.filter((a) => a.cash_known === false || a.cash == null);
  const accountSelect = $("#pfAccountFilter");
  const previousAccount = state.portfolioAccountId || accountSelect.value || "all";
  accountSelect.innerHTML = `<option value="all">All accounts</option>${accounts
    .filter((a) => a.account_id != null)
    .map((a) => `<option value="${esc(a.account_id)}">${esc(a.label || a.account_id)} · ${esc(a.broker || "Legacy")}</option>`).join("")}`;
  state.portfolioAccountId = accounts.some((a) => a.account_id === previousAccount) ? previousAccount : "all";
  accountSelect.value = state.portfolioAccountId;
  $("#pfSub").textContent = cashKnown && data.total_market_value != null
    ? `Equity ${moneyLevel(data.total_market_value)} · cash ${moneyLevel(data.cash)}`
    : unknownCashAccounts.length
      ? `Holdings ${moneyLevel(data.holdings_value)} · known cash subtotal ${moneyLevel(data.known_cash_subtotal)} · total equity unavailable because at least one account's USD cash is unknown`
      : `Holdings ${moneyLevel(data.holdings_value)} · cash ${moneyLevel(data.cash)} · total value unavailable because one or more holding prices are missing`;
  $("#pfAccountsNote").textContent = unknownCashAccounts.length
    ? `${unknownCashAccounts.length} account(s) have unknown USD cash; totals and cash percentages are partial/unavailable.`
    : `${accounts.length} account(s) included in the combined holdings.`;
  $("#pfAccounts tbody").innerHTML = globalThis.argusRenderPortfolioAccounts(accounts, {
    esc, moneyLevel,
  });

  const pnl = data.account?.unrealized_pnl ?? null;
  const change = moneyChange(pnl, true);
  const allPriced = (data.positions || []).length > 0 && (data.positions || []).every((p) => p.price != null);
  let pnlPct = null;
  if (cashKnown && allPriced && pnl != null && data.total_cost != null) {
    const basis = Number(data.total_cost) - Number(data.cash || 0);
    if (basis) {
      const raw = (pnl / basis) * 100;
      pnlPct = pctChange(raw, Math.abs(raw) > 0 && Math.abs(raw) < 1 ? 2 : 1);
    }
  }
  const pnlValue = change ? esc(change.text) : "—";
  const pnlClass = change && change.dir !== "flat" ? `ar-${change.dir}` : "";
  const pnlDelta = !change
    ? `<span class="ar-subtle">—</span>`
    : pnlPct
      ? `${deltaHtml(pnlPct)} <span class="ar-subtle">vs cost</span>`
      : deltaHtml({ text: "vs cost basis", dir: change.dir, arrow: change.arrow });

  $("#pfCards").innerHTML = `
    <article class="ar-stat ar-span-3"><span class="ar-stat__label">Total value</span><span class="ar-stat__value">${esc(moneyLevel(data.total_market_value, true))}</span><span class="ar-stat__delta"><span class="ar-subtle">Invested + cash</span></span></article>
    <article class="ar-stat ar-span-3"><span class="ar-stat__label">Cash</span><span class="ar-stat__value">${esc(moneyLevel(data.cash, true))}</span><span class="ar-stat__delta"><span class="ar-subtle">${esc(pctLevel(data.cash_pct, 1))} · approved target ${data.cash_target_pct != null ? esc(pctLevel(data.cash_target_pct, 1)) : "none"}</span></span></article>
    <article class="ar-stat ar-span-3"><span class="ar-stat__label">Unrealized P&amp;L</span><span class="ar-stat__value ${pnlClass}">${pnlValue}</span><span class="ar-stat__delta">${pnlDelta}</span></article>
    <article class="ar-stat ar-span-3"><span class="ar-stat__label">Positions</span><span class="ar-stat__value">${data.positions.length}</span><span class="ar-stat__delta"><span class="ar-subtle">Currency ${esc(data.currency || "USD")}</span></span></article>
  `;

  renderPortfolioHoldings(data);

  const sleeveNote = $("#pfSleeve");
  if (sleeveNote) {
    const core = (data.sleeves || {}).core_etf || {};
    const swing = (data.sleeves || {}).swing || {};
    const unknown = (data.sleeves || {}).unclassified || {};
    const corePnl = moneyChange(core.unrealized_pnl);
    const swingPnl = moneyChange(swing.unrealized_pnl);
    sleeveNote.innerHTML = state.portfolioAccountId === "all"
      ? `Instrument type grouping only; long-term / swing roles are proposed separately. ETFs ${esc(pctLevel(core.weight_pct, 1))} · ${corePnl ? deltaHtml(corePnl) : "—"} · Stocks and cash ${esc(pctLevel(swing.weight_pct, 1))} · ${swingPnl ? deltaHtml(swingPnl) : "—"} · Unclassified ${esc(pctLevel(unknown.weight_pct, 1))}`
      : "Single-account holding details; consolidated allocation figures are hidden while an account is selected.";
  }

  const riskNote = $("#pfRiskNote");
  if (riskNote) riskNote.textContent = `AI look-through warning cap: ${pctLevel(data.ai_sleeve_cap_pct, 0)}. This is a portfolio risk summary and is separate from sector and instrument classifications.`;
  renderWeightsChart(data);
}

function renderPortfolioHoldings(data) {
  const selected = state.portfolioAccountId || "all";
  const account = (data.accounts || []).find((item) => item.account_id === selected);
  $("#pfHoldingsNote").textContent = selected === "all"
    ? "Combined holdings across accounts. Select an account to inspect its quantity, average cost, sellable shares and P&L."
    : `${account?.label || "Selected account"}: quantities, acquisition costs and sellable shares are account-specific; weights are not consolidated.`;
  $("#pfTable tbody").innerHTML = globalThis.argusRenderPortfolioHoldings(data, selected, {
    esc, qty, price, moneyLevel, moneyChange, pctChange, deltaHtml, pctLevel,
  });
}

$("#pfAccountFilter").addEventListener("change", (event) => {
  state.portfolioAccountId = event.target.value || "all";
  if (state.portfolio) renderPortfolioHoldings(state.portfolio);
});

function renderWeightsChart(data) {
  const labels = [];
  const current = [];
  const target = [];
  const tickers = [...new Set([
    ...data.positions.map((p) => p.ticker),
    ...Object.keys(data.targets || {}).filter((k) => k !== "cash"),
  ])];
  tickers.forEach((t) => {
    const row = data.weights.find((w) => w.ticker === t) || {};
    labels.push(t);
    current.push(row.weight_pct ?? null);
    target.push(data.targets?.[t] ?? null);
  });
  labels.push("cash");
  current.push(data.cash_pct ?? null);
  target.push(data.cash_target_pct ?? null);

  const ctx = $("#weightsChart");
  const hasTargets = Object.keys(data.targets || {}).length > 0;
  if (state.chart) state.chart.destroy();
  const axis = cssVar("--argus-chart-axis");
  const grid = cssVar("--argus-chart-grid");
  const text = cssVar("--argus-text");
  const font = cssVar("--argus-font-sans");
  state.chart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        { label: "Current %", data: current, backgroundColor: cssVar("--argus-chart-1"), borderWidth: 0 },
        ...(hasTargets ? [{ label: "Approved target %", data: target, backgroundColor: cssVar("--argus-chart-2"), borderWidth: 0 }] : []),
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      font: { family: font },
      scales: {
        x: { ticks: { color: axis, font: { family: font } }, grid: { color: grid } },
        y: {
          ticks: { color: axis, font: { family: font } },
          grid: { color: grid },
          title: { display: true, text: "% of NAV", color: axis, font: { family: font } },
        },
      },
      plugins: { legend: { labels: { color: text, font: { family: font } } } },
    },
  });
}

/* ---------- read-only broker account import ---------- */
function currentBroker() { return $("#brokerType").value; }
function selectedLegacyReplacement() { return document.querySelector('input[name="legacyChoice"]:checked')?.value === "true"; }
function resetBrokerPreview(message = "Select an authorized account, then fetch a preview.") {
  state.tigerPreviewRequestId += 1;
  state.tigerPreview = null;
  $("#brokerPreviewBody").textContent = message;
  ["legacyChoiceWrap", "brokerReplaceWrap", "brokerStockOnlyWrap", "brokerEmptyWrap"].forEach((id) => $("#" + id).classList.add("hidden"));
  document.querySelectorAll('input[name="legacyChoice"]').forEach((el) => { el.checked = false; });
  ["brokerReplace", "brokerStockOnly", "brokerEmpty"].forEach((id) => { $("#" + id).checked = false; });
  $("#brokerApply").disabled = true;
}

function syncBrokerApply() {
  const preview = state.tigerPreview;
  const empty = Boolean(preview && (preview.positions || []).length === 0);
  const needsLegacyChoice = Boolean(preview?.replace_legacy_choice_required);
  $("#legacyChoiceWrap").classList.toggle("hidden", !preview?.can_apply || !needsLegacyChoice);
  $("#brokerReplaceWrap").classList.toggle("hidden", !preview?.can_apply || !preview?.replaces_existing_account);
  $("#brokerStockOnlyWrap").classList.toggle("hidden", !preview?.can_apply);
  $("#brokerEmptyWrap").classList.toggle("hidden", !preview?.can_apply || !empty);
  $("#brokerApply").disabled = !preview?.can_apply
    || (preview.replaces_existing_account && !$("#brokerReplace").checked)
    || (needsLegacyChoice && !document.querySelector('input[name="legacyChoice"]:checked'))
    || !$("#brokerStockOnly").checked
    || (empty && !$("#brokerEmpty").checked);
}

function renderBrokerPreview(preview) {
  const body = $("#brokerPreviewBody");
  $("#brokerAccount").dataset.legacyChoiceRequired = preview.replace_legacy_choice_required ? "true" : "false";
  const rows = (preview.positions || []).map((p) => `<tr>
    <td class="ar-ticker">${esc(p.ticker)}</td><td class="ar-num">${qty(p.quantity)}</td>
    <td class="ar-num">${price(p.average_price)}</td></tr>`).join("");
  const rejected = (preview.rejected || []).map((item) => `<li>${esc(item.market ? `${item.ticker || `Row ${item.row || "?"}`} [${item.market}]` : (item.ticker || `Row ${item.row || "?"}`))}: ${esc(item.reason)}</li>`).join("");
  const excluded = (preview.excluded || []).map((item) => `<li>${esc(item.market ? `${item.ticker || `Row ${item.row || "?"}`} [${item.market}]` : (item.ticker || `Row ${item.row || "?"}`))}: ${esc(item.reason)}</li>`).join("");
  const issues = (preview.issues || []).map((issue) => `<li>${esc(issue)}</li>`).join("");
  const warnings = (preview.warnings || []).map((warning) => `<li>${esc(warning)}</li>`).join("");
  const cash = preview.cash_known === false || preview.cash == null ? "Unknown USD cash" : moneyLevel(preview.cash);
  body.innerHTML = `<p><strong>${esc(preview.account_label || "Selected account")}</strong> · Snapshot ${esc(preview.fetched_at || "time unavailable")} · ${preview.position_count ?? (preview.positions || []).length} rows · ${preview.currency ? `currency ${esc(preview.currency)}` : "currency unavailable"} · cash ${esc(cash)}</p>
    ${rows ? `<div class="ar-table-wrap"><table class="ar-table"><thead><tr><th>Ticker</th><th>Quantity</th><th>Average cost</th></tr></thead><tbody>${rows}</tbody></table></div>` : "<p>No supported positions in snapshot.</p>"}
    ${warnings.length || excluded.length ? `<div class="ar-callout ar-callout--warn"><strong>Stock-only import scope</strong><ul>${warnings}${excluded}</ul></div>` : ""}
    ${issues.length || rejected.length ? `<div class="ar-callout ar-callout--warn"><strong>Cannot apply this snapshot</strong><ul>${issues}${rejected}</ul></div>` : "<p class=\"ar-subtle\">All stock rows are supported.</p>"}`;
  const replace = $("#brokerReplaceWrap");
  const replaceText = replace.querySelector("span");
  replaceText.textContent = preview.replaces_existing_legacy
    ? "I reviewed this snapshot and want to replace the legacy Argus book with this broker account."
    : `I reviewed this snapshot and want to update ${preview.account_label || "only this account"}.`;
  $("#legacyChoiceWrap").classList.toggle("hidden", !preview.can_apply || !preview.replace_legacy_choice_required);
  $("#brokerReplace").checked = false;
  $("#brokerStockOnly").checked = false;
  $("#brokerEmpty").checked = false;
  syncBrokerApply();
}

async function loadBrokerAccounts() {
  const broker = currentBroker();
  const select = $("#brokerAccount");
  select.innerHTML = '<option value="">Loading authorized accounts…</option>';
  try {
    const data = await api(`/api/${broker}/accounts`);
    select.innerHTML = '<option value="">Select an account…</option>' + (data.accounts || []).map((a) =>
      `<option value="${esc(a.account_key)}">${esc(a.label)} · ${esc(a.account_type)}${a.status ? ` · ${esc(a.status)}` : ""}</option>`).join("");
    if (!data.accounts?.length) select.innerHTML = '<option value="">No authorized accounts</option>';
    select.dataset.hasLegacy = data.has_legacy_account ? "true" : "false";
    select.dataset.legacyChoiceRequired = data.replace_legacy_choice_required ? "true" : "false";
    $("#legacyChoiceWrap").classList.toggle("hidden", !data.replace_legacy_choice_required);
  } catch (e) {
    select.innerHTML = '<option value="">Could not load accounts</option>';
    $("#brokerPreviewBody").textContent = e.message;
  }
}

$("#brokerImportOpen").addEventListener("click", async () => {
  resetBrokerPreview("Load an authorized broker account to preview positions.");
  $("#brokerImportModal").showModal();
  await loadBrokerAccounts();
});
$("#brokerCancel").addEventListener("click", () => {
  resetBrokerPreview();
  $("#brokerImportModal").close();
});
$("#brokerType").addEventListener("change", () => { resetBrokerPreview(); loadBrokerAccounts(); });
$("#brokerAccount").addEventListener("change", () => {
  resetBrokerPreview("Account changed. Fetch a new preview before applying.");
  $("#legacyChoiceWrap").classList.toggle("hidden", $("#brokerAccount").dataset.hasLegacy !== "true");
});
document.querySelectorAll('input[name="legacyChoice"]').forEach((el) => el.addEventListener("change", () => {
  if (state.tigerPreview) {
    const chosen = el.value;
    resetBrokerPreview("Legacy account choice changed. Fetch a new preview before applying.");
    $("#legacyChoiceWrap").classList.toggle("hidden", $("#brokerAccount").dataset.legacyChoiceRequired !== "true");
    el.checked = true;
    el.value = chosen;
  }
}));
["brokerReplace", "brokerStockOnly", "brokerEmpty"].forEach((id) => $("#" + id).addEventListener("change", syncBrokerApply));
$("#brokerFetch").addEventListener("click", async () => {
  const account_key = $("#brokerAccount").value;
  const broker = currentBroker();
  if (!account_key) { showToast("Select an authorized account first.", "warn"); return; }
  const requestId = ++state.tigerPreviewRequestId;
  state.tigerPreview = null;
  $("#brokerPreviewBody").textContent = "Fetching read-only positions and cash…";
  $("#brokerApply").disabled = true;
  try {
    const legacyChoice = document.querySelector('input[name="legacyChoice"]:checked');
    const replace_legacy = legacyChoice ? selectedLegacyReplacement() : null;
    const preview = await api(`/api/${broker}/preview`, { method: "POST", body: JSON.stringify({ account_key, replace_legacy }) });
    if (!globalThis.argusBrokerPreviewIsCurrent(requestId, state.tigerPreviewRequestId, account_key,
      $("#brokerAccount").value, preview.account_key, $("#brokerImportModal").open)) return;
    state.tigerPreview = preview;
    renderBrokerPreview(preview);
  } catch (e) {
    if (!globalThis.argusBrokerPreviewIsCurrent(requestId, state.tigerPreviewRequestId, account_key,
      $("#brokerAccount").value, account_key, $("#brokerImportModal").open)) return;
    $("#brokerPreviewBody").textContent = e.message;
    showToast(e.message, "danger");
  }
});
$("#brokerApply").addEventListener("click", async () => {
  const preview = state.tigerPreview;
  const broker = currentBroker();
  if (!preview || !$("#brokerStockOnly").checked) return;
  if (preview.replaces_existing_account && !$("#brokerReplace").checked) return;
  if ((preview.positions || []).length === 0 && !$("#brokerEmpty").checked) return;
  const button = $("#brokerApply");
  button.disabled = true;
  try {
    const result = await api(`/api/${broker}/apply`, { method: "POST", body: JSON.stringify({
      account_key: $("#brokerAccount").value, preview_id: preview.preview_id, confirm: true,
      confirm_empty: $("#brokerEmpty").checked, confirm_stock_only: true,
      replace_legacy: selectedLegacyReplacement(),
    }) });
    $("#brokerImportModal").close();
    resetBrokerPreview();
    showToast(result.backup ? `Account snapshot applied. Backup saved as ${result.backup}.` : "Broker account snapshot applied.", "ok");
    await loadPortfolio();
  } catch (e) {
    showToast(e.message, "danger");
    syncBrokerApply();
  }
});

/* ---------- watchlist ---------- */
async function loadWatchlist() {
  const [data, proposal] = await Promise.all([
    api("/api/watchlist"),
    api("/api/watchlist/proposal"),
  ]);
  state.watchlist = data.items || [];
  state.refreshTickers = state.refreshTickers.filter((ticker) => state.watchlist.some((item) => item.ticker === ticker && item.earnings_stale === true));
  state.watchlistProposal = proposal;
  const tb = $("#wlTable tbody");
  tb.innerHTML = state.watchlist.map((it) => {
    const eps = it.earnings_data || {};
    const lastEvent = eps.last || {};
    const nextEvent = eps.next || {};
    const calendarMeta = eps.error
      ? `Calendar error: ${esc(eps.error)}`
      : eps.fetched_at
        ? `Calendar checked ${esc(formatDateTime(eps.fetched_at))}${Number.isFinite(Number(eps.source_age_days)) ? ` · ${esc(eps.source_age_days)}d old` : ""}`
        : eps.as_of
          ? `Calendar as of ${esc(eps.as_of)} · age unknown`
          : "Calendar coverage unavailable";
    const last = it.earnings_last_datetime || (parseKnownDate(lastEvent.datetime) ? lastEvent.datetime : null);
    const lastDate = last || lastEvent.date || eps.last_date;
    const next = it.earnings_next_datetime || (parseKnownDate(nextEvent.datetime) ? nextEvent.datetime : null);
    const nextDateValue = next || nextEvent.date || eps.next_date;
    const earningsEps = earningsEpsValues(lastEvent, nextEvent, eps);
    const earningsData = [
      earningsEps.lastReported != null ? `Reported EPS ${esc(earningsEps.lastReported)}` : "",
      earningsEps.lastEstimated != null ? `Estimate ${esc(earningsEps.lastEstimated)}` : "",
      earningsEps.lastSurprise != null ? `Surprise ${esc(earningsEps.lastSurprise)}%` : "",
    ].filter(Boolean).join(" · ") || "EPS unavailable";
    const nextEstimate = earningsEps.nextEstimated;
    const nextDate = parseEarningsDate(nextDateValue);
    const now = new Date();
    const soon = nextDate && dayDistance(now, nextDate) >= 0 && dayDistance(now, nextDate) <= 5;
    const stale = it.earnings_stale === true;
    const status = stale ? "Earnings reported · rerun needed" : it.earnings_status === "updated" ? "Updated after earnings" : it.earnings_status === "missing" ? "No report" : it.earnings_status === "unknown" ? "Freshness unknown" : "—";
    return `<tr class="${soon ? "ar-earnings-soon" : ""} ${stale ? "ar-earnings-stale" : ""}">
      <td class="ar-ticker">${esc(it.ticker)}</td>
      <td>${esc(it.origin || "candidate")}</td>
      <td>${esc(it.sector || "")}</td>
      <td>${esc(it.instrument_type || "Unknown")}</td>
      <td>${esc(it.sleeve === "core_etf" ? "ETF" : it.sleeve === "swing" ? "Stock / cash" : "Unclassified")}</td>
      <td>${lastDate ? `${esc(formatEarningsDate(lastDate))}<br/><span class="ar-subtle">${earningsData}</span>` : `<span class="ar-subtle">No completed date</span>`}<br/><span class="ar-subtle">${calendarMeta}</span></td>
      <td>${nextDateValue ? `<span>${esc(formatEarningsDate(nextDateValue))}</span>${nextEstimate != null ? `<br/><span class="ar-subtle">Est. EPS ${esc(nextEstimate)}</span>` : ""}${soon ? `<br/><span class="ar-earnings-label">Within 5 days</span>` : ""}` : `<span class="ar-subtle">No upcoming date</span>`}</td>
      <td>${it.report_generated_at ? esc(formatDateTime(it.report_generated_at)) : it.report_generation_unknown ? "Time unknown" : "No report"}<br/><span class="${stale ? "ar-earnings-label" : "ar-subtle"}">${esc(status)}</span></td>
      <td>${stale && it.instrument_type !== "ETF" ? `<input type="checkbox" data-refresh-ticker="${esc(it.ticker)}" aria-label="Select ${esc(it.ticker)} to analyze after earnings" ${state.refreshTickers.includes(it.ticker) ? "checked" : ""}/>` : "—"}</td>
      <td class="ar-actions">${(it.origins || ["candidate"]).includes("candidate") ? `<button type="button" class="ar-btn ar-btn--sm ar-btn--danger" data-rm="${esc(it.ticker)}" aria-label="Remove ${esc(it.ticker)} candidate" data-tooltip="Remove saved candidate ${esc(it.ticker)}">${iconSvg("trash-2")}<span class="ar-btn__label">Remove</span></button>` : ""}</td>
    </tr>`;
  }).join("") || `<tr><td colspan="10" class="ar-subtle">No holdings or candidates to monitor</td></tr>`;
  syncRefreshButton();
  renderWatchlistProposal();
}

function parseKnownDate(value) {
  if (typeof value !== "string" || !/(Z|[+-]\d\d:\d\d)$/i.test(value)) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function parseEarningsDate(value) {
  const known = parseKnownDate(value);
  if (known) return known;
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const [year, month, day] = value.split("-").map(Number);
  const parsed = new Date(year, month - 1, day);
  return parsed.getFullYear() === year && parsed.getMonth() === month - 1 && parsed.getDate() === day ? parsed : null;
}

function earningsEpsValues(lastEvent, nextEvent, earnings) {
  return {
    lastReported: lastEvent.reported_eps ?? earnings.reported_eps,
    lastEstimated: lastEvent.estimated_eps,
    lastSurprise: lastEvent.surprise_percent ?? earnings.surprise_percent,
    nextEstimated: nextEvent.estimated_eps,
  };
}

function formatDateTime(value) {
  const date = parseKnownDate(value);
  return date ? date.toLocaleString() : "Time unknown";
}

function formatEarningsDate(value) {
  const parsed = parseKnownDate(value);
  if (parsed) return parsed.toLocaleString();
  const date = parseEarningsDate(value);
  return date ? `${date.toLocaleDateString()} (time unknown)` : "Time unknown";
}

function dayDistance(from, to) {
  const start = new Date(from.getFullYear(), from.getMonth(), from.getDate());
  const end = new Date(to.getFullYear(), to.getMonth(), to.getDate());
  return Math.round((end - start) / 86400000);
}

function syncRefreshButton() {
  const button = $("#wlRefreshSelected");
  if (button) {
    button.disabled = !state.refreshTickers.length;
    button.textContent = state.refreshTickers.length
      ? `Analyze ${state.refreshTickers.length} selected + review`
      : "Analyze selected + review";
  }
}

$("#wlTable").addEventListener("change", (event) => {
  const input = event.target.closest("[data-refresh-ticker]");
  if (!input) return;
  const ticker = input.dataset.refreshTicker;
  state.refreshTickers = input.checked
    ? [...new Set([...state.refreshTickers, ticker])]
    : state.refreshTickers.filter((item) => item !== ticker);
  syncRefreshButton();
});

function selectedScoutSectors() {
  return $$("#scoutSectors input[data-scout-sector]:checked").map((el) => el.dataset.scoutSector);
}

function syncScoutSectors() {
  const selected = selectedScoutSectors();
  const atLimit = selected.length >= 8;
  $$("#scoutSectors input[data-scout-sector]").forEach((el) => {
    el.disabled = atLimit && !el.checked;
  });
  $("#scoutSectorCount").textContent = `${selected.length} of 8 selected`;
  const none = selected.length === 0;
  $("#btnScreen").disabled = none;
  $("#btnScout").disabled = none;
}

$("#scoutSectors").addEventListener("change", syncScoutSectors);
syncScoutSectors();

function renderWatchlistProposal() {
  const view = state.watchlistProposal || {};
  const proposal = view.proposal;
  const coverage = view.coverage || {};
  const changes = view.review_changes || [];
  const stale = proposal && !view.applicable;
  const coverageStatus = coverage.ranking_status === "partial"
    ? ` · partial ranking ${coverage.ranking_count ?? "?"}/${coverage.ranking_expected_count ?? "?"} (${(coverage.ranking_missing_tickers || []).length} omitted)`
    : coverage.ranking_status === "complete" ? ` · complete ranking (${coverage.ranking_count ?? "?"})` : "";
  const missingCount = (coverage.ranking_missing_tickers || []).length;
  const validationWarnings = (coverage.ranking_warnings || [])
    .filter((warning) => !String(warning).startsWith("missing from ranking:")
      && !String(warning).startsWith("partial ranking:"))
    .slice(0, 3);
  const coverageParts = [];
  if (coverage.ranking_status === "partial" && missingCount) {
    coverageParts.push(`${missingCount} expected names were omitted; they have no inferred rank or action. Review returned candidates only.`);
  } else if (coverage.ranking_status === "partial") {
    coverageParts.push("All expected names were returned, but validation conflicts make one or more rows non-actionable.");
  }
  if (validationWarnings.length) coverageParts.push(`Validation warnings: ${validationWarnings.join("; ")}`);
  const coverageReason = coverageParts.join(" ");
  $("#wlProposalStatus").textContent = proposal ? `${view.date || proposal.date || "Proposal"} · ${stale ? "stale" : "fresh"}${coverageStatus}` : "No proposal";
  $("#wlProposalReason").textContent = proposal
    ? [coverageReason, view.reason || "Choose changes from this proposal. Applying any selection uses this proposal once; run the scout again to make another change."].filter(Boolean).join(" ")
    : (view.reason || "No scout proposal is available.");
  const tbody = $("#wlProposalTable tbody");
  tbody.innerHTML = changes.map((change) => {
    const allowed = view.applicable && !change.blocked_reason;
    return `<tr>
      <td><input type="checkbox" data-proposal-action="${esc(change.action)}" data-proposal-ticker="${esc(change.ticker)}" aria-label="Apply ${esc(change.action)} ${esc(change.ticker)}" ${allowed ? "" : "disabled"} /></td>
      <td>${esc(change.action)}</td>
      <td class="ar-ticker">${esc(change.ticker)}</td>
      <td>${esc(change.sector || "Unknown")}</td>
      <td>${esc(change.type || "Unknown")}</td>
      <td>${esc(change.blocked_reason || change.reason || "")}</td>
    </tr>`;
  }).join("") || `<tr><td colspan="6" class="ar-subtle">${proposal ? "This proposal has no add or drop actions." : "Run the weekly scout to create a proposal."}</td></tr>`;
  $("#wlProposalApply").disabled = !view.applicable || !changes.some((row) => !row.blocked_reason);
}

$("#wlProposalApply").addEventListener("click", async () => {
  const view = state.watchlistProposal || {};
  if (!view.applicable || !view.proposal) return;
  const selected = $$("#wlProposalTable input[data-proposal-action]:checked");
  const add = selected.filter((el) => el.dataset.proposalAction === "add").map((el) => el.dataset.proposalTicker);
  const drop = selected.filter((el) => el.dataset.proposalAction === "drop").map((el) => el.dataset.proposalTicker);
  if (!add.length && !drop.length) return showToast("Select at least one proposal change", "warning");
  try {
    await api("/api/watchlist/proposal/apply", { method: "POST", body: JSON.stringify({
      date: view.date,
      base_watchlist_version: view.base_watchlist_version,
      proposal_sha256: view.proposal_sha256,
      add,
      drop,
      confirm: true,
    }) });
    showToast(`Applied ${add.length} add(s) and ${drop.length} removal(s)`, "success");
    await loadWatchlist();
  } catch (e) {
    showToast(e.message, "danger");
    await loadWatchlist();
  }
});

$("#wlUndo").addEventListener("click", async () => {
  const err = $("#wlErr");
  err.classList.add("hidden");
  try {
    await api("/api/watchlist/undo", { method: "POST", body: "{}" });
    await loadWatchlist();
  } catch (e) {
    $("#wlErrText").textContent = e.message;
    err.classList.remove("hidden");
  }
});

$("#wlAdd").addEventListener("click", async () => {
  const err = $("#wlErr");
  err.classList.add("hidden");
  $("#wlTicker").removeAttribute("aria-invalid");
  try {
    await api("/api/watchlist", {
      method: "POST",
      body: JSON.stringify({
        ticker: $("#wlTicker").value,
        sector: $("#wlSector").value || "Other",
        type: $("#wlType").value,
      }),
    });
    $("#wlTicker").value = "";
    await loadWatchlist();
  } catch (e) {
    $("#wlErrText").textContent = e.message;
    err.classList.remove("hidden");
    $("#wlTicker").setAttribute("aria-invalid", "true");
  }
});

$("#wlTable").addEventListener("click", (e) => {
  const btn = e.target.closest("[data-rm]");
  if (!btn) return;
  state.pendingRun = null;
  state.pendingTheme = null;
  state.pendingRemove = btn.getAttribute("data-rm");
  $("#confirmText").textContent = `Remove ${state.pendingRemove} from the watchlist?`;
  openConfirm();
});

/* ---------- reports ---------- */
async function loadReports() {
  const data = await api("/api/reports");
  state.reports = data.reports || [];
  state.latestByTicker = data.latest_by_ticker || {};
  const tickers = [...new Set(state.reports.map((r) => r.ticker))].sort();
  const sel = $("#repFilter");
  const cur = sel.value;
  sel.innerHTML = `<option value="">All tickers</option>` + tickers.map((t) => {
    const lat = state.latestByTicker[t];
    const r = lat?.rating ? ` (${lat.rating})` : "";
    return `<option value="${esc(t)}">${esc(t + r)}</option>`;
  }).join("");
  sel.value = cur;
  renderReportList();
}

function renderReportList() {
  const filter = $("#repFilter").value;
  const items = state.reports.filter((r) => !filter || r.ticker === filter);
  $("#repList").innerHTML = items.map((r) => {
    const latest = state.latestByTicker[r.ticker]?.id === r.id;
    const on = state.selectedReport === r.id;
    return `<div class="ar-list__item" role="option" aria-selected="${on ? "true" : "false"}" data-id="${esc(r.id)}">
      <div>
        <div><span class="ar-ticker">${esc(r.ticker)}</span>
          ${r.rating ? ratingMarkup(r.rating) : ""}
          ${latest ? `<span class="ar-badge ar-badge--neutral">● Latest</span>` : ""}
        </div>
        <div class="ar-list__meta">${esc(r.analysis_date || r.ymd || "")} · ${esc(r.generated || r.stamp || r.id)}</div>
      </div>
    </div>`;
  }).join("") || `<div class="ar-muted">No reports yet</div>`;
}

$("#repFilter").addEventListener("change", renderReportList);
$("#repList").addEventListener("click", async (e) => {
  const item = e.target.closest("[data-id]");
  if (!item) return;
  state.selectedReport = item.dataset.id;
  const requestedId = state.selectedReport;
  state.stockReport = null;
  $("#repExportPdf").disabled = true;
  renderReportList();
  try {
    const data = await api(`/api/reports/${encodeURIComponent(requestedId)}`);
    if (state.selectedReport !== requestedId) return;
    state.stockReport = data;
    $("#repExportPdf").disabled = !data.markdown;
    $("#repTitle").textContent = data.meta.ticker;
    $("#repMeta").innerHTML = `${data.meta.rating ? `${ratingMarkup(data.meta.rating)} · ` : ""}
      analysis ${esc(data.meta.analysis_date || "—")} · generated ${esc(data.meta.generated || "—")}`;
    renderMarkdown($("#repMd"), data.markdown || "");
  } catch (err) {
    if (state.selectedReport === requestedId) showToast(err.message, "danger");
  }
});

/* ---------- fund manager ---------- */
async function loadFund(path) {
  const data = path
    ? await api(`/api/fund-manager/at?path=${encodeURIComponent(path)}`)
    : await api("/api/fund-manager");
  state.fund = data;
  if (!path) {
    $("#fmDate").innerHTML = (data.history || []).map((h) => {
      const id = h.path || h.date;
      const label = `${id}${h.kind === "snapshot" ? " snapshot" : ""}`;
      return `<option value="${esc(id)}" ${id === (data.path || data.date) ? "selected" : ""}>${esc(label)}</option>`;
    }).join("") || `<option value="">No runs</option>`;
    $("#fmHistory").innerHTML = (data.history || []).map((h) => `
      <div class="ar-list__item" data-path="${esc(h.path || h.date)}">
        <div><strong>${esc(h.path || h.date)}</strong>
      <div class="ar-list__meta">${esc([h.kind, h.review_outcome === "incomplete" && "review incomplete", h.review_outcome === "snapshot" && "quantitative snapshot", h.has_json && "json", h.has_stats && "stats"].filter(Boolean).join(" · "))}</div>
        </div>
      </div>`).join("") || `<div class="ar-muted">No history</div>`;
  }
  $("#fmSub").textContent = data.path ? `Plan ${data.path}` : "No fund manager output yet";
  const trades = data.validated_trades || data.trades || [];
  $("#fmTrades tbody").innerHTML = globalThis.argusRenderFundTrades(trades, {
    esc, qty, price, moneyLevel, ratingMarkup, actionClass,
  });

  const d = data.decision || {};
  $("#fmDecisionContext").innerHTML = globalThis.argusRenderFundContext(
    data.decision_context,
    data.candidate_coverage,
    data.position_results,
    { esc },
  );
  const summary = d.decision_summary || d.diagnosis || "";
  const warns = (data.warnings || []).map((w) => `<li>${esc(w)}</li>`).join("");
  const cash = d.cash_decision || data.cash_decision || {};
  const policySummary = globalThis.argusRenderTradePolicy(data.trade_policy, { moneyLevel });
  const incomplete = data.review_outcome === "incomplete";
  const snapshot = data.review_outcome === "snapshot" || data.kind === "snapshot";
  const rawOutputs = data.unvalidated_outputs || [];
  $("#fmUnvalidatedCard").classList.toggle("hidden", !(incomplete && rawOutputs.length));
  $("#fmIncompleteNotice").textContent = incomplete
    ? `This fund-manager review is incomplete${data.incomplete_stage ? ` at ${data.incomplete_stage}` : ""}. The content below is raw model output; no validated decision or trade list was produced.${data.incomplete_error ? ` ${data.incomplete_error}` : ""}`
    : "";
  $("#fmUnvalidatedOutput").innerHTML = renderUnvalidatedOutputs(rawOutputs, { esc, marked, DOMPurify });
  $("#fmSummary").innerHTML = `
    ${incomplete ? `<p class="ar-warning" role="alert">Review incomplete${data.incomplete_stage ? ` · ${esc(data.incomplete_stage)}` : ""}; do not rely on this run as a completed recommendation.</p>` : ""}
    ${snapshot ? `<p class="ar-subtle">Quantitative snapshot only; model review was not requested.</p>` : ""}
    <p><strong>${esc(d.headline || "—")}</strong></p>
    <p>${summary ? esc(summary) : "<span class='ar-muted'>No summary field</span>"}</p>
    <p class="ar-subtle">Confidence: ${esc(d.confidence ?? "—")}
      ${cash.target_cash_pct != null ? ` · target cash ${esc(cash.target_cash_pct)}%` : ""}
      ${data.ending_cash != null ? ` · post-trade cash ${moneyLevel(data.ending_cash)} (${esc(data.ending_cash_pct)}%)` : ""}
      ${data.fees_usd != null ? ` · estimated fees ${moneyLevel(data.fees_usd)}` : ""}
      ${policySummary ? ` · ${esc(policySummary)}` : ""}</p>
    ${warns ? `<ul>${warns}</ul>` : ""}`;
  renderMarkdown($("#fmMd"), data.markdown || "");
  $("#fmExportPdf").disabled = !data.markdown;
}

function renderUnvalidatedOutputs(outputs, { esc, marked, DOMPurify }) {
  return outputs.map((item) => {
    const rendered = item.content ? marked.parse(item.content) : "";
    const safe = DOMPurify.sanitize(rendered, { USE_PROFILES: { html: true } });
    return `<section class="ar-unvalidated-item"><h3 class="ar-h3">${esc(item.label || "Model response")} · ${esc(item.mode || "raw")}</h3><p class="ar-subtle">${esc(item.reason || "This output has not passed structured parsing and trade validation.")}</p><div class="ar-md">${safe}</div></section>`;
  }).join("");
}

async function exportReportPdf(kind) {
  const report = kind === "fund" ? state.fund : kind === "themes" ? state.themeReport : state.stockReport;
  if (!report || !report.markdown) return;
  const button = $({ fund: "#fmExportPdf", themes: "#themeExportPdf", stock: "#repExportPdf" }[kind]);
  button.disabled = true;
  try {
    const response = await fetch("/api/report-pdf", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind, markdown: report.markdown }),
    });
    if (!response.ok) throw new Error(`PDF export failed (${response.status})`);
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url;
    const ticker = String(report.meta?.ticker || "stock").replace(/[^a-z0-9._-]/gi, "_");
    link.download = kind === "fund" ? "fund-manager-report.pdf" : kind === "themes" ? "theme-scout-report.pdf" : `${ticker}-report.pdf`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (err) {
    showToast(err.message, "danger");
  } finally {
    const current = kind === "fund" ? state.fund : kind === "themes" ? state.themeReport : state.stockReport;
    button.disabled = !current?.markdown;
  }
}

$("#repExportPdf").addEventListener("click", () => exportReportPdf("stock"));
$("#fmExportPdf").addEventListener("click", () => exportReportPdf("fund"));
$("#themeExportPdf").addEventListener("click", () => exportReportPdf("themes"));

$("#fmDate").addEventListener("change", (e) => loadFund(e.target.value).catch((err) => showToast(err.message, "danger")));
$("#fmHistory").addEventListener("click", (e) => {
  const it = e.target.closest("[data-path]");
  if (!it) return;
  $("#fmDate").value = it.dataset.path;
  loadFund(it.dataset.path).catch((err) => showToast(err.message, "danger"));
});

/* ---------- runs ---------- */
async function loadRuns() {
  const [book, wl, runs, spend, settings] = await Promise.all([
    api("/api/portfolio"),
    api("/api/watchlist"),
    api("/api/runs"),
    api("/api/spend"),
api("/api/settings"),
  ]);
  const spendEl = $("#runSpend");
  if (spendEl && spend) {
    const spent = Number(spend.spent_usd || 0);
    const budget = Number(spend.budget_usd || 0);
    const unpriced = Number(spend.unpriced_runs || 0);
    const estimated = Number(spend.estimated_runs || 0);
    let extra = "";
    if (estimated) extra += ` · ${estimated} older runs priced from tokens (upper bound)`;
    if (unpriced) extra += ` · ${unpriced} runs with no tokens or price`;
    const text = spend.budget_enabled === false
      ? `This week ${moneyCost(spent)} spent · weekly check disabled${extra}`
      : `This week ${moneyCost(spent)} of ${moneyCost(budget)}${extra}`;
    spendEl.textContent = text;
    spendEl.classList.toggle("is-over", budget > 0 && spent >= budget);
  }
  state.bookTickers = (book.positions || []).map((p) => p.ticker);
  state.watchlist = wl.items || [];
  state.settings = settings;
  state.runs = runs.runs || [];
  renderRunTickerLists();
  renderRunList();
  renderRunComposer();
}

function runEligibility() {
  const holdings = [...new Set((state.bookTickers || []).map((ticker) => String(ticker).toUpperCase()))];
  const held = new Set(holdings);
  const candidates = [...new Set((state.watchlist || [])
    .map((row) => String(row.ticker || "").toUpperCase())
    .filter((ticker) => ticker && !held.has(ticker)))];
  const groups = {};
  holdings.forEach((ticker) => { groups[ticker] = "holding"; });
  candidates.forEach((ticker) => { groups[ticker] = "candidate"; });
  return { holdings, candidates, groups };
}

function renderRunSectorOptions() {
  $("#runSectors").innerHTML = RunDraft.sectors.map((sector) => `
    <label class="ar-run-chip"><input type="checkbox" data-run-sector value="${esc(sector.ticker)}" checked aria-describedby="runSectorHelp runSectorError" />
      <span><strong>${esc(sector.label)}</strong><small>${esc(sector.ticker)}</small></span></label>`).join("");
}

renderRunSectorOptions();

let runPreviewInFlight = false;

function renderRunTickerLists() {
  const eligible = runEligibility();
  const selected = new Set(state.runDraft.tickers || []);
  const renderGroup = (tickers, group) => tickers.length
    ? tickers.map((ticker) => {
      const row = (state.watchlist || []).find((item) => String(item.ticker || "").toUpperCase() === ticker) || {};
      const detail = group === "holding" ? "Current holding" : (row.sector || row.type || "Saved candidate");
      return `<label class="ar-run-chip"><input type="checkbox" data-run-ticker="${esc(ticker)}" data-run-source="${group}" value="${esc(ticker)}" ${selected.has(ticker) ? "checked" : ""} aria-describedby="runTickerHelp runTickerError" /><span><strong>${esc(ticker)}</strong><small>${esc(detail)}</small></span></label>`;
    }).join("")
    : `<p class="ar-subtle">No ${group === "holding" ? "saved holdings" : "non-held saved candidates"} available.</p>`;
  $("#runHoldingTickers").innerHTML = renderGroup(eligible.holdings, "holding");
  $("#runCandidateTickers").innerHTML = renderGroup(eligible.candidates, "candidate");
  renderRunTickerChanges(eligible.groups);
}

function renderRunTickerChanges(groups = runEligibility().groups) {
  const changes = RunDraft.selectedSourceChanges(state.runDraft, groups);
  const rows = [
    ...changes.missing.map((ticker) => ({ ticker, message: "No longer eligible" })),
    ...changes.changed.map((ticker) => ({ ticker, message: `Scope changed from ${state.runDraft.tickerSources[ticker]} to ${groups[ticker]}` })),
  ];
  const box = $("#runTickerChanges");
  box.hidden = rows.length === 0;
  box.innerHTML = rows.length ? `<p class="ar-subtle">Review these selected names before continuing. Uncheck and reselect a name to confirm its current scope, or remove it.</p>${rows.map(({ ticker, message }) => `<div class="ar-run-change"><span><strong>${esc(ticker)}</strong> · ${esc(message)}</span><button class="ar-btn ar-btn--sm" type="button" data-remove-run-ticker="${esc(ticker)}" aria-label="Remove ${esc(ticker)} from selected research">Remove</button></div>`).join("")}` : "";
}

function renderRunComposer() {
  const draft = state.runDraft;
  const meta = RunDraft.modes[draft.mode];
  const research = RunDraft.isResearch(draft.mode);
  const portfolio = RunDraft.isPortfolioReview(draft.mode);
  const discovery = RunDraft.isDiscovery(draft.mode);
  const snapshot = draft.mode === "snapshot";
  const selected = draft.tickers || [];
  const sectorLabels = RunDraft.sectors.filter((sector) => draft.sectors.includes(sector.ticker)).map((sector) => sector.ticker);
  const names = selected.length ? selected.join(", ") : "none selected";
  const summaryRefresh = snapshot ? "Prices and calculated portfolio statistics"
    : discovery ? `${draft.mode === "screen" ? "Screen" : "Scout screen"} across ${sectorLabels.length ? sectorLabels.join(", ") : "no sectors selected"}`
      : research ? `New ticker research: ${names}` : "No fresh ticker research";
  const summaryReuse = portfolio ? "Saved research for all holdings and watchlist candidates, with dates and evidence gaps"
    : snapshot ? "Saved holdings and watchlist context"
      : discovery ? "Selected discovery sectors; saved candidates remain unchanged"
        : "No portfolio review; existing reports are not included in a fund decision";

  $("#runPurpose").textContent = meta.title;
  $("#runPurposeCopy").textContent = meta.description;
  $("#runTickerScope").hidden = !research;
  $("#runPortfolioScope").hidden = !portfolio;
  $("#runSnapshotScope").hidden = !snapshot;
  $("#runSectorScope").hidden = !discovery;
  $("#runDateBlock").hidden = discovery;
  $("#runDiscoveryDate").hidden = !discovery;
  $("#runCustomDateWrap").hidden = draft.dateMode !== "custom";
  $("#runOptions").hidden = !(snapshot || portfolio);
  $("#runEconomicWrap").hidden = !(snapshot || portfolio);
  $("#runRiskNote").hidden = !portfolio;
  $("#runSinceWrap").hidden = !portfolio;
  $("#runTickerCount").textContent = `· ${selected.length} selected`;
  $("#runSectorCount").textContent = `· ${sectorLabels.length} of 8 selected`;
  $("#runSummaryRefresh").textContent = summaryRefresh;
  $("#runSummaryReuse").textContent = summaryReuse;
  $("#runSummaryOutput").textContent = meta.output;
  $("#runSummaryCost").textContent = meta.paid
    ? "Paid AI; current scope and estimate are shown in the review."
    : "No AI calls.";
  $("#runEconomicData").checked = Boolean(draft.includeEconomicData);
  $("#runSince").value = draft.since || "";
  $("#runDateInput").value = draft.date || "";
  $("input[name='runDateMode'][value='auto']").checked = draft.dateMode !== "custom";
  $("input[name='runDateMode'][value='custom']").checked = draft.dateMode === "custom";
  $$("#runSectors input[data-run-sector]").forEach((input) => { input.checked = draft.sectors.includes(input.value); });
  $$("#runTickerScope input[data-run-ticker]").forEach((input) => { input.checked = selected.includes(input.value); });
  $$("#runScenarios input[name='runScenario']").forEach((input) => { input.checked = input.value === draft.mode; });
  $("#runStart").disabled = runPreviewInFlight;
  $("#runStart").textContent = runPreviewInFlight ? "Preparing review…" : "Start run";
  renderRunTickerChanges();
}

function clearRunValidation() {
  state.runDraftErrors = [];
  const summary = $("#runErrors");
  summary.hidden = true;
  $("#runErrorList").replaceChildren();
  ["runTickerError", "runSectorError", "runDateError"].forEach((id) => {
    const input = $("#" + id);
    input.hidden = true;
    input.textContent = "";
  });
  $$("#runComposer [aria-invalid='true']").forEach((input) => input.removeAttribute("aria-invalid"));
}

function showRunValidation(errors, focus = true) {
  state.runDraftErrors = errors;
  const inline = { tickers: "runTickerError", sectors: "runSectorError", date: "runDateError" };
  const target = { tickers: "runTickerScope", sectors: "runSectorScope", date: "runDateInput" };
  errors.forEach((error) => {
    const inlineEl = $("#" + inline[error.field]);
    inlineEl.textContent = error.message;
    inlineEl.hidden = false;
    $("#" + target[error.field]).setAttribute("aria-invalid", "true");
  });
  const summary = $("#runErrors");
  $("#runErrorList").innerHTML = errors.map((error) => `<li><a href="#${target[error.field]}">${esc(error.message)}</a></li>`).join("");
  summary.hidden = errors.length === 0;
  if (focus && errors.length) summary.focus();
}

function renderRunResult(message, isError = false) {
  const result = $("#runResult");
  result.textContent = message;
  result.classList.toggle("ar-run-result--error", isError);
}

function updateRunDraft(patch) {
  state.runDraft = RunDraft.setOptions(state.runDraft, patch);
  clearRunValidation();
  renderRunComposer();
}

// The scenario cards only edit the local draft. They never preview or navigate.
$("#runScenarios").addEventListener("change", (event) => {
  const input = event.target.closest("input[name='runScenario']");
  if (!input) return;
  state.runDraft = RunDraft.setMode(state.runDraft, input.value);
  clearRunValidation();
  renderRunComposer();
  $("#runStatus").textContent = `New run set to ${RunDraft.modes[input.value].title}. Your selections are kept.`;
  renderRunResult("");
});

$("#runComposer").addEventListener("change", (event) => {
  const input = event.target;
  if (input.matches("input[data-run-ticker]")) {
    state.runDraft = RunDraft.toggleTicker(state.runDraft, input.value, input.dataset.runSource);
  } else if (input.matches("input[data-run-sector]")) {
    state.runDraft = RunDraft.toggleSector(state.runDraft, input.value);
  } else if (input.name === "runDateMode") {
    state.runDraft = RunDraft.setOptions(state.runDraft, { dateMode: input.value });
  } else if (input.id === "runDateInput") {
    state.runDraft = RunDraft.setOptions(state.runDraft, { date: input.value });
  } else if (input.id === "runEconomicData") {
    state.runDraft = RunDraft.setOptions(state.runDraft, { includeEconomicData: input.checked });
  } else if (input.id === "runSince") {
    state.runDraft = RunDraft.setOptions(state.runDraft, { since: input.value });
  } else return;
  clearRunValidation();
  renderRunComposer();
});

$("#runComposer").addEventListener("click", (event) => {
  const bulk = event.target.closest("[data-run-bulk]");
  if (bulk) {
    const eligible = runEligibility();
    if (bulk.dataset.runBulk === "clear") {
      state.runDraft = RunDraft.setTickerSelection(state.runDraft, [], {});
    } else if (bulk.dataset.runBulk === "all") {
      state.runDraft = RunDraft.setTickerSelection(state.runDraft, [...eligible.holdings, ...eligible.candidates], eligible.groups);
    } else {
      const names = bulk.dataset.runBulk === "holding" ? eligible.holdings : eligible.candidates;
      state.runDraft = RunDraft.mergeTickerSelection(state.runDraft, names, eligible.groups);
    }
  } else {
    const remove = event.target.closest("[data-remove-run-ticker]");
    if (!remove) return;
    state.runDraft = RunDraft.toggleTicker(state.runDraft, remove.dataset.removeRunTicker);
  }
  clearRunValidation();
  renderRunComposer();
});

async function handoffWatchlistRefresh() {
  const tickers = [...new Set((state.refreshTickers || []).map((ticker) => String(ticker).toUpperCase()))];
  if (!tickers.length) return;
  await setTab("runs");
  const eligible = runEligibility();
  state.runDraft = RunDraft.setMode(state.runDraft, "analyze-review");
  state.runDraft = RunDraft.setTickerSelection(state.runDraft, tickers, eligible.groups);
  state.refreshTickers = [];
  syncRefreshButton();
  clearRunValidation();
  renderRunComposer();
  $("#runStart").scrollIntoView({ behavior: "smooth", block: "center" });
  renderRunResult("Review the selected fresh research scope, then choose Start run to prepare it.");
}

$("#wlRefreshSelected").addEventListener("click", handoffWatchlistRefresh);
renderRunComposer();

function statusMarkup(status) {
  const s = status || "";
  if (s === "succeeded") return `<span class="ar-gain">✓ ${esc(s)}</span>`;
  if (s === "failed") return `<span class="ar-loss">✕ ${esc(s)}</span>`;
  return `<span class="ar-flat">● ${esc(s)}</span>`;
}

function renderRunList() {
  $("#runList").innerHTML = state.runs.map((r) => `
    <div class="ar-list__item" aria-selected="${state.selectedRun === r.id ? "true" : "false"}" data-run="${esc(r.id)}">
      <div>
        <div><span class="ar-mono">${esc(r.id)}</span> · ${statusMarkup(r.status)}</div>
        <div class="ar-list__meta">${esc(r.started_at || "")} · est ${esc(r.estimate_minutes ?? "?")} min · tickers ${esc(r.ticker_count ?? "?")}</div>
      </div>
    </div>`).join("") || `<div class="ar-muted">No runs yet</div>`;
}

$("#runList").addEventListener("click", (e) => {
  const it = e.target.closest("[data-run]");
  if (!it) return;
  selectRun(it.dataset.run);
});

function logLineClass(line) {
  const s = line.toLowerCase();
  if (/\b(error|exception|traceback)\b|status=failed/.test(s)) return "ar-log__line--error";
  if (/\bwarn/.test(s)) return "ar-log__line--warn";
  if (/status=succeeded|\bdone\b/.test(s)) return "ar-log__line--ok";
  return "ar-log__line--info";
}

function renderLog() {
  const el = $("#runLog");
  if (!state.logText) {
    el.innerHTML = `<div class="ar-log__line ar-log__line--info"><span class="ar-log__msg">Select a run to tail its log.</span></div>`;
    return;
  }
  el.innerHTML = state.logText.split(/\n/).map((line) => (
    `<div class="ar-log__line ${logLineClass(line)}"><span class="ar-log__msg">${esc(line) || " "}</span></div>`
  )).join("");
  el.scrollTop = el.scrollHeight;
}

async function selectRun(id) {
  state.selectedRun = id;
  state.logOffset = 0;
  state.logText = "";
  renderRunList();
  renderLog();
  if (state.logTimer) clearInterval(state.logTimer);
  await pollLog();
  state.logTimer = setInterval(pollLog, 1500);
}

async function pollLog() {
  if (!state.selectedRun) return;
  try {
    const data = await api(`/api/runs/${encodeURIComponent(state.selectedRun)}/log?from_byte=${state.logOffset}`);
    if (data.chunk) {
      state.logText += data.chunk;
      state.logOffset = data.offset;
      renderLog();
    }
    if (data.done && state.logTimer) {
      clearInterval(state.logTimer);
      state.logTimer = null;
      const runs = await api("/api/runs");
      state.runs = runs.runs || [];
      renderRunList();
    }
  } catch (_) { /* ignore transient */ }
}

function showRunSubmissionError(message) {
  const error = String(message || "The preview could not be prepared.");
  $("#runErrors").hidden = false;
  $("#runErrorList").innerHTML = `<li>${esc(error)} Review the draft and choose Start run to try again.</li>`;
  $("#runErrors").focus();
  renderRunResult(error, true);
}

function isCurrentRunDraftPreview(draftRevision, previewGeneration) {
  return state.tab === "runs"
    && state.runDraft.revision === draftRevision
    && runDraftPreviewGeneration === previewGeneration;
}

function discardStaleRunDraftPreview(message) {
  if (state.tab === "runs") renderRunResult(message);
  return false;
}

async function prepareRunPreview(body, { draftRevision, previewGeneration } = {}) {
  const preview = await api("/api/runs/manifest", { method: "POST", body: JSON.stringify(body) });
  if (draftRevision != null && !isCurrentRunDraftPreview(draftRevision, previewGeneration)) {
    return discardStaleRunDraftPreview("The draft or page changed while preparing the review. Return to Runs, check the scope, and choose Start run again.");
  }
  const manifest = preview.manifest || {};
  const stages = (manifest.stages || []).map((stage) => stage.name).join(" → ") || "No paid stages";
  const estimate = manifest.cost_estimate || {};
  const spending = manifest.spending_controls || {};
  const seats = new Map();
  const collectSeats = (value) => {
    if (!value || typeof value !== "object") return;
    if (Array.isArray(value)) return value.forEach(collectSeats);
    if (value.id && value.model && value.pipeline) seats.set(value.id, `${value.label}: ${value.model} (${value.max_tokens_setting || (value.max_tokens ? `${value.max_tokens} max tokens` : "runtime default")})`);
    Object.values(value).forEach(collectSeats);
  };
  collectSeats(manifest.stages);
  const all = (manifest.portfolio_review_context_tickers || []).join(", ") || "none";
  const paidScope = (manifest.fresh_analysis_tickers || []).join(", ") || "none";
  const reportSources = Object.entries(manifest.portfolio_report_inputs || {})
    .map(([ticker, source]) => `${ticker}: ${source.status}${source.analysis_date ? ` (${source.analysis_date})` : ""}`)
    .join(", ") || "none";
  const priceInventory = manifest.model_price_inventory || {};
  const rates = (priceInventory.rates || []).map((rate) =>
    `${rate.id}: $${rate.usd_per_mtok_in ?? "?"}/$${rate.usd_per_mtok_out ?? "?"} per million input/output tokens`).join("; ") || "No local rate rows";
  $("#confirmText").style.whiteSpace = "pre-line";
  $("#confirmText").textContent = [
    `Mode: ${manifest.mode}. Fresh ticker scope: ${paidScope}.`,
    `Portfolio review context: ${all}.`,
    `Existing report inputs: ${reportSources}.`,
    `Ordered stages: ${stages}.`,
    `Configured seats: ${[...seats.values()].join("; ") || "No model seats"}.`,
    `Local rate inventory (${priceInventory.pricing_note || "no pricing note"}): ${rates}.`,
    `Configured budget-planning placeholder: $${Number(estimate.amount_usd || 0).toFixed(2)} (not model-priced and not a provider price quote). Weekly allowance check: ${spending.weekly_budget_enabled === false ? "disabled" : `$${Number(spending.weekly_budget_usd || 0).toFixed(2)}`}; already spent: $${Number(spending.spent_usd || 0).toFixed(2)}. Check actual provider usage and cost after the call.`,
    estimate.note || "",
    manifest.model_price_inventory?.warning || "",
    `Outputs: ${manifest.outputs?.ticker_reports || ""} ${manifest.outputs?.portfolio_report || ""}`,
  ].filter(Boolean).join("\n");
  const pending = { ...body, manifest_sha256: preview.manifest_sha256 };
  state.pendingTheme = null;
  state.pendingRemove = null;
  state.pendingRun = Object.freeze(pending);
  state.runReviewFocusOnClose = draftRevision != null;
  openConfirm();
  renderRunResult("Review ready. Confirm the scope and consent before starting.");
  return true;
}

let themePreviewInFlight = false;

async function prepareThemePreview(mode, includeLlm, sectors, { draftRevision, previewGeneration } = {}) {
  if (themePreviewInFlight) return false;
  themePreviewInFlight = true;
  try {
    const selectedSectors = [...sectors];
    if (!selectedSectors.length || selectedSectors.length > 8) throw new Error("Choose between one and eight discovery sectors.");
    const body = { mode, include_llm: Boolean(includeLlm), sectors: selectedSectors, single_call: Boolean(includeLlm), confirm: false };
    const reviewed = await api("/api/theme-scout/manifest", { method: "POST", body: JSON.stringify(body) });
    if (draftRevision != null && !isCurrentRunDraftPreview(draftRevision, previewGeneration)) {
      return discardStaleRunDraftPreview("The draft or page changed while preparing the review. Return to Runs, check the sectors, and choose Start run again.");
    }
    const manifest = reviewed.manifest || {};
    const scope = manifest.model_scope || {};
    const spending = manifest.spending_controls || {};
    const names = (values) => Array.isArray(values) && values.length ? values.join(", ") : "none";
    const selectedEtfs = scope.selected_sector_etfs || [];
    const sectorsInScope = selectedEtfs.map((item) => `${item.ticker} (${item.sector})`).join(", ") || selectedSectors.join(", ");
    const discovery = scope.dynamic_discovery || {};
    const scopeDetails = [
      `Selected sector ETFs: ${sectorsInScope}`,
      `Current holdings in model context: ${names(scope.holdings)}`,
      `Saved watchlist candidates: ${names(scope.saved_candidates)}`,
      `Possible new stock symbols: up to ${discovery.max_stock_tickers_per_sector || 20} per sector, at most ${discovery.maximum_stock_tickers || 0} total. The free screen chooses these symbols before the model call; their names are not known at confirmation and are recorded in the run report.`,
    ].join("\n");
    const estimate = mode === "screen"
      ? "The screen is free and does not edit the watchlist."
      : includeLlm
        ? `The scout uses the configured model across ${selectedSectors.length} selected sector(s). Current estimate: ${moneyLevel(manifest.cost_estimate?.amount_usd) || "unavailable"}; this is not a spending cap. Weekly check: ${spending.weekly_budget_enabled === false ? "disabled" : `enabled at ${moneyLevel(spending.weekly_budget_usd) || "the configured limit"}`} (already spent ${moneyLevel(spending.spent_usd) || "$0.00"}). Check actual provider cost after the call.\n\n${manifest.cost_estimate?.note || ""}`
        : "The scout pack will not call a paid model. The watchlist is not edited.";
    $("#confirmText").textContent = `${estimate}\n\n${scopeDetails}`;
    $("#confirmText").style.whiteSpace = "pre-line";
    state.pendingRun = null;
    state.pendingRemove = null;
    state.pendingTheme = Object.freeze({ ...body, manifest_sha256: reviewed.manifest_sha256 });
    state.runReviewFocusOnClose = draftRevision != null;
    openConfirm();
    if (draftRevision != null) renderRunResult("Review ready. Confirm the scope and consent before starting.");
    return true;
  } catch (error) {
    if (draftRevision != null && isCurrentRunDraftPreview(draftRevision, previewGeneration)) showRunSubmissionError(error.message);
    else if (draftRevision != null) discardStaleRunDraftPreview("The draft or page changed while preparing the review. Return to Runs, check the sectors, and choose Start run again.");
    else showToast(error.message, "danger");
    return false;
  } finally {
    themePreviewInFlight = false;
  }
}

async function startRunDraft() {
  if (runPreviewInFlight) return;
  clearRunValidation();
  renderRunResult("");
  const eligibility = runEligibility();
  const prepared = RunDraft.request(state.runDraft, eligibility.groups);
  if (prepared.errors.length) {
    showRunValidation(prepared.errors);
    return;
  }
  const revision = state.runDraft.revision;
  const previewGeneration = runDraftPreviewGeneration;
  runPreviewInFlight = true;
  renderRunComposer();
  try {
    if (prepared.family === "theme-scout") {
      await prepareThemePreview(prepared.body.mode, prepared.body.include_llm, prepared.body.sectors, { draftRevision: revision, previewGeneration });
    } else {
      await prepareRunPreview(prepared.body, { draftRevision: revision, previewGeneration });
    }
  } catch (error) {
    if (isCurrentRunDraftPreview(revision, previewGeneration)) showRunSubmissionError(error.message);
    else discardStaleRunDraftPreview("The draft or page changed while preparing the review. Return to Runs, check the scope, and choose Start run again.");
  } finally {
    runPreviewInFlight = false;
    renderRunComposer();
  }
}

$("#runStart").addEventListener("click", startRunDraft);

function isPendingPaid() {
  if (state.pendingRemove || state.pendingAgentSave) return false;
  if (state.pendingTheme) return state.pendingTheme.mode === "weekly" && !!state.pendingTheme.include_llm;
  const b = state.pendingRun;
  if (!b) return false;
  return !b.no_llm;
}

function setConfirmButton(label, variant, icon) {
  const btn = $("#confirmGo");
  btn.className = `ar-btn ar-btn--${variant}`;
  btn.innerHTML = `${iconSvg(icon)}<span class="ar-btn__label">${esc(label)}</span>`;
}

function openConfirm() {
  const paid = isPendingPaid();
  const icon = $("#confirmIcon");
  icon.className = `ar-dialog__icon${state.pendingRemove ? " ar-dialog__icon--danger" : ""}`;
  icon.innerHTML = iconSvg(state.pendingRemove ? "trash-2" : "triangle-alert", "ar-icon");
  $("#confirmConsentWrap").classList.toggle("hidden", !paid);
  $("#confirmConsent").checked = false;
  $("#confirmGo").disabled = paid;
  if (state.pendingAgentSave) {
    $("#confirmTitle").textContent = "Save agent config";
    $("#confirmCaption").textContent = "Writes addons/agent_config.json. The next run reads it. No model is called.";
    setConfirmButton("Save agents", "primary", "check");
  } else if (state.pendingSettingsSave) {
    $("#confirmTitle").textContent = "Save policy settings";
    $("#confirmCaption").textContent = "Updates the active spending and watchlist policy. No model is called.";
    setConfirmButton("Save settings", "primary", "check");
  } else if (state.pendingRemove) {
    $("#confirmTitle").textContent = "Remove from watchlist";
    $("#confirmCaption").textContent = "Writes data/watchlist.json and appends the change log. Undo restores the last add or removal.";
    setConfirmButton("Remove", "danger", "trash-2");
  } else if (state.pendingTheme?.mode === "screen") {
    $("#confirmTitle").textContent = "Run daily screen";
    $("#confirmCaption").textContent = "This step does not call a paid model.";
    setConfirmButton("Run screen", "primary", "play");
  } else if (state.pendingTheme) {
    $("#confirmTitle").textContent = paid ? "Start a paid run?" : "Weekly scout";
    $("#confirmCaption").textContent = paid
      ? "Uses OpenRouter credits. Argus never shows your API keys."
      : "This step does not call a paid model.";
    setConfirmButton("Weekly scout", "primary", "play");
  } else {
    $("#confirmTitle").textContent = paid ? "Start a paid run?" : "Confirm run";
    $("#confirmCaption").textContent = paid
      ? "Uses OpenRouter credits. Argus never shows your API keys."
      : "This step does not call a paid model.";
    setConfirmButton("Start run", "primary", "play");
  }
  $("#confirmModal").showModal();
}

$("#confirmCancel").addEventListener("click", () => $("#confirmModal").close());
$("#confirmModal").addEventListener("close", () => {
  const returnToRunStart = state.runReviewFocusOnClose;
  state.runReviewFocusOnClose = false;
  if (closingFromConfirm) return;
  state.pendingRun = null;
  state.pendingTheme = null;
  state.pendingRemove = null;
  state.pendingAgentSave = false;
  state.pendingSettingsSave = false;
  if (returnToRunStart) $("#runStart").focus();
});
$("#confirmConsent").addEventListener("change", (e) => {
  if (!$("#confirmConsentWrap").classList.contains("hidden")) $("#confirmGo").disabled = !e.target.checked;
});

$("#confirmGo").addEventListener("click", async () => {
  const theme = state.pendingTheme ? { ...state.pendingTheme, confirm: true } : null;
  const saveAgents = state.pendingAgentSave;
  const saveSettings = state.pendingSettingsSave;
  const body = !theme && !saveAgents && state.pendingRun ? { ...state.pendingRun, confirm: true } : null;
  const remove = state.pendingRemove;
  state.pendingTheme = null;
  state.pendingRun = null;
  state.pendingRemove = null;
  state.pendingAgentSave = false;
  state.pendingSettingsSave = false;
  state.runReviewFocusOnClose = false;
  closingFromConfirm = true;
  $("#confirmModal").close();
  closingFromConfirm = false;
  try {
    if (remove) {
      await api(`/api/watchlist/${encodeURIComponent(remove)}`, { method: "DELETE" });
      await loadWatchlist();
      return;
    }
    if (saveAgents) {
      await persistAgents();
      return;
    }
    if (saveSettings) {
      await persistSettings();
      return;
    }
    if (theme) {
      const res = await api("/api/theme-scout", { method: "POST", body: JSON.stringify(theme) });
      await setTab("runs");
      if (res.run?.id) await selectRun(res.run.id);
      return;
    }
    if (!body) return;
    const res = await api("/api/runs", { method: "POST", body: JSON.stringify(body) });
    await loadRuns();
    if (res.run?.id) await selectRun(res.run.id);
  } catch (e) {
    showToast(e.message, "danger");
  }
});

/* ---------- themes ---------- */
async function loadThemes() {
  const data = await api("/api/theme-scout");
  state.themeReport = data;
  const when = formatSessionDate(data.date);
  $("#themeAsOf").textContent = when ? `As of ${when}` : "No report yet";
  $("#themeSub").textContent = data.model_skipped === false
    ? "Weekly scout included the configured model call"
    : "Latest pack did not call a model";
  const screen = data.screen || [];
  $("#themeScreen tbody").innerHTML = screen.slice(0, 40).map((r) => `<tr>
    <td class="ar-num">${r.rank ?? "—"}</td>
    <td class="ar-ticker">${esc(r.ticker || "")}</td>
    <td class="ar-num">${r.score == null || r.score === "" ? "—" : Number(r.score).toFixed(3)}</td>
    <td class="ar-num">${deltaHtml(pctChange(r.rs_1m, 2))}</td>
    <td class="ar-num">${deltaHtml(pctChange(r.dist_ma50, 2))}</td>
    <td class="ar-num">${r.atr_pct == null || r.atr_pct === "" ? "—" : pctLevel(r.atr_pct, 2)}</td>
    <td class="ar-num">${r.earnings_days == null || r.earnings_days === "" ? "—" : esc(r.earnings_days)}</td>
  </tr>`).join("") || `<tr><td colspan="7" class="ar-subtle">No screen yet</td></tr>`;
  const rs = data.relative_strength || [];
  $("#themeRs tbody").innerHTML = rs.map((r) => `<tr>
    <td>${esc(r.id || "")}</td>
    <td class="ar-num">${deltaHtml(pctChange(r.rs_1w, 2))}</td>
    <td class="ar-num">${deltaHtml(pctChange(r.rs_1m, 2))}</td>
    <td class="ar-num">${deltaHtml(pctChange(r.rs_3m, 2))}</td>
  </tr>`).join("") || `<tr><td colspan="4" class="ar-subtle">Run a weekly pack to fill this</td></tr>`;
  const changes = data.changes || [];
  $("#themeChanges").innerHTML = changes.length
    ? changes.map((c) => `<div>${esc(c.action || "")} <span class="ar-mono">${esc(c.ticker || "")}</span> ${esc(c.reason || "")}</div>`).join("")
    : `<p class="ar-muted">No watchlist edits in this pack.</p>`;
  renderMarkdown($("#themeMd"), data.markdown || "_No theme-scout report yet._");
  $("#themeExportPdf").disabled = !data.markdown;
}

async function queueThemeRun(mode) {
  const includeLlm = mode === "weekly" && $("#optScoutLlm").checked;
  const sectors = selectedScoutSectors();
  return prepareThemePreview(mode, includeLlm, sectors);
}

$("#btnScreen").addEventListener("click", () => queueThemeRun("screen"));
$("#btnScout").addEventListener("click", () => queueThemeRun("weekly"));

/* ---------- agents ---------- */
const AGENT_STAGES = [
  { id: "macro", label: "Macro", seats: ["theme_scout"] },
  { id: "analysts", label: "Analysts", seats: ["market", "sentiment", "news", "fundamentals"] },
  { id: "research", label: "Research", seats: ["bull", "bear", "research_manager"] },
  { id: "trader", label: "Trader", seats: ["trader"] },
  { id: "risk", label: "Per-ticker risk", seats: ["risk_aggressive", "risk_conservative", "risk_neutral"] },
  { id: "fund", label: "Fund manager & portfolio risk", seats: ["fm_manager", "fm_aggressive", "fm_conservative", "fm_neutral", "portfolio_manager"] },
  { id: "memory", label: "Memory", seats: ["memory"] },
];
const AGENT_ROLES = {
  theme_scout: "Weekly themes and watchlist ideas",
  market: "Price action and technicals",
  sentiment: "Social, insider, and mood signals",
  news: "Headlines and catalysts",
  fundamentals: "Financials and valuation",
  bull: "Case for the long",
  bear: "Case against the trade",
  research_manager: "Judges the bull and bear debate",
  trader: "Turns the verdict into an order",
  risk_aggressive: "Per-ticker case for taking the trade",
  risk_conservative: "Per-ticker case for staying strict",
  risk_neutral: "Per-ticker case between the two",
  portfolio_manager: "Final per-ticker decision",
  memory: "Lesson written after the run",
  fm_manager: "Portfolio draft and final plan",
  fm_aggressive: "Fund debate: push for more risk",
  fm_conservative: "Fund debate: defend the limits",
  fm_neutral: "Fund debate: the middle view",
};
const AGENT_EFFORTS = [["", "Default"], ["low", "Low"], ["medium", "Med"], ["high", "High"]];

function lineDiff(before, after) {
  const a = String(before ?? "").split("\n");
  const b = String(after ?? "").split("\n");
  const n = a.length;
  const m = b.length;
  const dp = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const rows = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) { rows.push([" ", a[i]]); i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) { rows.push(["−", a[i]]); i++; }
    else { rows.push(["+", b[j]]); j++; }
  }
  while (i < n) rows.push(["−", a[i++]]);
  while (j < m) rows.push(["+", b[j++]]);
  return rows;
}

function fillDiff(pre, before, after) {
  pre.replaceChildren();
  if (String(before) === String(after)) {
    const same = document.createElement("div");
    same.textContent = "Same as the default role text.";
    pre.appendChild(same);
    return;
  }
  lineDiff(before, after).forEach(([mark, line]) => {
    const row = document.createElement("div");
    if (mark === "+") row.className = "ar-diff__add";
    if (mark === "−") row.className = "ar-diff__del";
    row.textContent = `${mark} ${line}`;
    pre.appendChild(row);
  });
}

function seatById(id) {
  return (state.agentDoc?.seats || []).find((s) => s.id === id) || null;
}

function draftFrom(seat) {
  return {
    model: seat.model || "",
    effort: seat.effort || "",
    temperature: seat.temperature ?? null,
    max_tokens: seat.max_tokens ?? null,
    system: seat.system || "",
  };
}

function applyServer(doc) {
  state.agentDoc = doc;
  state.agentDraft = {};
  (doc.seats || []).forEach((seat) => { state.agentDraft[seat.id] = draftFrom(seat); });
}

function normEffort(value) {
  return value || null;
}

function seatDirty(seat) {
  const draft = state.agentDraft[seat.id];
  if (!draft) return false;
  return (draft.model || "") !== (seat.model || "")
    || normEffort(draft.effort) !== normEffort(seat.effort)
    || (draft.max_tokens ?? null) !== (seat.max_tokens ?? null)
    || (draft.temperature ?? null) !== (seat.temperature ?? null)
    || (draft.system || "") !== (seat.system || "");
}

function isModified(seat) {
  const draft = state.agentDraft[seat.id];
  if (!draft) return !!seat.customized;
  return (draft.model || "") !== (seat.default_model || "")
    || normEffort(draft.effort) !== normEffort(seat.default_effort)
    || (draft.max_tokens ?? null) !== (seat.default_max_tokens ?? null)
    || (draft.system || "") !== (seat.default_system || "")
    || (seat.supports_temperature && draft.temperature != null);
}

function unsavedIds() {
  return (state.agentDoc?.seats || []).filter(seatDirty).map((s) => s.id);
}

function stageOf(id) {
  return AGENT_STAGES.find((stage) => stage.seats.includes(id)) || { id: "other", label: "Other" };
}

function familyOf(model) {
  const prefix = String(model || "").split("/")[0].toLowerCase();
  const names = {
    openai: "OpenAI", anthropic: "Anthropic", google: "Google",
    "meta-llama": "Meta", mistralai: "Mistral", "x-ai": "xAI",
  };
  if (!prefix) return "Model";
  return names[prefix] || prefix.charAt(0).toUpperCase() + prefix.slice(1);
}

function moneyCost(n) {
  const v = Number(n);
  if (!Number.isFinite(v)) return "\u2014";
  const digits = Math.abs(v) < 1 ? 4 : 2;
  return "$" + v.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function seatCost(seat, modelId) {
  const row = (state.agentDoc?.models || []).find((m) => m.id === modelId);
  if (!row || seat.est_input_tokens == null || seat.est_output_tokens == null) return null;
  if (row.usd_per_mtok_in == null || row.usd_per_mtok_out == null) return null;
  return seat.est_input_tokens / 1e6 * row.usd_per_mtok_in + seat.est_output_tokens / 1e6 * row.usd_per_mtok_out;
}

function opusWarn(seat) {
  const model = state.agentDraft[seat.id]?.model || "";
  if (seat.id === "risk_conservative" || seat.id === "fm_conservative") return false;
  return /opus/i.test(model);
}

function visibleStages() {
  const query = state.agentQuery.trim().toLowerCase();
  const known = new Set(AGENT_STAGES.flatMap((stage) => stage.seats));
  const extras = (state.agentDoc?.seats || []).map((s) => s.id).filter((id) => !known.has(id));
  const stages = extras.length ? AGENT_STAGES.concat([{ id: "other", label: "Other", seats: extras }]) : AGENT_STAGES;
  return stages.map((stage) => ({
    ...stage,
    rows: stage.seats.map(seatById).filter(Boolean).filter((seat) => {
      if (state.agentModifiedOnly && !isModified(seat)) return false;
      if (!query) return true;
      const draft = state.agentDraft[seat.id] || {};
      const blob = `${seat.label} ${AGENT_ROLES[seat.id] || ""} ${draft.model || ""} ${stage.label}`.toLowerCase();
      return blob.includes(query);
    }),
  })).filter((stage) => stage.rows.length);
}

function visibleIds() {
  return visibleStages().flatMap((stage) => stage.rows.map((seat) => seat.id));
}

function iconEl(name, cls) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", cls);
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", `${SPRITE}#${name}`);
  svg.append(use);
  return svg;
}

function badge(cls, label, icon) {
  const el = document.createElement("span");
  el.className = `ar-badge ${cls}`;
  if (icon) el.append(iconEl(icon, "ar-icon ar-icon--sm"));
  el.append(document.createTextNode(label));
  return el;
}

function fillStatus(cell, seat) {
  const wrap = document.createElement("div");
  wrap.className = "ar-agent-status";
  if (opusWarn(seat)) wrap.append(badge("ar-badge--warn", "Opus", "triangle-alert"));
  if (isModified(seat)) {
    const mod = badge("ar-badge--info", "Modified");
    mod.prepend(Object.assign(document.createElement("span"), { className: "ar-badge__dot" }));
    wrap.append(mod);
  } else {
    wrap.append(badge("ar-badge--neutral", "Default"));
  }
  cell.replaceChildren(wrap);
}

function modelOptions(select, seat) {
  const draft = state.agentDraft[seat.id];
  const known = state.agentDoc.models || [];
  select.replaceChildren();
  if (draft.model && !known.some((m) => m.id === draft.model)) {
    const custom = document.createElement("option");
    custom.value = draft.model;
    custom.textContent = draft.model;
    select.append(custom);
  }
  known.forEach((model) => {
    const opt = document.createElement("option");
    opt.value = model.id;
    opt.textContent = model.label || model.id;
    select.append(opt);
  });
  select.value = draft.model;
}

function buildRow(seat) {
  const draft = state.agentDraft[seat.id];
  const tr = document.createElement("tr");
  tr.dataset.seat = seat.id;
  tr.tabIndex = -1;
  if (state.agentSelected === seat.id) tr.setAttribute("aria-selected", "true");

  const name = document.createElement("td");
  const nameEl = document.createElement("div");
  nameEl.className = "ar-agent-name";
  nameEl.textContent = seat.label;
  const role = document.createElement("div");
  role.className = "ar-agent-role";
  role.textContent = AGENT_ROLES[seat.id] || seat.group || "";
  name.append(nameEl, role);

  const model = document.createElement("td");
  const modelWrap = document.createElement("div");
  modelWrap.className = "ar-agent-model";
  const fam = document.createElement("span");
  fam.className = "ar-badge ar-badge--neutral";
  fam.dataset.family = "1";
  fam.textContent = familyOf(draft.model);
  const select = document.createElement("select");
  select.className = "ar-select ar-select--sm";
  select.dataset.model = "1";
  select.setAttribute("aria-label", `Model for ${seat.label}`);
  modelOptions(select, seat);
  modelWrap.append(fam, select);
  model.append(modelWrap);

  const effort = document.createElement("td");
  const effortWrap = document.createElement("div");
  effortWrap.className = "ar-agent-effort";
  const effortSelect = document.createElement("select");
  effortSelect.className = "ar-select ar-select--sm";
  effortSelect.dataset.effort = "1";
  effortSelect.setAttribute("aria-label", `Reasoning effort for ${seat.label}`);
  AGENT_EFFORTS.forEach(([value, label]) => {
    const opt = document.createElement("option");
    opt.value = value;
    opt.textContent = label;
    effortSelect.append(opt);
  });
  effortSelect.value = draft.effort || "";
  effortSelect.disabled = !seat.supports_effort;
  if (!seat.supports_effort) {
    effortWrap.dataset.tooltip = "Effort is not sent";
    effortWrap.tabIndex = 0;
  }
  effortWrap.append(effortSelect);
  effort.append(effortWrap);

  const tokens = document.createElement("td");
  tokens.className = "ar-num ar-col-extra";
  const tokenInput = document.createElement("input");
  tokenInput.className = "ar-input ar-input--num ar-input--sm";
  tokenInput.dataset.tokens = "1";
  tokenInput.inputMode = "numeric";
  tokenInput.setAttribute("aria-label", `Max tokens for ${seat.label}`);
  tokenInput.value = draft.max_tokens == null ? "" : String(draft.max_tokens);
  tokenInput.placeholder = "\u2014";
  tokenInput.disabled = !seat.supports_max_tokens;
  if (!seat.supports_max_tokens) {
    tokenInput.dataset.tooltip = "Max tokens are not sent";
    tokenInput.tabIndex = 0;
  }
  tokens.append(tokenInput);

  const cost = document.createElement("td");
  cost.className = "ar-num ar-agent-cost ar-col-extra";
  cost.dataset.cost = "1";
  const amount = seatCost(seat, draft.model);
  cost.textContent = amount == null ? "\u2014" : moneyCost(amount);

  const status = document.createElement("td");
  status.dataset.status = "1";
  fillStatus(status, seat);
  tr.append(name, model, effort, tokens, cost, status);
  return tr;
}

function patchRow(id) {
  const seat = seatById(id);
  const tr = document.querySelector(`#agentTable tr[data-seat="${id}"]`);
  if (!seat || !tr) return;
  const draft = state.agentDraft[id];
  tr.toggleAttribute("aria-selected", state.agentSelected === id);
  if (state.agentSelected === id) tr.setAttribute("aria-selected", "true");
  else tr.removeAttribute("aria-selected");
  const fam = tr.querySelector("[data-family]");
  if (fam) fam.textContent = familyOf(draft.model);
  const select = tr.querySelector("[data-model]");
  if (select && document.activeElement !== select) {
    modelOptions(select, seat);
  }
  const effort = tr.querySelector("[data-effort]");
  if (effort && document.activeElement !== effort) {
    effort.value = draft.effort || "";
    effort.disabled = !seat.supports_effort;
  }
  const tokens = tr.querySelector("[data-tokens]");
  if (tokens && document.activeElement !== tokens) {
    tokens.value = draft.max_tokens == null ? "" : String(draft.max_tokens);
    tokens.disabled = !seat.supports_max_tokens;
  }
  const cost = tr.querySelector("[data-cost]");
  if (cost) {
    const amount = seatCost(seat, draft.model);
    cost.textContent = amount == null ? "\u2014" : moneyCost(amount);
  }
  fillStatus(tr.querySelector("[data-status]"), seat);
  syncPanelFields(id);
}

function syncPanelFields(id) {
  if (state.agentSelected !== id || !$("#agentPanelTokens")) return;
  const seat = seatById(id);
  const draft = state.agentDraft[id];
  if (!seat || !draft) return;
  $$("[data-panel-effort]").forEach((btn) => {
    btn.setAttribute("aria-pressed", String((btn.dataset.panelEffort || "") === (draft.effort || "")));
    btn.disabled = !seat.supports_effort;
  });
  const tokens = $("#agentPanelTokens");
  if (tokens && document.activeElement !== tokens) {
    tokens.value = draft.max_tokens == null ? "" : String(draft.max_tokens);
    tokens.disabled = !seat.supports_max_tokens;
  }
  const custom = $("#agentCustomModel");
  if (custom && document.activeElement !== custom) {
    const known = new Set((state.agentDoc.models || []).map((m) => m.id));
    custom.value = known.has(draft.model) ? "" : draft.model;
  }
  const temp = $("#agentPanelTemp");
  if (temp && document.activeElement !== temp) {
    temp.value = draft.temperature == null ? "" : String(draft.temperature);
  }
  const cost = $("#agentPanelCost");
  if (cost) {
    const amount = seatCost(seat, draft.model);
    cost.value = amount == null ? "\u2014" : moneyCost(amount);
  }
  refreshPanelChrome();
}

function renderEmpty(title, text, retry) {
  const tbody = $("#agentTable");
  tbody.replaceChildren();
  const tr = document.createElement("tr");
  const td = document.createElement("td");
  td.colSpan = 6;
  const box = document.createElement("div");
  box.className = "ar-empty ar-agents__empty";
  const icon = document.createElement("div");
  icon.className = "ar-empty__icon";
  icon.append(iconEl(retry ? "circle-x" : "search", "ar-icon ar-icon--lg"));
  const h = document.createElement("p");
  h.className = "ar-empty__title";
  h.textContent = title;
  const p = document.createElement("p");
  p.className = "ar-empty__text";
  p.textContent = text;
  box.append(icon, h, p);
  if (retry) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "ar-btn";
    btn.innerHTML = `${iconSvg("refresh-cw")}<span class="ar-btn__label">Retry</span>`;
    btn.addEventListener("click", () => { state.agentDoc = null; loadAgents(); });
    box.append(btn);
  }
  td.append(box);
  tr.append(td);
  tbody.append(tr);
}

function renderTable() {
  const tbody = $("#agentTable");
  if (!$("#agentTable")) return;
  if (state.agentLoading && !state.agentDoc) {
    tbody.replaceChildren();
    for (let i = 0; i < 8; i += 1) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 6;
      const bar = document.createElement("span");
      bar.className = "ar-skeleton ar-skeleton--row";
      td.append(bar);
      tr.append(td);
      tbody.append(tr);
    }
    return;
  }
  if (!state.agentDoc) {
    renderEmpty("Agents did not load", state.agentError || "The config could not be read.", true);
    return;
  }
  const stages = visibleStages();
  if (!stages.length) {
    const title = state.agentModifiedOnly ? "No modified agents" : "No agents match";
    const text = state.agentModifiedOnly
      ? "Every visible seat still uses its default model and role text."
      : "Try another name, role, or model id.";
    renderEmpty(title, text, false);
    return;
  }
  tbody.replaceChildren();
  stages.forEach((stage) => {
    const group = document.createElement("tr");
    group.className = "ar-agents__group";
    const cell = document.createElement("td");
    cell.colSpan = 6;
    cell.textContent = stage.label;
    group.append(cell);
    tbody.append(group);
    stage.rows.forEach((seat) => tbody.append(buildRow(seat)));
  });
}

function paintLines(text) {
  const count = Math.max(1, String(text || "").split("\n").length);
  const lines = [];
  for (let i = 1; i <= count; i += 1) lines.push(String(i));
  $("#agentLines").textContent = lines.join("\n");
}

function setAgentTab(name) {
  state.agentTab = name;
  $$("[data-agent-tab]").forEach((btn) => {
    const on = btn.dataset.agentTab === name;
    btn.setAttribute("aria-selected", on ? "true" : "false");
  });
  $("#agentPreview").classList.toggle("hidden", name !== "preview");
  $("#agentEdit").classList.toggle("hidden", name !== "edit");
  $("#agentDiff").classList.toggle("hidden", name !== "diff");
  const seat = seatById(state.agentSelected);
  if (!seat) return;
  const system = state.agentDraft[seat.id]?.system || "";
  if (name === "preview") renderMarkdown($("#agentPreview"), system || "_No role text._");
  if (name === "diff") fillDiff($("#agentDiff"), seat.default_system || "", system);
  if (name === "edit") paintLines(system);
}

function buildPanelMeta(seat) {
  const host = $("#agentPanelMeta");
  host.replaceChildren();
  const draft = state.agentDraft[seat.id];

  const effortField = document.createElement("div");
  effortField.className = "ar-field";
  const effortLabel = document.createElement("span");
  effortLabel.className = "ar-label";
  effortLabel.textContent = "Reasoning effort";
  effortField.classList.add("ar-agents__span-2");
  const seg = document.createElement("div");
  seg.className = "ar-segmented ar-agents__effort";
  seg.setAttribute("role", "group");
  seg.setAttribute("aria-label", "Reasoning effort");
  if (!seat.supports_effort) {
    seg.dataset.tooltip = "Effort is not sent";
    seg.tabIndex = 0;
  }
  AGENT_EFFORTS.forEach(([value, label]) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = label;
    btn.dataset.panelEffort = value;
    btn.setAttribute("aria-pressed", String((draft.effort || "") === value));
    btn.disabled = !seat.supports_effort;
    btn.addEventListener("click", () => {
      state.agentDraft[seat.id].effort = value;
      $$("[data-panel-effort]", seg).forEach((b) => b.setAttribute("aria-pressed", String(b === btn)));
      patchRow(seat.id);
      syncBar();
    });
    seg.append(btn);
  });
  effortField.append(effortLabel, seg);

  const tokenField = document.createElement("div");
  tokenField.className = "ar-field";
  const tokenLabel = document.createElement("label");
  tokenLabel.className = "ar-label";
  tokenLabel.htmlFor = "agentPanelTokens";
  tokenLabel.textContent = "Max tokens";
  const tokenInput = document.createElement("input");
  tokenInput.className = "ar-input ar-input--num";
  tokenInput.id = "agentPanelTokens";
  tokenInput.inputMode = "numeric";
  tokenInput.value = draft.max_tokens == null ? "" : String(draft.max_tokens);
  tokenInput.disabled = !seat.supports_max_tokens;
  tokenInput.addEventListener("input", () => {
    const parsed = parseTokens(tokenInput.value);
    tokenInput.setAttribute("aria-invalid", parsed.ok ? "false" : "true");
    if (!parsed.ok) return;
    state.agentDraft[seat.id].max_tokens = parsed.value == null ? seat.default_max_tokens : parsed.value;
    patchRow(seat.id);
    syncBar();
  });
  tokenField.append(tokenLabel, tokenInput);

  const customField = document.createElement("div");
  customField.className = "ar-field";
  const customLabel = document.createElement("label");
  customLabel.className = "ar-label";
  customLabel.htmlFor = "agentCustomModel";
  customLabel.textContent = "Custom model id";
  const custom = document.createElement("input");
  custom.className = "ar-input ar-input--mono";
  custom.id = "agentCustomModel";
  custom.autocomplete = "off";
  custom.spellcheck = false;
  custom.placeholder = "provider/model";
  const known = new Set((state.agentDoc.models || []).map((m) => m.id));
  custom.value = known.has(draft.model) ? "" : draft.model;
  custom.addEventListener("input", () => {
    const text = custom.value.trim();
    const rowSelect = document.querySelector(`#agentTable tr[data-seat="${seat.id}"] [data-model]`);
    state.agentDraft[seat.id].model = text || rowSelect?.value || seat.default_model;
    patchRow(seat.id);
    refreshPanelChrome();
    refreshAgentWarnings();
    syncBar();
  });
  customField.append(customLabel, custom);

  const costField = document.createElement("div");
  costField.className = "ar-field";
  const costLabel = document.createElement("label");
  costLabel.className = "ar-label";
  costLabel.htmlFor = "agentPanelCost";
  costLabel.textContent = "Est. cost";
  const costInput = document.createElement("input");
  costInput.className = "ar-input ar-input--mono";
  costInput.id = "agentPanelCost";
  costInput.readOnly = true;
  costInput.tabIndex = -1;
  const amount = seatCost(seat, draft.model);
  costInput.value = amount == null ? "\u2014" : moneyCost(amount);
  costField.append(costLabel, costInput);

  host.append(effortField, tokenField);
  if (!seat.supports_temperature) customField.classList.add("ar-agents__span-2");
  host.append(customField);
  if (seat.supports_temperature) {
    const tempField = document.createElement("div");
    tempField.className = "ar-field";
    const tempLabel = document.createElement("label");
    tempLabel.className = "ar-label";
    tempLabel.htmlFor = "agentPanelTemp";
    tempLabel.textContent = "Temperature";
    const temp = document.createElement("input");
    temp.className = "ar-input ar-input--num";
    temp.id = "agentPanelTemp";
    temp.inputMode = "decimal";
    temp.placeholder = "Not sent";
    temp.value = draft.temperature == null ? "" : String(draft.temperature);
    temp.addEventListener("input", () => {
      const parsed = parseTemp(temp.value);
      temp.setAttribute("aria-invalid", parsed.ok ? "false" : "true");
      if (!parsed.ok) return;
      state.agentDraft[seat.id].temperature = parsed.value;
      patchRow(seat.id);
      syncBar();
    });
    tempField.append(tempLabel, temp);
    host.append(tempField);
  }
  host.append(costField);
}

function parseTokens(value) {
  const text = String(value || "").trim();
  if (!text) return { ok: true, value: null };
  if (!/^\d+$/.test(text)) return { ok: false };
  const number = Number(text);
  if (number < 1 || number > 200000) return { ok: false };
  return { ok: true, value: number };
}

function parseTemp(value) {
  const text = String(value || "").trim();
  if (!text) return { ok: true, value: null };
  const number = Number(text);
  if (!Number.isFinite(number) || number < 0 || number > 2) return { ok: false };
  return { ok: true, value: number };
}

function refreshPanelChrome() {
  const seat = seatById(state.agentSelected);
  if (!seat) return;
  const draft = state.agentDraft[seat.id];
  $("#agentPanelName").textContent = seat.label;
  $("#agentPanelStage").textContent = stageOf(seat.id).label;
  const chip = $("#agentPanelChip");
  chip.textContent = `${familyOf(draft.model)} \u00b7 ${draft.model}`;
  const note = $("#agentLockNote");
  if (opusWarn(seat)) {
    note.classList.remove("hidden");
    note.textContent = `${seat.label} uses ${draft.model}. Opus on this seat is allowed and is not blocked.`;
  } else {
    note.classList.add("hidden");
    note.textContent = "";
  }
}

function refreshPanel(opts = {}) {
  const seat = seatById(state.agentSelected);
  if (!seat) return;
  refreshPanelChrome();
  const system = state.agentDraft[seat.id].system || "";
  const area = $("#agentPrompt");
  if (opts.forceText || document.activeElement !== area) area.value = system;
  paintLines(area.value);
  setAgentTab(state.agentTab || "preview");
  syncBar();
}

function hidePanel() {
  state.agentSelected = null;
  $("#agentPanel").classList.add("hidden");
  $("#agentPanel").setAttribute("aria-hidden", "true");
  $("#tab-agents").classList.remove("is-panel");
  $$("#agentTable tr[data-seat]").forEach((tr) => tr.removeAttribute("aria-selected"));
  syncBar();
}

function selectAgent(id) {
  if (!seatById(id)) return;
  state.agentSelected = id;
  $("#agentPanel").classList.remove("hidden");
  $("#agentPanel").setAttribute("aria-hidden", "false");
  $("#tab-agents").classList.add("is-panel");
  $$("#agentTable tr[data-seat]").forEach((tr) => {
    if (tr.dataset.seat === id) tr.setAttribute("aria-selected", "true");
    else tr.removeAttribute("aria-selected");
  });
  buildPanelMeta(seatById(id));
  refreshPanel({ forceText: true });
  const row = document.querySelector(`#agentTable tr[data-seat="${id}"]`);
  if (row) row.scrollIntoView({ block: "nearest" });
}

function requestClosePanel() {
  const seat = seatById(state.agentSelected);
  if (!seat) return;
  if (seatDirty(seat)) {
    state.agentCloseMode = "panel";
    $("#agentCloseTitle").textContent = "Close this agent?";
    $("#agentCloseText").textContent = `${seat.label} has unsaved changes. Discard them, or keep them in the table until you save.`;
    $("#agentCloseModal").showModal();
    return;
  }
  hidePanel();
}

function revertSeat(id) {
  const seat = seatById(id);
  if (!seat) return;
  state.agentDraft[id] = draftFrom(seat);
}

function revertAll() {
  (state.agentDoc?.seats || []).forEach((seat) => revertSeat(seat.id));
}

function syncBar() {
  const count = unsavedIds().length;
  const open = !!state.agentSelected && !$("#agentPanel").classList.contains("hidden");
  $("#agentDirtyCount").textContent = count === 0
    ? "No unsaved changes"
    : `${count} unsaved change${count === 1 ? "" : "s"}`;
  $("#agentDiscard").disabled = count === 0;
  $("#agentSaveAll").disabled = count === 0;
  $("#agentSave").disabled = count === 0;
  $("#agentSaveAll").className = open ? "ar-btn" : "ar-btn ar-btn--primary";
  const seat = seatById(state.agentSelected);
  $("#agentSeatDirty").classList.toggle("hidden", !(seat && seatDirty(seat)));
}

function refreshAgentWarnings() {
  const warnings = [];
  (state.agentDoc?.seats || []).forEach((seat) => {
    const model = state.agentDraft[seat.id]?.model || "";
    if (opusWarn(seat)) {
      warnings.push(`${seat.label} uses ${model}. Opus on this seat is allowed and is not blocked.`);
    }
  });
  $("#agentWarn").classList.toggle("hidden", warnings.length === 0);
  $("#agentWarnText").textContent = warnings.join(" ");
}

function renderAgents() {
  const doc = state.agentDoc;
  $("#agentPricing").textContent = doc?.pricing_note || "";
  const err = $("#agentError");
  err.classList.toggle("hidden", !state.agentError);
  $("#agentErrorText").textContent = state.agentError || "";
  renderTable();
  refreshAgentWarnings();
  if (state.agentSelected && seatById(state.agentSelected)) {
    buildPanelMeta(seatById(state.agentSelected));
    refreshPanel();
  } else if (state.agentSelected) hidePanel();
  syncBar();
}

async function loadAgents() {
  if (unsavedIds().length) return;
  state.agentError = "";
  if (!state.agentDoc) {
    state.agentLoading = true;
    renderAgents();
  }
  try {
    applyServer(await api("/api/agents"));
    state.agentLoading = false;
    renderAgents();
  } catch (e) {
    state.agentLoading = false;
    state.agentError = e.message || "Could not load agents";
    renderAgents();
  }
}

function collectAgents() {
  const seats = {};
  (state.agentDoc.seats || []).forEach((seat) => {
    const draft = state.agentDraft[seat.id];
    const model = (draft.model || "").trim() || seat.default_model;
    seats[seat.id] = {
      model,
      effort: draft.effort || null,
      temperature: seat.supports_temperature ? draft.temperature : null,
      max_tokens: draft.max_tokens,
      system: draft.system || "",
    };
  });
  return { seats, unlock: [] };
}

async function persistAgents() {
  const doc = await api("/api/agents", { method: "PUT", body: JSON.stringify(collectAgents()) });
  applyServer(doc);
  renderAgents();
  const warns = doc.warnings || [];
  showToast(warns.length ? `Saved. ${warns.length} Opus warning${warns.length === 1 ? "" : "s"}.` : "Agent config saved.", warns.length ? "warn" : "ok");
}

function requestSave() {
  if (!unsavedIds().length) return;
  state.pendingRun = null;
  state.pendingTheme = null;
  state.pendingRemove = null;
  state.pendingAgentSave = true;
  $("#confirmText").textContent = "Save these models and role prompts? The next fund-manager, theme-scout, and per-ticker run reads them. Nothing is called now.";
  openConfirm();
}

$("#agentTable").addEventListener("click", (e) => {
  if (e.target.closest("input, select, button, textarea, a, label")) return;
  const tr = e.target.closest("tr[data-seat]");
  if (tr) selectAgent(tr.dataset.seat);
});

$("#agentTable").addEventListener("change", (e) => {
  const tr = e.target.closest("tr[data-seat]");
  if (!tr) return;
  const draft = state.agentDraft[tr.dataset.seat];
  if (!draft) return;
  if (e.target.matches("[data-model]")) draft.model = e.target.value;
  if (e.target.matches("[data-effort]")) draft.effort = e.target.value;
  patchRow(tr.dataset.seat);
  refreshAgentWarnings();
  syncBar();
});

$("#agentTable").addEventListener("input", (e) => {
  if (!e.target.matches("[data-tokens]")) return;
  const tr = e.target.closest("tr[data-seat]");
  const seat = seatById(tr?.dataset.seat);
  if (!seat) return;
  const parsed = parseTokens(e.target.value);
  e.target.setAttribute("aria-invalid", parsed.ok ? "false" : "true");
  if (!parsed.ok) return;
  state.agentDraft[seat.id].max_tokens = parsed.value == null ? seat.default_max_tokens : parsed.value;
  patchRow(seat.id);
  syncBar();
});

$("#agentSearch").addEventListener("input", () => {
  state.agentQuery = $("#agentSearch").value;
  renderTable();
});

$("#agentModifiedOnly").addEventListener("change", () => {
  state.agentModifiedOnly = $("#agentModifiedOnly").checked;
  renderTable();
});

$$("[data-agent-tab]").forEach((btn) => {
  btn.addEventListener("click", () => setAgentTab(btn.dataset.agentTab));
});

$("#agentPrompt").addEventListener("input", () => {
  const seat = seatById(state.agentSelected);
  if (!seat) return;
  state.agentDraft[seat.id].system = $("#agentPrompt").value;
  paintLines($("#agentPrompt").value);
  if (state.agentTab === "preview") renderMarkdown($("#agentPreview"), $("#agentPrompt").value || "_No role text._");
  if (state.agentTab === "diff") fillDiff($("#agentDiff"), seat.default_system || "", $("#agentPrompt").value);
  patchRow(seat.id);
  syncBar();
});

$("#agentPrompt").addEventListener("scroll", () => {
  $("#agentLines").scrollTop = $("#agentPrompt").scrollTop;
});

$("#agentReset").addEventListener("click", () => {
  const seat = seatById(state.agentSelected);
  if (!seat) return;
  state.agentDraft[seat.id].system = seat.default_system || "";
  refreshPanel({ forceText: true });
  patchRow(seat.id);
  syncBar();
});

$("#agentSave").addEventListener("click", requestSave);
$("#agentSaveAll").addEventListener("click", requestSave);
$("#agentPanelClose").addEventListener("click", requestClosePanel);
$("#agentBackdrop").addEventListener("click", requestClosePanel);

$("#agentDiscard").addEventListener("click", () => {
  const count = unsavedIds().length;
  if (!count) return;
  state.agentCloseMode = "all";
  $("#agentCloseTitle").textContent = "Discard unsaved edits?";
  $("#agentCloseText").textContent = `Discard ${count} unsaved change${count === 1 ? "" : "s"}? The table returns to the last save.`;
  $("#agentCloseModal").showModal();
});

$("#agentCloseKeep").addEventListener("click", () => {
  const mode = state.agentCloseMode;
  $("#agentCloseModal").close();
  state.agentCloseMode = null;
  if (mode === "panel") hidePanel();
});

$("#agentCloseDiscard").addEventListener("click", () => {
  const mode = state.agentCloseMode;
  const selected = state.agentSelected;
  $("#agentCloseModal").close();
  state.agentCloseMode = null;
  if (mode === "panel" && selected) revertSeat(selected);
  if (mode === "all") revertAll();
  hidePanel();
  renderAgents();
});

$("#agentResize").addEventListener("pointerdown", (e) => {
  if (window.innerWidth <= 1100) return;
  e.preventDefault();
  const body = $(".ar-agents__body");
  const panel = $("#agentPanel");
  const move = (ev) => {
    const rect = body.getBoundingClientRect();
    const pct = Math.min(56, Math.max(28, ((rect.right - ev.clientX) / rect.width) * 100));
    panel.style.width = `${pct}%`;
    panel.style.flexBasis = `${pct}%`;
  };
  const up = () => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", up);
  };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", up);
});

document.addEventListener("keydown", (e) => {
  if (state.tab !== "agents") return;
  if (document.querySelector("dialog[open]")) return;
  if (e.key === "Escape" && state.agentSelected) {
    e.preventDefault();
    requestClosePanel();
    return;
  }
  if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
  const tag = document.activeElement?.tagName || "";
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || document.activeElement?.isContentEditable) return;
  const ids = visibleIds();
  if (!ids.length) return;
  e.preventDefault();
  let index = ids.indexOf(state.agentSelected);
  if (e.key === "ArrowDown") index = index < 0 ? 0 : Math.min(ids.length - 1, index + 1);
  else index = index < 0 ? ids.length - 1 : Math.max(0, index - 1);
  selectAgent(ids[index]);
});

/* ---------- boot ---------- */
(async function boot() {
  syncChromeToggles();
  try {
    const res = await fetch("/api/session");
    if (res.ok) state.token = (await res.json()).token;
  } catch (_) { /* runs will 401 until a session token loads */ }
  await loadHealth();
  await setTab("portfolio");
})();
