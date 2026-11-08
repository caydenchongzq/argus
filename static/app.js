/* Argus frontend. Rendering uses the brand system; API behaviour is unchanged. */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const SPRITE = "/static/argus-brand/assets/icons/argus-icons.svg";
const MINUS = "\u2212";

const state = {
  tab: "portfolio",
  portfolio: null,
  watchlist: [],
  reports: [],
  latestByTicker: {},
  fund: null,
  runs: [],
  flags: {},
  selectedReport: null,
  selectedRun: null,
  pendingTheme: null,
  pendingRemove: null,
  logOffset: 0,
  logText: "",
  logTimer: null,
  chart: null,
  bookTickers: [],
  pendingRun: null,
  tigerPreview: null,
  tigerPreviewRequestId: 0,
  pendingAgentSave: false,
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
  if (n == null || Number.isNaN(Number(n))) return "—";
  const v = Number(n);
  const body = moneyAbs(v, abbreviate);
  return v < 0 ? `${MINUS}${body}` : body;
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
  if (n == null || Number.isNaN(Number(n))) return "—";
  const v = Number(n);
  if (Number.isInteger(v)) return v.toLocaleString();
  return String(Number(v.toFixed(4)));
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
    if (name === "agents") await loadAgents();
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
    state.flags = h.flags || {};
    pill.className = `ar-badge ${h.data_ok ? "ar-badge--ok" : "ar-badge--warn"}`;
    pill.innerHTML = `<span class="ar-badge__dot"></span> ${h.data_ok ? "Connected" : "Data missing"}`;
    $("#optWlWrap").classList.toggle("hidden", !state.flags.IncludeWatchlist);
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
  $("#pfSub").textContent = data.total_market_value != null
    ? `NAV ${moneyLevel(data.total_market_value)} · cash ${moneyLevel(data.cash)}`
    : `Cash ${moneyLevel(data.cash)} · mark prices when a fund-manager stats file exists`;

  const pnl = data.account?.unrealized_pnl;
  const change = moneyChange(pnl, true);
  const allPriced = (data.positions || []).length > 0 && (data.positions || []).every((p) => p.price != null);
  let pnlPct = null;
  if (allPriced && pnl != null && data.total_cost != null) {
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
    <article class="ar-stat ar-span-3"><span class="ar-stat__label">Cash</span><span class="ar-stat__value">${esc(moneyLevel(data.cash, true))}</span><span class="ar-stat__delta"><span class="ar-subtle">${esc(pctLevel(data.cash_pct, 1))} · target ${esc(pctLevel(data.cash_target_pct, 1))}</span></span></article>
    <article class="ar-stat ar-span-3"><span class="ar-stat__label">Unrealized P&amp;L</span><span class="ar-stat__value ${pnlClass}">${pnlValue}</span><span class="ar-stat__delta">${pnlDelta}</span></article>
    <article class="ar-stat ar-span-3"><span class="ar-stat__label">Positions</span><span class="ar-stat__value">${data.positions.length}</span><span class="ar-stat__delta"><span class="ar-subtle">Currency ${esc(data.currency || "USD")}</span></span></article>
  `;

  const subLabel = {};
  (data.ai_subthemes || []).forEach((b) => {
    if (b && b.id) subLabel[b.id] = b.label || b.id;
  });
  const tb = $("#pfTable tbody");
  tb.innerHTML = data.positions.map((p) => {
    const rowChange = moneyChange(p.unrealized_pnl);
    const rowPct = pctChange(p.unrealized_pnl_pct, 2);
    const pnlCell = rowChange
      ? `${deltaHtml(rowChange)}${rowPct ? ` ${deltaHtml(rowPct)}` : ""}`
      : `<span class="ar-subtle">—</span>`;
    const stale = p.price == null ? "is-stale" : "";
    return `<tr class="${stale}">
      <td class="ar-ticker">${esc(p.ticker)}</td>
      <td class="ar-subtle">${esc(p.name || "")}</td>
      <td class="ar-subtle">${esc(p.sub_theme ? (subLabel[p.sub_theme] || p.sub_theme) : "—")}</td>
      <td>${esc(p.sleeve === "core_etf" ? "Core ETF" : "Swing")}</td>
      <td class="ar-num">${qty(p.quantity)}</td>
      <td class="ar-num">${price(p.average_price)}</td>
      <td class="ar-num">${price(p.price)}</td>
      <td class="ar-num">${moneyLevel(p.market_value)}</td>
      <td class="ar-num">${pnlCell}</td>
      <td class="ar-num">${pctLevel(p.weight_pct, 1)}</td>
      <td class="ar-num ar-subtle">${p.target_pct != null ? pctLevel(p.target_pct, 1) : "—"}</td>
    </tr>`;
  }).join("");

  const sleeveNote = $("#pfSleeve");
  if (sleeveNote) {
    const core = (data.sleeves || {}).core_etf || {};
    const swing = (data.sleeves || {}).swing || {};
    const corePnl = moneyChange(core.unrealized_pnl);
    const swingPnl = moneyChange(swing.unrealized_pnl);
    sleeveNote.innerHTML = `Core ETF ${esc(pctLevel(core.weight_pct, 1))} · ${corePnl ? deltaHtml(corePnl) : "—"} · Swing ${esc(pctLevel(swing.weight_pct, 1))} · ${swingPnl ? deltaHtml(swingPnl) : "—"} · guide ${esc(pctLevel(data.core_etf_warn_pct, 0))} / rest`;
  }

  renderWeightsChart(data);
  const note = $("#aiSubNote");
  if (note) {
    note.textContent = `Direct holding weight. Look-through warn cap is ${pctLevel(data.ai_sleeve_cap_pct, 0)} (targets.json). SPY's sleeve fraction is not split into these rows.`;
  }
  const sub = $("#aiSubTable tbody");
  if (sub) sub.innerHTML = renderSubthemeRows(data.ai_subthemes, true);
}

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
    current.push(row.weight_pct ?? 0);
    target.push(data.targets?.[t] ?? 0);
  });
  labels.push("cash");
  current.push(data.cash_pct ?? 0);
  target.push(data.cash_target_pct ?? 0);

  const ctx = $("#weightsChart");
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
        { label: "Target %", data: target, backgroundColor: cssVar("--argus-chart-2"), borderWidth: 0 },
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

