/* Argus frontend */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

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
  logOffset: 0,
  logTimer: null,
  chart: null,
  bookTickers: [],
  pendingRun: null,
  token: null,
};

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;",
  }[c]));
}

function renderMarkdown(el, md) {
  if (!md) {
    el.innerHTML = "<p class='muted'>No markdown report</p>";
    return;
  }
  if (!window.marked || !window.DOMPurify) {
    el.textContent = md;
    return;
  }
  el.innerHTML = DOMPurify.sanitize(marked.parse(md), { USE_PROFILES: { html: true } });
}

function money(n) {
  if (n == null || Number.isNaN(n)) return "—";
  return n.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 });
}
function money2(n) {
  if (n == null || Number.isNaN(n)) return "—";
  return n.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 2 });
}
function pct(n, d = 1) {
  if (n == null || Number.isNaN(n)) return "—";
  return `${Number(n).toFixed(d)}%`;
}
function ratingClass(r) {
  const x = (r || "").toLowerCase();
  if (x.includes("buy") || x.includes("overweight")) return "buy";
  if (x.includes("underweight") || x.includes("sell")) return "sell";
  return "hold";
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

/* ---------- tabs ---------- */
function setTab(name) {
  state.tab = name;
  $$(".nav button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  $$(".tab").forEach((t) => t.classList.toggle("hidden", t.id !== `tab-${name}`));
  if (name === "portfolio") loadPortfolio();
  if (name === "watchlist") loadWatchlist();
  if (name === "reports") loadReports();
  if (name === "fund") loadFund();
  if (name === "runs") loadRuns();
}

$("#nav").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-tab]");
  if (b) setTab(b.dataset.tab);
});

/* ---------- health ---------- */
async function loadHealth() {
  try {
    const h = await api("/api/health");
    state.flags = h.flags || {};
    $("#healthPill").textContent = h.data_ok ? "connected" : "data missing";
    $("#optWlWrap").classList.toggle("hidden", !state.flags.IncludeWatchlist);
  } catch (e) {
    $("#healthPill").textContent = "offline";
  }
}

/* ---------- portfolio ---------- */
async function loadPortfolio() {
  const data = await api("/api/portfolio");
  state.portfolio = data;
  state.bookTickers = (data.positions || []).map((p) => p.ticker);
  let asOf = data.prices_as_of
    ? `prices as of ${data.prices_as_of}`
    : "cost basis only (no stats yet)";
  if (data.book_newer_than_stats) asOf += " · book is newer than these prices";
  $("#pfAsOf").textContent = asOf;
  $("#pfSub").textContent = data.total_market_value != null
    ? `NAV ${money(data.total_market_value)} · cash ${money(data.cash)}`
    : `Cash ${money(data.cash)} · mark prices when a fund-manager stats file exists`;

  const pnl = data.account?.unrealized_pnl;
  $("#pfCards").innerHTML = `
    <div class="card"><div class="label">Total value</div><div class="value">${money(data.total_market_value)}</div><div class="hint">invested + cash</div></div>
    <div class="card"><div class="label">Cash</div><div class="value">${money(data.cash)}</div><div class="hint">${pct(data.cash_pct)} · target ${pct(data.cash_target_pct, 0)}</div></div>
    <div class="card"><div class="label">Unrealized P&amp;L</div><div class="value ${pnl >= 0 ? "pos" : "neg"}">${money(pnl)}</div><div class="hint">vs cost basis</div></div>
    <div class="card"><div class="label">Positions</div><div class="value">${data.positions.length}</div><div class="hint">currency ${data.currency || "USD"}</div></div>
  `;

  const tb = $("#pfTable tbody");
  tb.innerHTML = data.positions.map((p) => {
    const pnlCls = (p.unrealized_pnl ?? 0) >= 0 ? "pos" : "neg";
    return `<tr>
      <td class="mono"><strong>${esc(p.ticker)}</strong></td>
      <td class="muted">${esc(p.name || "")}</td>
      <td class="muted">${esc(p.sub_theme || "")}</td>
      <td class="num">${p.quantity}</td>
      <td class="num">${money2(p.average_price)}</td>
      <td class="num">${money2(p.price)}</td>
      <td class="num">${money(p.market_value)}</td>
      <td class="num ${pnlCls}">${money(p.unrealized_pnl)} <span class="muted">${p.unrealized_pnl_pct != null ? `(${pct(p.unrealized_pnl_pct)})` : ""}</span></td>
      <td class="num">${pct(p.weight_pct)}</td>
      <td class="num muted">${p.target_pct != null ? pct(p.target_pct, 0) : "—"}</td>
    </tr>`;
  }).join("");

  renderWeightsChart(data);
  const note = $("#aiSubNote");
  if (note) {
    note.textContent = `Direct holding weight. Look-through warn cap is ${pct(data.ai_sleeve_cap_pct, 0)} (targets.json). SPY's sleeve fraction is not split into these rows.`;
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
  state.chart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        { label: "Current %", data: current, backgroundColor: "rgba(91,140,255,.75)" },
        { label: "Target %", data: target, backgroundColor: "rgba(61,214,198,.55)" },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { ticks: { color: "#8fa3c1" }, grid: { color: "rgba(255,255,255,.04)" } },
        y: { ticks: { color: "#8fa3c1" }, grid: { color: "rgba(255,255,255,.06)" }, title: { display: true, text: "% of NAV", color: "#8fa3c1" } },
      },
      plugins: { legend: { labels: { color: "#e8eef9" } } },
    },
  });
}

