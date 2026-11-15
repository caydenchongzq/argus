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
  if (!rows.length) return '<tr><td colspan="12" class="ar-subtle">No trades in this run</td></tr>';
  return rows.map((t) => {
    const requested = t.requested_shares ?? t.proposed_shares ?? t.shares;
    const effective = t.effective_shares;
    const reason = [t.reason || t.validation_reason, t.availability_caveat].filter(Boolean).join(" · ");
    const rationale = t.rationale || "";
    return `<tr>
      <td>${esc(t.status || "—")}</td>
      <td>${esc(t.account_label || t.account || t.account_id || "—")}</td>
      <td class="ar-ticker">${esc(t.ticker)}</td>
      <td class="${format.actionClass(t.action)}">${esc(t.action)}</td>
      <td class="ar-num">${requested == null || requested === "" ? "—" : format.qty(requested)}</td>
      <td class="ar-num">${effective == null || effective === "" ? "—" : format.qty(effective)}</td>
      <td class="ar-num">${format.price(t.calc_price ?? t.est_price)}</td>
      <td class="ar-num">${t.estimated_fee_usd == null && t.fee_usd == null ? "—" : money(t.estimated_fee_usd ?? t.fee_usd)}</td>
      <td class="ar-num">${t.cash_delta_usd == null ? "—" : signedMoney(Number(t.cash_delta_usd))}</td>
      <td class="ar-wrap ar-subtle">${esc(reason)}</td>
      <td>${format.ratingMarkup(t.agent_rating)}</td>
      <td class="ar-wrap ar-subtle">${esc(rationale.slice(0, 160))}${rationale.length > 160 ? "…" : ""}</td>
    </tr>`;
  }).join("");
};