function renderSubthemeRows(rows, withValue) {
  return (rows || []).map((b) => {
    const names = (b.tickers || []).map((t) => t.weight_pct != null ? `${t.ticker} ${pctLevel(t.weight_pct, 1)}` : t.ticker).join(", ") || "—";
    const value = withValue ? `<td class="ar-num">${moneyLevel(b.market_value)}</td>` : `<td class="ar-num">${b.count || 0}</td>`;
    const weight = withValue ? `<td class="ar-num">${pctLevel(b.weight_pct, 1)}</td>` : "";
    return `<tr><td>${esc(b.label || b.id)}</td><td class="ar-mono">${esc(names)}</td>${weight}${value}</tr>`;
  }).join("");
}

/* ---------- Tiger read-only import ---------- */
function syncTigerApply() {
  const preview = state.tigerPreview;
  const empty = Boolean(preview && preview.positions.length === 0);
  $("#tigerReplaceWrap").classList.toggle("hidden", !preview?.can_apply);
  $("#tigerStockOnlyWrap").classList.toggle("hidden", !preview?.can_apply);
  $("#tigerEmptyWrap").classList.toggle("hidden", !preview?.can_apply || !empty);
  $("#tigerApply").disabled = !preview?.can_apply
    || !$("#tigerReplace").checked
    || !$("#tigerStockOnly").checked
    || (empty && !$("#tigerEmpty").checked);
}

function renderTigerPreview(preview) {
  const body = $("#tigerPreviewBody");
  const rows = (preview.positions || []).map((p) => `<tr>
    <td class="ar-ticker">${esc(p.ticker)}</td><td class="ar-num">${qty(p.quantity)}</td>
    <td class="ar-num">${price(p.average_price)}</td></tr>`).join("");
  const rejected = (preview.rejected || []).map((item) => `<li>${esc(item.market ? `${item.ticker || `Row ${item.row || "?"}`} [${item.market}]` : (item.ticker || `Row ${item.row || "?"}`))}: ${esc(item.reason)}</li>`).join("");
  const excluded = (preview.excluded || []).map((item) => `<li>${esc(item.market ? `${item.ticker || `Row ${item.row || "?"}`} [${item.market}]` : (item.ticker || `Row ${item.row || "?"}`))}: ${esc(item.reason)}</li>`).join("");
  const issues = (preview.issues || []).map((issue) => `<li>${esc(issue)}</li>`).join("");
  const warnings = (preview.warnings || []).map((warning) => `<li>${esc(warning)}</li>`).join("");
  body.innerHTML = `<p><strong>${esc(preview.account_label || "Selected account")}</strong> · Snapshot ${esc(preview.fetched_at || "time unavailable")} · ${preview.position_count} rows · ${preview.currency ? `currency ${esc(preview.currency)}` : "currency unavailable"} · cash ${esc(moneyLevel(preview.cash))}</p>
    ${rows ? `<div class="ar-table-wrap"><table class="ar-table"><thead><tr><th>Ticker</th><th>Quantity</th><th>Average cost</th></tr></thead><tbody>${rows}</tbody></table></div>` : "<p>No supported positions in snapshot.</p>"}
    ${warnings.length || excluded.length ? `<div class="ar-callout ar-callout--warn"><strong>Stock-only import scope</strong><ul>${warnings}${excluded}</ul></div>` : ""}
    ${issues.length || rejected.length ? `<div class="ar-callout ar-callout--warn"><strong>Cannot apply this snapshot</strong><ul>${issues}${rejected}</ul></div>` : "<p class=\"ar-subtle\">All stock rows are supported.</p>"}`;
  $("#tigerReplace").checked = false;
  $("#tigerStockOnly").checked = false;
  $("#tigerEmpty").checked = false;
  syncTigerApply();
}