function renderSubthemeRows(rows, withValue) {
  return (rows || []).map((b) => {
    const names = (b.tickers || []).map((t) => t.weight_pct != null ? `${t.ticker} ${pct(t.weight_pct)}` : t.ticker).join(", ") || "—";
    const value = withValue ? `<td class="num">${money(b.market_value)}</td>` : `<td class="num">${b.count || 0}</td>`;
    const weight = withValue ? `<td class="num">${pct(b.weight_pct)}</td>` : "";
    return `<tr><td>${esc(b.label || b.id)}</td><td class="mono">${esc(names)}</td>${weight}${value}</tr>`;
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
      return `<tr><td>${esc(b.label || b.id)}</td><td class="mono">${esc(names)}</td><td class="num">${b.count || 0}</td></tr>`;
    }).join("");
  }
  const tb = $("#wlTable tbody");
  tb.innerHTML = state.watchlist.map((it) => `
    <tr>
      <td class="mono"><strong>${esc(it.ticker)}</strong></td>
      <td>${esc(it.sector || "")}</td>
      <td>${esc(it.type || "")}</td>
      <td class="muted">${esc(it.sub_theme || "")}</td>
      <td><button class="btn sm danger" data-rm="${esc(it.ticker)}">Remove</button></td>
    </tr>`).join("") || `<tr><td colspan="5" class="muted">Empty watchlist</td></tr>`;
}

$("#wlAdd").addEventListener("click", async () => {
  const err = $("#wlErr");
  err.classList.add("hidden");
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
    err.textContent = e.message;
    err.classList.remove("hidden");
  }
});

$("#wlTable").addEventListener("click", async (e) => {
  const t = e.target.getAttribute("data-rm");
  if (!t) return;
  if (!confirm(`Remove ${t} from watchlist?`)) return;
  await api(`/api/watchlist/${encodeURIComponent(t)}`, { method: "DELETE" });
  await loadWatchlist();
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
    return `<option value="${t}">${t}${r}</option>`;
  }).join("");
  sel.value = cur;
  renderReportList();
}

function renderReportList() {
  const filter = $("#repFilter").value;
  const items = state.reports.filter((r) => !filter || r.ticker === filter);
  $("#repList").innerHTML = items.map((r) => {
    const latest = state.latestByTicker[r.ticker]?.id === r.id;
    const rc = ratingClass(r.rating);
    return `<div class="list-item ${state.selectedReport === r.id ? "active" : ""}" data-id="${r.id}">
      <div>
        <div><strong class="mono">${r.ticker}</strong>
          ${r.rating ? `<span class="rating ${rc}">${r.rating}</span>` : ""}
          ${latest ? `<span class="muted">· latest</span>` : ""}
        </div>
        <div class="meta">${r.analysis_date || r.ymd || ""} · ${r.generated || r.stamp || r.id}</div>
      </div>
    </div>`;
  }).join("") || `<div class="muted">No reports yet</div>`;
}

