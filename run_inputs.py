"""Fingerprints for portfolio inputs that a confirmed run will consume."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping


def research_profile_paths(ta_root: Path) -> dict[str, Path]:
    """Native sources and launchers that define account-blind research runs."""
    root = ta_root.resolve()
    relative = {
        "research_cli": "cli/main.py",
        "research_cli_runner": "cli/run.py",
        "research_defaults": "tradingagents/default_config.py",
        "research_graph": "tradingagents/graph/trading_graph.py",
        "research_propagation": "tradingagents/graph/propagation.py",
        "research_graph_setup": "tradingagents/graph/setup.py",
        "research_context": "tradingagents/agents/context.py",
        "research_schemas": "tradingagents/agents/schemas.py",
        "research_state": "tradingagents/agents/state.py",
        "research_structured": "tradingagents/agents/structured.py",
        "research_tools": "tradingagents/agents/tools.py",
        "research_rating": "tradingagents/agents/rating.py",
        "research_market_analyst": "tradingagents/agents/analysts/market_analyst.py",
        "research_sentiment_analyst": "tradingagents/agents/analysts/sentiment_analyst.py",
        "research_news_analyst": "tradingagents/agents/analysts/news_analyst.py",
        "research_fundamentals_analyst": "tradingagents/agents/analysts/fundamentals_analyst.py",
        "research_bull_researcher": "tradingagents/agents/researchers/bull_researcher.py",
        "research_bear_researcher": "tradingagents/agents/researchers/bear_researcher.py",
        "research_manager": "tradingagents/agents/managers/research_manager.py",
        "research_trader": "tradingagents/agents/trader/trader.py",
        "research_risk_aggressive": "tradingagents/agents/risk_mgmt/aggressive_debator.py",
        "research_risk_conservative": "tradingagents/agents/risk_mgmt/conservative_debator.py",
        "research_risk_neutral": "tradingagents/agents/risk_mgmt/neutral_debator.py",
        "research_portfolio_manager": "tradingagents/agents/managers/portfolio_manager.py",
        "research_reporting": "tradingagents/reporting.py",
        "research_native_wrapper": "addons/fund_manager/run_native.py",
        "research_windows_wrapper": "addons/fund_manager/run_portfolio.ps1",
        "research_agent_config": "addons/agent_config.py",
    }
    return {key: root / path for key, path in relative.items()}


def fingerprint(data_root: Path, ta_root: Path, config_paths: Mapping[str, Path], *,
                include_research_profile: bool = False) -> dict:
    """Return stable content hashes for shared portfolio and model inputs.

    Only digests leave the process; input contents and credentials are never
    copied into run metadata. Missing files have an explicit stable marker.
    """
    paths = {
        "book": data_root / "my_book.json",
        "portfolio_book_contract": ta_root / "addons" / "portfolio_book.py",
        "trade_policy_contract": ta_root / "addons" / "fund_manager" / "trade_validation.py",
        "watchlist": data_root / "watchlist.json",
        "targets": data_root / "targets.json",
        "themes": ta_root / "addons" / "fund_manager" / "themes.json",
        **config_paths,
    }
    if include_research_profile:
        paths.update(research_profile_paths(ta_root))
    files = {}
    for name, path in sorted(paths.items()):
        try:
            files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        except FileNotFoundError:
            files[name] = None
    encoded = json.dumps(files, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return {"files": files, "sha256": hashlib.sha256(encoded).hexdigest()}