async function loadTigerAccounts() {
  const select = $("#tigerAccount");
  select.innerHTML = '<option value="">Loading authorized accounts…</option>';
  try {
    const data = await api("/api/tiger/accounts");
    select.innerHTML = '<option value="">Select an account…</option>' + (data.accounts || []).map((a) =>
      `<option value="${esc(a.account_key)}">${esc(a.label)} · ${esc(a.account_type)}${a.status ? ` · ${esc(a.status)}` : ""}</option>`).join("");
    if (!data.accounts?.length) select.innerHTML = '<option value="">No authorized accounts</option>';
  } catch (e) {
    select.innerHTML = '<option value="">Could not load accounts</option>';
    $("#tigerPreviewBody").textContent = e.message;
  }
}

$("#tigerImportOpen").addEventListener("click", async () => {
  state.tigerPreviewRequestId += 1;
  state.tigerPreview = null;
  $("#tigerPreviewBody").textContent = "Load an authorized Tiger account to preview positions.";
  $("#tigerReplaceWrap").classList.add("hidden");
  $("#tigerStockOnlyWrap").classList.add("hidden");
  $("#tigerEmptyWrap").classList.add("hidden");
  $("#tigerApply").disabled = true;
  $("#tigerImportModal").showModal();
  await loadTigerAccounts();
});
$("#tigerCancel").addEventListener("click", () => {
  state.tigerPreviewRequestId += 1;
  $("#tigerImportModal").close();
});
$("#tigerAccount").addEventListener("change", () => {
  state.tigerPreviewRequestId += 1;
  state.tigerPreview = null;
  $("#tigerReplace").checked = false;
  $("#tigerStockOnly").checked = false;
  $("#tigerEmpty").checked = false;
  $("#tigerPreviewBody").textContent = "Account changed. Fetch a new preview before applying.";
  syncTigerApply();
});
$("#tigerReplace").addEventListener("change", syncTigerApply);
$("#tigerStockOnly").addEventListener("change", syncTigerApply);
$("#tigerEmpty").addEventListener("change", syncTigerApply);
$("#tigerFetch").addEventListener("click", async () => {
  const account_key = $("#tigerAccount").value;
  if (!account_key) { showToast("Select an authorized Tiger account first.", "warn"); return; }
  const requestId = ++state.tigerPreviewRequestId;
  state.tigerPreview = null;
  $("#tigerPreviewBody").textContent = "Fetching read-only positions and cash…";
  $("#tigerApply").disabled = true;
  try {
    const preview = await api("/api/tiger/preview", { method: "POST", body: JSON.stringify({ account_key }) });
    if (!globalThis.argusTigerPreviewIsCurrent(requestId, state.tigerPreviewRequestId, account_key,
      $("#tigerAccount").value, preview.account_key, $("#tigerImportModal").open)) return;
    state.tigerPreview = preview;
    renderTigerPreview(preview);
  } catch (e) {
    if (!globalThis.argusTigerPreviewIsCurrent(requestId, state.tigerPreviewRequestId, account_key,
      $("#tigerAccount").value, account_key, $("#tigerImportModal").open)) return;
    $("#tigerPreviewBody").textContent = e.message;
    showToast(e.message, "danger");
  }
});
$("#tigerApply").addEventListener("click", async () => {
  const preview = state.tigerPreview;
  if (!preview || !$("#tigerReplace").checked) return;
  if (!$("#tigerStockOnly").checked) return;
  if (preview.positions.length === 0 && !$("#tigerEmpty").checked) return;
  const button = $("#tigerApply");
  button.disabled = true;
  try {
    const result = await api("/api/tiger/apply", { method: "POST", body: JSON.stringify({
      preview_id: preview.preview_id, confirm: true, confirm_empty: $("#tigerEmpty").checked,
      confirm_stock_only: true,
    }) });
    $("#tigerImportModal").close();
    showToast(result.backup ? `Portfolio replaced. Backup saved as ${result.backup}.` : "Portfolio created from the reviewed Tiger snapshot.", "ok");
    await loadPortfolio();
  } catch (e) {
    showToast(e.message, "danger");
    syncTigerApply();
  }
});