$("#repFilter").addEventListener("change", renderReportList);
$("#repList").addEventListener("click", async (e) => {
  const item = e.target.closest("[data-id]");
  if (!item) return;
  state.selectedReport = item.dataset.id;
  renderReportList();
  const data = await api(`/api/reports/${encodeURIComponent(item.dataset.id)}`);
  $("#repTitle").textContent = data.meta.ticker;
  const rc = ratingClass(data.meta.rating);
  $("#repMeta").innerHTML = `${data.meta.rating ? `<span class="rating ${rc}">${data.meta.rating}</span> · ` : ""}
    analysis ${data.meta.analysis_date || "—"} · generated ${data.meta.generated || "—"}`;
  renderMarkdown($("#repMd"), data.markdown || "");
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
      <div class="list-item" data-path="${esc(h.path || h.date)}">
        <div><strong>${esc(h.path || h.date)}</strong>
          <div class="meta">${[h.kind, h.has_json && "json", h.has_stats && "stats"].filter(Boolean).join(" · ")}</div>
        </div>
      </div>`).join("") || `<div class="muted">No history</div>`;
  }
  $("#fmSub").textContent = data.path ? `Plan ${data.path}` : "No fund manager output yet";
  const trades = data.trades || [];
  $("#fmTrades tbody").innerHTML = trades.map((t) => `
    <tr>
      <td class="mono"><strong>${esc(t.ticker)}</strong></td>
      <td class="action ${esc((t.action || "").toLowerCase())}">${esc(t.action)}</td>
      <td class="num">${t.shares ?? "—"}</td>
      <td class="num">${money2(t.calc_price ?? t.est_price)}</td>
      <td><span class="rating ${ratingClass(t.agent_rating)}">${esc(t.agent_rating || "—")}</span></td>
      <td class="muted">${esc(t.follows_agent || "")}</td>
      <td class="muted">${esc((t.rationale || "").slice(0, 160))}${(t.rationale || "").length > 160 ? "…" : ""}</td>
    </tr>`).join("") || `<tr><td colspan="7" class="muted">No trades in this run</td></tr>`;

  const d = data.decision || {};
  const summary = d.decision_summary || d.diagnosis || "";
  const warns = (data.warnings || []).map((w) => `<li>${esc(w)}</li>`).join("");
  const cash = d.cash_decision || data.cash_decision || {};
  $("#fmSummary").innerHTML = `
    <p><strong>${esc(d.headline || "—")}</strong></p>
    <p>${summary ? esc(summary) : "<span class='muted'>No summary field</span>"}</p>
    <p class="muted">Confidence: ${esc(d.confidence ?? "—")}
      ${cash.target_cash_pct != null ? ` · target cash ${esc(cash.target_cash_pct)}%` : ""}
      ${data.ending_cash != null ? ` · post-trade cash ${money(data.ending_cash)} (${esc(data.ending_cash_pct)}%)` : ""}</p>
    ${warns ? `<ul>${warns}</ul>` : ""}`;
  renderMarkdown($("#fmMd"), data.markdown || "");
}

$("#fmDate").addEventListener("change", (e) => loadFund(e.target.value));
$("#fmHistory").addEventListener("click", (e) => {
  const it = e.target.closest("[data-path]");
  if (!it) return;
  $("#fmDate").value = it.dataset.path;
  loadFund(it.dataset.path);
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
    <label class="ticker-chip ${selected.has(t) ? "on" : ""}">
      <input type="checkbox" value="${t}" ${selected.has(t) ? "checked" : ""} />
      <span><strong class="mono">${t}</strong><br/><span class="muted">${g === "book" ? "book" : (sector || "watch")}</span></span>
    </label>`).join("");
  $$("#tickerGrid input").forEach((inp) => {
    inp.addEventListener("change", () => {
      inp.closest(".ticker-chip").classList.toggle("on", inp.checked);
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
  $("#runWarn").textContent = msg;
}

["optRunAgents", "optNoLLM"].forEach((id) => $(`#${id}`).addEventListener("change", updateRunWarn));

$("#selBook").addEventListener("click", () => {
  $$("#tickerGrid input").forEach((i) => {
    i.checked = state.bookTickers.includes(i.value);
    i.closest(".ticker-chip").classList.toggle("on", i.checked);
  });
  updateRunWarn();
});
$("#selWatch").addEventListener("click", () => {
  const w = new Set(state.watchlist.map((x) => x.ticker));
  $$("#tickerGrid input").forEach((i) => {
    i.checked = w.has(i.value);
    i.closest(".ticker-chip").classList.toggle("on", i.checked);
  });
  updateRunWarn();
});
$("#selNone").addEventListener("click", () => {
  $$("#tickerGrid input").forEach((i) => { i.checked = false; i.closest(".ticker-chip").classList.remove("on"); });
  updateRunWarn();
});
$("#selEtfs").addEventListener("click", () => {
  const etfs = new Set(state.watchlist.filter((x) => x.type === "etf").map((x) => x.ticker));
  $$("#tickerGrid input").forEach((i) => {
    i.checked = etfs.has(i.value);
    i.closest(".ticker-chip").classList.toggle("on", i.checked);
  });
  updateRunWarn();
});

function renderRunList() {
  $("#runList").innerHTML = state.runs.map((r) => `
    <div class="list-item ${state.selectedRun === r.id ? "active" : ""}" data-run="${r.id}">
      <div>
        <div><strong class="mono">${r.id}</strong> · <span class="${r.status === "succeeded" ? "pos" : r.status === "failed" ? "neg" : ""}">${r.status}</span></div>
        <div class="meta">${r.started_at || ""} · est ${r.estimate_minutes ?? "?"} min · tickers ${r.ticker_count ?? "?"}</div>
      </div>
    </div>`).join("") || `<div class="muted">No runs yet</div>`;
}

$("#runList").addEventListener("click", (e) => {
  const it = e.target.closest("[data-run]");
  if (!it) return;
  selectRun(it.dataset.run);
});

async function selectRun(id) {
  state.selectedRun = id;
  state.logOffset = 0;
  renderRunList();
  $("#runLog").textContent = "";
  if (state.logTimer) clearInterval(state.logTimer);
  await pollLog();
  state.logTimer = setInterval(pollLog, 1500);
}

async function pollLog() {
  if (!state.selectedRun) return;
  try {
    const data = await api(`/api/runs/${encodeURIComponent(state.selectedRun)}/log?from_byte=${state.logOffset}`);
    if (data.chunk) {
      $("#runLog").textContent += data.chunk;
      $("#runLog").scrollTop = $("#runLog").scrollHeight;
      state.logOffset = data.offset;
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
  state.pendingRun = body;
  $("#confirmText").textContent = `Start this run? Estimate: ${est}. Tickers: ${body.tickers.length ? body.tickers.join(", ") : "(default / none)"}.`;
  $("#confirmModal").classList.remove("hidden");
});

$("#confirmCancel").addEventListener("click", () => {
  state.pendingRun = null;
  $("#confirmModal").classList.add("hidden");
});

$("#confirmGo").addEventListener("click", async () => {
  const body = { ...state.pendingRun, confirm: true };
  $("#confirmModal").classList.add("hidden");
  try {
    const res = await api("/api/runs", { method: "POST", body: JSON.stringify(body) });
    state.pendingRun = null;
    await loadRuns();
    if (res.run?.id) selectRun(res.run.id);
  } catch (e) {
    alert(e.message);
  }
});

/* ---------- boot ---------- */
(async function boot() {
  try {
    const res = await fetch("/api/session");
    if (res.ok) state.token = (await res.json()).token;
  } catch (_) { /* runs will 401 until a session token loads */ }
  await loadHealth();
  setTab("portfolio");
})();
