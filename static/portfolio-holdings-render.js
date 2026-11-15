/* Pure portfolio holdings renderer shared by the account filter and fixtures. */
globalThis.argusRenderPortfolioAccounts = function (accounts, format) {
  const rows = Array.isArray(accounts) ? accounts : [];
  if (!rows.length) return '<tr><td colspan="6" class="ar-subtle">No account breakdown available.</td></tr>';
  return rows.map((account) => {
    const cash = account.cash_known === false || account.cash == null ? "Unknown" : format.moneyLevel(account.cash);
    const total = account.total_market_value ?? account.total_value ?? null;
    const holdings = account.holdings_value_complete === false
      ? `Partial ${format.moneyLevel(account.holdings_value)}` : format.moneyLevel(account.holdings_value);
    const asOf = account.fetched_at || account.updated_at || account.snapshot_at || "—";
    return `<tr><td>${format.esc(account.label || account.account_label || account.account_id || "Account")}</td><td>${format.esc(account.broker || "Legacy")}</td><td class="ar-num">${format.esc(holdings)}</td><td class="ar-num">${format.esc(cash)}</td><td class="ar-num">${format.moneyLevel(total)}</td><td>${format.esc(asOf)}</td></tr>`;
  }).join("");
};

globalThis.argusRenderPortfolioHoldings = function (data, accountId, format) {
  const aggregate = Array.isArray(data.positions) ? data.positions : [];
  const scoped = accountId && accountId !== "all";
  const rows = scoped ? aggregate.flatMap((position) => {
    const detail = (position.account_positions || position.accounts || [])
      .find((accountPosition) => accountPosition.account_id === accountId);
    if (!detail) return [];
    const quantity = detail.quantity;
    const average = detail.average_price ?? null;
    const price = detail.price ?? position.price ?? null;
    const marketValue = detail.market_value ?? (quantity != null && price != null ? Number(quantity) * Number(price) : null);
    const pnl = detail.unrealized_pnl ?? (average != null && price != null && quantity != null
      ? (Number(price) - Number(average)) * Number(quantity) : null);
    const pnlPct = detail.unrealized_pnl_pct ?? (pnl != null && average
      ? (Number(price) / Number(average) - 1) * 100 : null);
    return [{
      ...position,
      quantity,
      average_price: average,
      price,
      market_value: marketValue,
      unrealized_pnl: pnl,
      unrealized_pnl_pct: pnlPct,
      weight_pct: detail.weight_pct ?? null,
      sellable_quantity: detail.sellable_quantity ?? null,
    }];
  }) : aggregate;

  if (!rows.length) return '<tr><td colspan="12" class="ar-subtle">No holdings in this account</td></tr>';
  return rows.map((position) => {
    const change = format.moneyChange(position.unrealized_pnl, true);
    const percent = format.pctChange(position.unrealized_pnl_pct, 2);
    const pnl = change
      ? `${format.deltaHtml(change)}${percent ? ` ${format.deltaHtml(percent)}` : ""}`
      : '<span class="ar-subtle">—</span>';
    return `<tr class="${position.price == null ? "is-stale" : ""}">
      <td class="ar-ticker">${format.esc(position.ticker)}</td>
      <td class="ar-subtle">${format.esc(position.name || "")}</td>
      <td>${format.esc(position.instrument_type || "Unknown")}</td>
      <td>${format.esc(position.sleeve === "core_etf" ? "ETF" : position.sleeve === "swing" ? "Stock / cash" : "Unclassified")}</td>
      <td class="ar-num">${format.qty(position.quantity)}</td>
      <td class="ar-num">${scoped ? format.qty(position.sellable_quantity) : "—"}</td>
      <td class="ar-num">${format.price(position.average_price)}</td>
      <td class="ar-num">${format.price(position.price)}</td>
      <td class="ar-num">${format.moneyLevel(position.market_value)}</td>
      <td class="ar-num">${pnl}</td>
      <td class="ar-num">${format.pctLevel(position.weight_pct, 1)}</td>
      <td class="ar-num ar-subtle">${position.target_pct != null ? format.pctLevel(position.target_pct, 1) : "—"}</td>
    </tr>`;
  }).join("");
};
