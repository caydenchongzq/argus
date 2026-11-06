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
  token: null,
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
      <td class="ar-subtle">${esc(p.sub_theme || "")}</td>
      <td class="ar-num">${qty(p.quantity)}</td>
      <td class="ar-num">${price(p.average_price)}</td>
      <td class="ar-num">${price(p.price)}</td>
      <td class="ar-num">${moneyLevel(p.market_value)}</td>
      <td class="ar-num">${pnlCell}</td>
      <td class="ar-num">${pctLevel(p.weight_pct, 1)}</td>
      <td class="ar-num ar-subtle">${p.target_pct != null ? pctLevel(p.target_pct, 1) : "—"}</td>
    </tr>`;
  }).join("");

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

  const [book, wl, runs] = await Promise.all([
    api("/api/portfolio"),
    api("/api/watchlist"),
    api("/api/runs"),
  ]);
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
  const nollm = $("#optNoLLM").checked;
  const n = selectedTickers().length || (agents ? state.bookTickers.length : 0);
  let msg;
  if (nollm && !agents) {
    msg = "Snapshot only (-NoLLM): no model call, free, usually under a minute.";
  } else if (agents) {
    msg = `Agent runs: ~${n} ticker(s) × ~2.5 min ≈ ${Math.round(n * 2.5)} minutes, plus OpenRouter fees. The fund manager step after that is 5 calls.`;
  } else {
    msg = "Fund manager only: 5 calls (draft, aggressive, conservative, neutral, final), about 9 minutes. Conservative is Opus; neutral is Luna. The last committee with that Opus seat was about $1.20.";
  }
  $("#runWarnText").textContent = msg;
}

["optRunAgents", "optNoLLM"].forEach((id) => $(`#${id}`).addEventListener("change", updateRunWarn));

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
  const n = body.tickers.length || (body.run_agents ? state.bookTickers.length : 0);
  let est;
  if (body.no_llm && !body.run_agents) est = "under ~1 min, free";
  else if (body.run_agents) est = `~${Math.round(n * 2.5)} min + model fees, then 5 fund-manager calls`;
  else est = "~9 min, 5 model calls (Opus for conservative, Luna for neutral)";
  state.pendingTheme = null;
  state.pendingRemove = null;
  state.pendingRun = body;
  $("#confirmText").textContent = `Start this run? Estimate: ${est}. Tickers: ${body.tickers.length ? body.tickers.join(", ") : "(default / none)"}.`;
  openConfirm();
});

function isPendingPaid() {
  if (state.pendingRemove) return false;
  if (state.pendingTheme) return state.pendingTheme.mode === "weekly" && !!state.pendingTheme.include_llm;
  const b = state.pendingRun;
  if (!b) return false;
  return !(b.no_llm && !b.run_agents);
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
  if (state.pendingRemove) {
    $("#confirmTitle").textContent = "Remove from watchlist";
    $("#confirmCaption").textContent = "Writes data/watchlist.json after a backup.";
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
});
$("#confirmConsent").addEventListener("change", (e) => {
  if (!$("#confirmConsentWrap").classList.contains("hidden")) $("#confirmGo").disabled = !e.target.checked;
});

$("#confirmGo").addEventListener("click", async () => {
  const theme = state.pendingTheme ? { ...state.pendingTheme, confirm: true } : null;
  const body = !theme && state.pendingRun ? { ...state.pendingRun, confirm: true } : null;
  const remove = state.pendingRemove;
  state.pendingTheme = null;
  state.pendingRun = null;
  state.pendingRemove = null;
  closingFromConfirm = true;
  $("#confirmModal").close();
  closingFromConfirm = false;
  try {
    if (remove) {
      await api(`/api/watchlist/${encodeURIComponent(remove)}`, { method: "DELETE" });
      await loadWatchlist();
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
      ? "Weekly scout: one Sol call, about $0.10–$0.30, then a watchlist backup and update."
      : "Weekly pack without the Sol call. Free. The watchlist is not edited.");
  $("#confirmText").textContent = est;
  openConfirm();
}

$("#btnScreen").addEventListener("click", () => queueThemeRun("screen"));
$("#btnScout").addEventListener("click", () => queueThemeRun("weekly"));

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
