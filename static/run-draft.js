/* Pure draft model and adapters for the six existing Argus run scenarios. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.ArgusRunDraft = api;
})(typeof globalThis === "object" ? globalThis : this, function () {
  "use strict";

  const SECTORS = Object.freeze([
    Object.freeze({ ticker: "XLK", label: "Information Technology" }),
    Object.freeze({ ticker: "XLY", label: "Consumer Cyclical" }),
    Object.freeze({ ticker: "XLV", label: "Healthcare" }),
    Object.freeze({ ticker: "XLP", label: "Consumer Defensive" }),
    Object.freeze({ ticker: "XLU", label: "Utilities" }),
    Object.freeze({ ticker: "XLE", label: "Energy" }),
    Object.freeze({ ticker: "XLF", label: "Financial Services" }),
    Object.freeze({ ticker: "SMH", label: "Semiconductors" }),
  ]);
  const SECTOR_IDS = new Set(SECTORS.map((sector) => sector.ticker));
  const MODES = Object.freeze({
    snapshot: Object.freeze({ title: "Refresh prices & portfolio metrics", description: "Update prices and calculated portfolio statistics from your saved holdings. No AI review or broker import.", paid: false, output: "Quantitative portfolio snapshot" }),
    screen: Object.freeze({ title: "Screen the market", description: "Refresh the market screen across selected discovery sectors. Your watchlist stays unchanged.", paid: false, output: "Market screen and relative-strength data in Themes" }),
    scout: Object.freeze({ title: "Find watchlist ideas", description: "Refresh the screen, then ask the scout for watchlist suggestions. Review and apply suggestions separately.", paid: true, output: "Dated scout report and proposal in Themes" }),
    analyze: Object.freeze({ title: "Research selected tickers", description: "Create fresh research reports for the names you choose. Skip the portfolio review.", paid: true, output: "Fresh reports for selected tickers" }),
    "analyze-review": Object.freeze({ title: "Research + portfolio review", description: "Refresh your selected ticker reports, then review the whole portfolio using fresh and saved research.", paid: true, output: "Selected research reports and whole-portfolio advisory review" }),
    fund: Object.freeze({ title: "Review portfolio", description: "Ask the fund manager to review your holdings and saved watchlist using existing ticker reports. No fresh ticker research.", paid: true, output: "Advisory portfolio review" }),
  });
  const RESEARCH_MODES = new Set(["analyze", "analyze-review"]);
  const PORTFOLIO_MODES = new Set(["fund", "analyze-review"]);
  const DISCOVERY_MODES = new Set(["screen", "scout"]);

  const normalize = (ticker) => String(ticker ?? "").trim().toUpperCase();
  const unique = (values) => [...new Set((Array.isArray(values) ? values : []).map(normalize).filter(Boolean))];
  const next = (draft, patch) => ({ ...draft, ...patch, revision: (Number(draft.revision) || 0) + 1 });

  function create() {
    return {
      mode: "snapshot",
      tickers: [],
      tickerSources: {},
      sectors: SECTORS.map((sector) => sector.ticker),
      dateMode: "auto",
      date: "",
      includeEconomicData: true,
      since: "",
      scoutIncludeLlm: true,
      revision: 0,
    };
  }

  function setMode(draft, mode) {
    if (!Object.prototype.hasOwnProperty.call(MODES, mode)) return { ...draft };
    return draft.mode === mode ? { ...draft } : next(draft, { mode });
  }

  function setTickerSelection(draft, tickers, eligibility) {
    const selected = unique(tickers);
    const rows = eligibility || {};
    const sources = {};
    selected.forEach((ticker) => {
      const group = rows[ticker];
      if (group === "holding" || group === "candidate") sources[ticker] = group;
    });
    return next(draft, { tickers: selected, tickerSources: sources });
  }

  function mergeTickerSelection(draft, tickers, eligibility) {
    const selected = new Set(draft.tickers || []);
    const sources = { ...(draft.tickerSources || {}) };
    (Array.isArray(tickers) ? tickers : []).map(normalize).filter(Boolean).forEach((ticker) => {
      selected.add(ticker);
      const group = eligibility?.[ticker];
      if (group === "holding" || group === "candidate") sources[ticker] = group;
    });
    return next(draft, { tickers: [...selected], tickerSources: sources });
  }

  function toggleTicker(draft, ticker, group) {
    const name = normalize(ticker);
    if (!name) return { ...draft };
    const selected = new Set(draft.tickers || []);
    const sources = { ...(draft.tickerSources || {}) };
    if (selected.has(name)) {
      selected.delete(name);
      delete sources[name];
    } else {
      selected.add(name);
      if (group === "holding" || group === "candidate") sources[name] = group;
    }
    return next(draft, { tickers: [...selected], tickerSources: sources });
  }

  function setSectors(draft, sectors) {
    return next(draft, { sectors: unique(sectors).filter((sector) => SECTOR_IDS.has(sector)) });
  }

  function toggleSector(draft, sector) {
    const ticker = normalize(sector);
    if (!SECTOR_IDS.has(ticker)) return { ...draft };
    const selected = new Set(draft.sectors || []);
    if (selected.has(ticker)) selected.delete(ticker);
    else selected.add(ticker);
    return setSectors(draft, [...selected]);
  }

  function setOptions(draft, patch) {
    const allowed = {};
    if (Object.prototype.hasOwnProperty.call(patch, "dateMode")) allowed.dateMode = patch.dateMode === "custom" ? "custom" : "auto";
    if (Object.prototype.hasOwnProperty.call(patch, "date")) allowed.date = String(patch.date || "");
    if (Object.prototype.hasOwnProperty.call(patch, "includeEconomicData")) allowed.includeEconomicData = Boolean(patch.includeEconomicData);
    if (Object.prototype.hasOwnProperty.call(patch, "since")) allowed.since = String(patch.since || "");
    if (Object.prototype.hasOwnProperty.call(patch, "scoutIncludeLlm")) allowed.scoutIncludeLlm = Boolean(patch.scoutIncludeLlm);
    return next(draft, allowed);
  }

  function researchEligibility(draft, eligibility) {
    const rows = eligibility || {};
    const selected = unique(draft.tickers);
    const missing = selected.filter((ticker) => !rows[ticker]);
    const changed = selected.filter((ticker) => rows[ticker]
      && draft.tickerSources?.[ticker] && draft.tickerSources[ticker] !== rows[ticker]
      && (draft.tickerSources[ticker] === "holding" || draft.tickerSources[ticker] === "candidate"));
    return { missing, changed };
  }

  function isCalendarDate(value) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(String(value || ""))) return false;
    const [year, month, day] = value.split("-").map(Number);
    const date = new Date(Date.UTC(year, month - 1, day));
    return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day;
  }

  function validate(draft, eligibility) {
    const errors = [];
    if (RESEARCH_MODES.has(draft.mode)) {
      if (!draft.tickers?.length) errors.push({ field: "tickers", message: "Choose at least one ticker to research." });
      const changed = researchEligibility(draft, eligibility);
      if (changed.missing.length || changed.changed.length) {
        const names = [
          ...changed.missing.map((ticker) => `${ticker} is no longer eligible`),
          ...changed.changed.map((ticker) => `${ticker} changed from ${draft.tickerSources[ticker]} to ${eligibility[ticker]}`),
        ];
        errors.push({ field: "tickers", message: `Review the changed ticker scope: ${names.join("; ")}. Uncheck and reselect any name to confirm its current scope.` });
      }
    }
    if (DISCOVERY_MODES.has(draft.mode) && (draft.sectors?.length < 1 || draft.sectors?.length > 8)) {
      errors.push({ field: "sectors", message: "Choose between one and eight discovery sectors." });
    }
    if (!DISCOVERY_MODES.has(draft.mode) && draft.dateMode === "custom" && !isCalendarDate(draft.date)) {
      errors.push({ field: "date", message: "Choose a valid market date or switch to Automatic." });
    }
    return errors;
  }

  function request(draft, eligibility) {
    const errors = validate(draft, eligibility);
    if (errors.length) return { errors };
    if (DISCOVERY_MODES.has(draft.mode)) {
      const includeLlm = draft.mode === "scout" && Boolean(draft.scoutIncludeLlm);
      return {
        family: "theme-scout",
        body: {
          mode: draft.mode === "screen" ? "screen" : "weekly",
          include_llm: includeLlm,
          sectors: [...draft.sectors],
          single_call: includeLlm,
          confirm: false,
        },
        errors: [],
      };
    }
    const selected = RESEARCH_MODES.has(draft.mode) ? unique(draft.tickers) : [];
    const usesEconomicData = draft.mode === "snapshot" || PORTFOLIO_MODES.has(draft.mode);
    const body = {
      run_agents: selected.some((ticker) => eligibility[ticker] === "holding"),
      analysis_only: draft.mode === "analyze",
      no_llm: draft.mode === "snapshot",
      include_risk: false,
      no_macro: usesEconomicData ? !draft.includeEconomicData : false,
      include_watchlist: selected.some((ticker) => eligibility[ticker] === "candidate"),
      analysis_date: draft.dateMode === "custom" ? draft.date : "",
      since: PORTFOLIO_MODES.has(draft.mode) ? String(draft.since || "") : "",
      tickers: selected,
      confirm: false,
    };
    return { family: "runs", body, errors: [] };
  }

  function selectedSourceChanges(draft, eligibility) {
    return researchEligibility(draft, eligibility);
  }

  return Object.freeze({
    modes: MODES,
    sectors: SECTORS,
    create,
    setMode,
    setTickerSelection,
    mergeTickerSelection,
    toggleTicker,
    setSectors,
    toggleSector,
    setOptions,
    validate,
    request,
    selectedSourceChanges,
    isResearch: (mode) => RESEARCH_MODES.has(mode),
    isPortfolioReview: (mode) => PORTFOLIO_MODES.has(mode),
    isDiscovery: (mode) => DISCOVERY_MODES.has(mode),
  });
});
