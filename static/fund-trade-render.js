/* Pure fund-manager trade table renderer. Formatters are supplied by app.js. */
globalThis.argusRenderTradePolicy = function (policy, format) {
  if (!policy || typeof policy !== "object") return "";
  const fields = [policy.fee_per_order_usd, policy.min_buy_notional_usd, policy.min_residual_notional_usd];
  if (!fields.every((value) => typeof value === "number" && Number.isFinite(value))) return "";
  return `Trade policy: ${format.moneyLevel(fields[0])} per order; minimum buy ${format.moneyLevel(fields[1])}; residual guideline ${format.moneyLevel(fields[2])}`;
};

globalThis.argusRenderFundTrades = function (trades, format) {
  const esc = format.esc;
  const money = (value) => format.moneyLevel(value) ?? "—";
  const signedMoney = (value) => value < 0 ? `−${money(Math.abs(Number(value)))}` : money(value);
  const rows = Array.isArray(trades) ? trades : [];
  if (!rows.length) return '<tr><td colspan="15" class="ar-subtle">No trades in this run</td></tr>';
  return rows.map((t) => {
    const requested = t.requested_shares ?? t.proposed_shares ?? t.shares;
    const effective = t.effective_shares;
    const reason = [t.reason || t.validation_reason, t.availability_caveat].filter(Boolean).join(" · ");
    const rationale = t.sizing_rationale || t.rationale || "";
    return `<tr>
      <td>${esc(t.status || "—")}</td>
      <td>${esc(t.account_label || t.account || t.account_id || "—")}</td>
      <td class="ar-ticker">${esc(t.ticker)}</td>
      <td class="${format.actionClass(t.action)}">${esc(t.action)}</td>
      <td class="ar-num">${requested == null || requested === "" ? "—" : format.qty(requested)}</td>
      <td class="ar-num">${t.target_shares == null || t.target_shares === "" ? "—" : format.qty(t.target_shares)}</td>
      <td class="ar-num">${effective == null || effective === "" ? "—" : format.qty(effective)}</td>
      <td>${esc(t.execution_intent || "—")}</td>
      <td>${esc(t.review_horizon || "—")}</td>
      <td class="ar-num">${format.price(t.calc_price ?? t.est_price)}</td>
      <td class="ar-num">${t.estimated_fee_usd == null && t.fee_usd == null ? "—" : money(t.estimated_fee_usd ?? t.fee_usd)}</td>
      <td class="ar-num">${t.cash_delta_usd == null ? "—" : signedMoney(Number(t.cash_delta_usd))}</td>
      <td class="ar-wrap ar-subtle">${esc([reason, t.condition, t.change_reason].filter(Boolean).join(" · "))}</td>
      <td>${format.ratingMarkup(t.agent_rating)}</td>
      <td class="ar-wrap ar-subtle">${esc(rationale.slice(0, 160))}${rationale.length > 160 ? "…" : ""}</td>
    </tr>`;
  }).join("");
};

globalThis.argusRenderFundContext = function (context, coverage, positions, format) {
  const esc = format.esc;
  const value = (item) => item == null || item === "" ? "—" : esc(
    Array.isArray(item) && item.every((part) => typeof part !== "object") ? item.join(", ")
      : typeof item === "object" ? JSON.stringify(item) : item,
  );
  const noteList = (label, items) => Array.isArray(items) && items.length
    ? `<p><strong>${esc(label)}:</strong> ${items.map(value).join(" · ")}</p>`
    : "";
  const table = (headers, rows, fields, empty) => {
    if (!Array.isArray(rows) || !rows.length) return `<p class="ar-subtle">${esc(empty)}</p>`;
    return `<div class="ar-table-wrap"><table class="ar-table"><thead><tr>${headers.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${fields.map((field) => `<td class="ar-wrap">${value(typeof field === "function" ? field(row) : row?.[field])}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
  };
  const comparisons = context && Array.isArray(context.comparisons) ? context.comparisons : [];
  const contextSummary = context && typeof context === "object"
    ? `<p><strong>Prior review:</strong> ${value(context.baseline_status)}${context.prior_run_id ? ` · ${value(context.prior_run_id)}` : ""}${context.prior_report_date ? ` · ${value(context.prior_report_date)}` : ""}</p>`
    : `<p class="ar-subtle">No decision continuity fields in this report.</p>`;
  const priorSummary = context && typeof context === "object"
    ? `<div>${context.prior_decision_summary ? `<p><strong>Prior decision:</strong> ${value(context.prior_decision_summary)}</p>` : ""}${context.prior_cash_decision ? `<p><strong>Prior cash decision:</strong> ${value(context.prior_cash_decision)}</p>` : ""}${noteList("Prior objections", context.prior_objections)}${noteList("Prior changes versus draft", context.prior_changes_vs_draft)}</div>`
    : "";
  const comparisonTable = table(
    ["Account", "Ticker", "Observed now", "Previously observed", "Quantity change", "Prior proposal", "Prior target", "Prior intent", "Prior rationale / condition", "Prior validation", "Prior hypothetical", "Execution attribution", "Current research", "Research date"],
    comparisons,
    ["account_id", "ticker", "observed_shares", "prior_observed_shares", "quantity_change", "prior_proposed_shares", "prior_target_shares", "prior_intent",
      (row) => [row.prior_decision, row.prior_condition, row.prior_sizing_rationale, row.prior_change_reason].filter(Boolean).join(" · "),
      "prior_validation_status", "prior_effective_hypothetical_shares", "execution_attribution", "current_research_status", "current_research_date"],
    "No prior position comparisons in this report.",
  );
  const coverageTable = table(
    ["Ticker", "Disposition", "Research status", "Profile", "Evidence date", "Reason"],
    coverage,
    ["ticker", "disposition", "research_status", "source_profile", "evidence_date", "rationale"],
    "No candidate coverage details in this report.",
  );
  const positionTable = table(
    ["Account", "Ticker", "Observed shares", "Hypothetical after", "Target shares", "Target gap", "Position status", "Validation"],
    positions,
    ["account_id", "ticker", "observed_shares", "hypothetical_after_shares", "target_shares", "target_gap_shares", "position_status", "validation_status"],
    "No position results in this report.",
  );
  return `<div class="ar-stack">${contextSummary}${priorSummary}<h3 class="ar-h3">Prior review comparisons</h3>${comparisonTable}<h3 class="ar-h3">Candidate coverage</h3>${coverageTable}<h3 class="ar-h3">Position outcomes</h3>${positionTable}</div>`;
};