/* ---------- watchlist ---------- */
async function loadWatchlist() {
  const data = await api("/api/watchlist");
  state.watchlist = data.items || [];
  const sub = $("#wlSubTable tbody");
  if (sub) {
    sub.innerHTML = (data.subthemes || []).map((b) => {
      const names = (b.tickers || []).map((t) => t.ticker).join(", ") || "—";
      return `<tr><td>${esc(b.label || b.id)}</td><td class="ar-mono">${esc(names)}</td><td class="ar-num">${b.count || 0}</td></tr>`;
    }).join("");
  }
  const tb = $("#wlTable tbody");
  tb.innerHTML = state.watchlist.map((it) => `
    <tr>
      <td class="ar-ticker">${esc(it.ticker)}</td>
      <td>${esc(it.sector || "")}</td>
      <td>${esc(it.type || "")}</td>
      <td class="ar-subtle">${esc(it.sub_theme || "")}</td>
      <td class="ar-actions"><button type="button" class="ar-btn ar-btn--sm ar-btn--danger" data-rm="${esc(it.ticker)}" aria-label="Remove ${esc(it.ticker)}" data-tooltip="Remove ${esc(it.ticker)}">${iconSvg("trash-2")}<span class="ar-btn__label">Remove</span></button></td>
    </tr>`).join("") || `<tr><td colspan="5" class="ar-subtle">Empty watchlist</td></tr>`;
}

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
        sub_theme: $("#wlSub").value,
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
  renderReportList();
  try {
    const data = await api(`/api/reports/${encodeURIComponent(item.dataset.id)}`);
    $("#repTitle").textContent = data.meta.ticker;
    $("#repMeta").innerHTML = `${data.meta.rating ? `${ratingMarkup(data.meta.rating)} · ` : ""}
      analysis ${esc(data.meta.analysis_date || "—")} · generated ${esc(data.meta.generated || "—")}`;
    renderMarkdown($("#repMd"), data.markdown || "");
  } catch (err) {
    showToast(err.message, "danger");
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
          <div class="ar-list__meta">${esc([h.kind, h.has_json && "json", h.has_stats && "stats"].filter(Boolean).join(" · "))}</div>
        </div>
      </div>`).join("") || `<div class="ar-muted">No history</div>`;
  }
  $("#fmSub").textContent = data.path ? `Plan ${data.path}` : "No fund manager output yet";
  const trades = data.trades || [];
  $("#fmTrades tbody").innerHTML = trades.map((t) => `
    <tr>
      <td class="ar-ticker">${esc(t.ticker)}</td>
      <td class="${actionClass(t.action)}">${esc(t.action)}</td>
      <td class="ar-num">${t.shares == null || t.shares === "" ? "—" : qty(t.shares)}</td>
      <td class="ar-num">${price(t.calc_price ?? t.est_price)}</td>
      <td>${ratingMarkup(t.agent_rating)}</td>
      <td class="ar-subtle">${esc(t.follows_agent || "")}</td>
      <td class="ar-wrap ar-subtle">${esc((t.rationale || "").slice(0, 160))}${(t.rationale || "").length > 160 ? "…" : ""}</td>
    </tr>`).join("") || `<tr><td colspan="7" class="ar-subtle">No trades in this run</td></tr>`;

  const d = data.decision || {};
  const summary = d.decision_summary || d.diagnosis || "";
  const warns = (data.warnings || []).map((w) => `<li>${esc(w)}</li>`).join("");
  const cash = d.cash_decision || data.cash_decision || {};
  $("#fmSummary").innerHTML = `
    <p><strong>${esc(d.headline || "—")}</strong></p>
    <p>${summary ? esc(summary) : "<span class='ar-muted'>No summary field</span>"}</p>
    <p class="ar-subtle">Confidence: ${esc(d.confidence ?? "—")}
      ${cash.target_cash_pct != null ? ` · target cash ${esc(cash.target_cash_pct)}%` : ""}
      ${data.ending_cash != null ? ` · post-trade cash ${moneyLevel(data.ending_cash)} (${esc(data.ending_cash_pct)}%)` : ""}</p>
    ${warns ? `<ul>${warns}</ul>` : ""}`;
  renderMarkdown($("#fmMd"), data.markdown || "");
}

$("#fmDate").addEventListener("change", (e) => loadFund(e.target.value).catch((err) => showToast(err.message, "danger")));
$("#fmHistory").addEventListener("click", (e) => {
  const it = e.target.closest("[data-path]");
  if (!it) return;
  $("#fmDate").value = it.dataset.path;
  loadFund(it.dataset.path).catch((err) => showToast(err.message, "danger"));
});

/* ---------- runs ---------- */
async function loadRuns() {
  const cfg = await api("/api/config");
  state.flags = cfg.flags || {};
  $("#optWlWrap").classList.toggle("hidden", !state.flags.IncludeWatchlist);

  const [book, wl, runs, spend] = await Promise.all([
    api("/api/portfolio"),
    api("/api/watchlist"),
    api("/api/runs"),
    api("/api/spend"),
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
    const text = `This week ${moneyCost(spent)} of ${moneyCost(budget)}${extra}`;
    spendEl.textContent = text;
    spendEl.classList.toggle("is-over", budget > 0 && spent >= budget);
  }
  state.bookTickers = (book.positions || []).map((p) => p.ticker);
  state.watchlist = wl.items || [];
  state.runs = runs.runs || [];
  buildTickerGrid();
  renderRunList();
  updateRunWarn();
}

function buildTickerGrid() {
  const selected = new Set($$("#tickerGrid input:checked").map((i) => i.value));
  const all = [];
  state.bookTickers.forEach((t) => all.push({ t, g: "book" }));
  state.watchlist.forEach((w) => {
    if (!all.find((x) => x.t === w.ticker)) all.push({ t: w.ticker, g: "watch", sector: w.sector });
  });
  $("#tickerGrid").innerHTML = all.map(({ t, g, sector }) => `
    <label class="ar-check ar-ticker-chip ${selected.has(t) ? "on" : ""}">
      <input type="checkbox" value="${esc(t)}" ${selected.has(t) ? "checked" : ""} />
      <span><strong>${esc(t)}</strong><br/><span class="ar-subtle">${g === "book" ? "book" : esc(sector || "watch")}</span></span>
    </label>`).join("");
  $$("#tickerGrid input").forEach((inp) => {
    inp.addEventListener("change", () => {
      inp.closest(".ar-ticker-chip").classList.toggle("on", inp.checked);
      updateRunWarn();
    });
  });
}

function selectedTickers() {
  return $$("#tickerGrid input:checked").map((i) => i.value);
}

function updateRunWarn() {
  const agents = $("#optRunAgents").checked;
  const watchAgents = $("#optWatchlist").checked;
  const nollm = $("#optNoLLM").checked;
  const selected = selectedTickers();
  const hasSelection = selected.length > 0;
  const selectedSet = new Set(selected);
  const bookCount = hasSelection ? state.bookTickers.filter((t) => selectedSet.has(t)).length : state.bookTickers.length;
  const watchCount = hasSelection ? state.watchlist.filter((w) => selectedSet.has(w.ticker)).length : state.watchlist.length;
  const n = (agents ? bookCount : 0) + (watchAgents ? watchCount : 0);
  let msg;
  if (nollm) {
    msg = "Snapshot only (-NoLLM): no model calls, free, usually under a minute. Watchlist agent runs are also suppressed.";
  } else if (n > 0) {
    msg = `Agent runs: ~${n} ticker(s) × ~2.5 min ≈ ${Math.round(n * 2.5)} minutes, plus OpenRouter fees. The fund manager step after that is 5 calls.`;
  } else {
    msg = "Fund manager only: 5 calls (draft, aggressive, conservative, neutral, final), about 9 minutes. Conservative is Opus; neutral is Luna. The last committee with that Opus seat was about $1.20.";
  }
  $("#runWarnText").textContent = msg;
}

["optRunAgents", "optNoLLM", "optWatchlist"].forEach((id) => $(`#${id}`).addEventListener("change", updateRunWarn));

$("#selBook").addEventListener("click", () => {
  $$("#tickerGrid input").forEach((i) => {
    i.checked = state.bookTickers.includes(i.value);
    i.closest(".ar-ticker-chip").classList.toggle("on", i.checked);
  });
  updateRunWarn();
});
$("#selWatch").addEventListener("click", () => {
  const w = new Set(state.watchlist.map((x) => x.ticker));
  $$("#tickerGrid input").forEach((i) => {
    i.checked = w.has(i.value);
    i.closest(".ar-ticker-chip").classList.toggle("on", i.checked);
  });
  updateRunWarn();
});
$("#selNone").addEventListener("click", () => {
  $$("#tickerGrid input").forEach((i) => { i.checked = false; i.closest(".ar-ticker-chip").classList.remove("on"); });
  updateRunWarn();
});
$("#selEtfs").addEventListener("click", () => {
  const etfs = new Set(state.watchlist.filter((x) => x.type === "etf").map((x) => x.ticker));
  $$("#tickerGrid input").forEach((i) => {
    i.checked = etfs.has(i.value);
    i.closest(".ar-ticker-chip").classList.toggle("on", i.checked);
  });
  updateRunWarn();
});

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

$("#btnStartRun").addEventListener("click", () => {
  const body = {
    run_agents: $("#optRunAgents").checked,
    no_llm: $("#optNoLLM").checked,
    include_risk: $("#optRisk").checked,
    no_macro: $("#optNoMacro").checked,
    include_watchlist: $("#optWatchlist").checked,
    analysis_date: $("#optDate").value || "",
    since: $("#optSince").value || "",
    tickers: selectedTickers(),
    confirm: false,
  };
  const selected = body.tickers.length ? new Set(body.tickers) : null;
  const countMatching = (values) => selected ? values.filter((v) => selected.has(v)).length : values.length;
  const n = (body.run_agents ? countMatching(state.bookTickers) : 0)
    + (body.include_watchlist ? countMatching(state.watchlist.map((w) => w.ticker)) : 0);
  let est;
  if (body.no_llm) est = "under ~1 min, free (all model stages suppressed)";
  else if (n) est = `~${Math.round(n * 2.5)} min + model fees, then 5 fund-manager calls`;
  else est = "~9 min, 5 model calls (Opus for conservative, Luna for neutral)";
  state.pendingTheme = null;
  state.pendingRemove = null;
  state.pendingRun = body;
  $("#confirmText").textContent = `Start this run? Estimate: ${est}. Tickers: ${body.tickers.length ? body.tickers.join(", ") : "(default / none)"}.`;
  openConfirm();
});

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
  if (closingFromConfirm) return;
  state.pendingRun = null;
  state.pendingTheme = null;
  state.pendingRemove = null;
  state.pendingAgentSave = false;
});
$("#confirmConsent").addEventListener("change", (e) => {
  if (!$("#confirmConsentWrap").classList.contains("hidden")) $("#confirmGo").disabled = !e.target.checked;
});

$("#confirmGo").addEventListener("click", async () => {
  const theme = state.pendingTheme ? { ...state.pendingTheme, confirm: true } : null;
  const saveAgents = state.pendingAgentSave;
  const body = !theme && !saveAgents && state.pendingRun ? { ...state.pendingRun, confirm: true } : null;
  const remove = state.pendingRemove;
  state.pendingTheme = null;
  state.pendingRun = null;
  state.pendingRemove = null;
  state.pendingAgentSave = false;
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
  const when = formatSessionDate(data.date);
  $("#themeAsOf").textContent = when ? `As of ${when}` : "No report yet";
  $("#themeSub").textContent = data.model_skipped === false
    ? "Weekly scout included the Sol call"
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
}

function queueThemeRun(mode) {
  const includeLlm = mode === "weekly" && $("#optScoutLlm").checked;
  state.pendingRun = null;
  state.pendingRemove = null;
  state.pendingTheme = { mode, include_llm: includeLlm, confirm: false };
  const est = mode === "screen"
    ? "Daily screen is free and does not edit the watchlist. A few minutes of price and earnings lookups."
    : (includeLlm
      ? "Weekly scout: one Sol call, about $0.10–$0.30. Shadow mode writes a proposal and does not edit the watchlist."
      : "Weekly pack without the Sol call. Free. The watchlist is not edited.");
  $("#confirmText").textContent = est;
  openConfirm();
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

function moneyLevel(n) {
  const v = Number(n);
  if (!Number.isFinite(v)) return null;
  const digits = Math.abs(v) >= 0.01 ? 2 : 4;
  const body = v.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
  return "$" + body;
}

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
