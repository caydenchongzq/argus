"""Read-only Tiger OAuth adapter and guarded portfolio-book import helpers."""
from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class TigerImportError(ValueError):
    pass


_US_CLASS_SHARE_ALIASES = {
    # Tiger uses dot notation; Yahoo Finance and TradingAgents use dashes.
    "BRK.B": "BRK-B",
}


def yahoo_ticker(symbol: str, market: str) -> str:
    """Map known Tiger US class-share symbols to Yahoo/TradingAgents spelling."""
    normalized = str(symbol or "").strip().upper()
    if str(market or "").strip().upper() == "US":
        return _US_CLASS_SHARE_ALIASES.get(normalized, normalized)
    return normalized


def book_version(path: Path) -> str:
    if not path.exists():
        return "missing"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Validate the stock-only import scope and preserve out-of-scope disclosures."""
    issues: list[str] = []
    warnings: list[str] = []
    if snapshot.get("scope") != "stocks_only":
        issues.append("Snapshot import scope is missing or unsupported")
    else:
        warnings.append("This replaces Argus with supported US stocks only; other instrument types are excluded")
    if snapshot.get("complete") is not True:
        issues.append("Tiger did not confirm a complete stock positions and assets snapshot")
    query_errors = snapshot.get("query_errors")
    if isinstance(query_errors, list):
        issues.extend(f"Positions unavailable for {kind}: {reason}" for kind, reason in query_errors)
    excluded_categories = snapshot.get("excluded_categories")
    if isinstance(excluded_categories, list) and excluded_categories:
        warnings.append("This import replaces Argus with stock positions only; other instrument categories are excluded")
        warnings.extend(f"{kind} excluded from stock-only import: {reason}" for kind, reason in excluded_categories)
    fetched = snapshot.get("fetched_at")
    if not isinstance(fetched, str) or not fetched:
        issues.append("Snapshot timestamp is missing")
    raw_positions = snapshot.get("positions")
    if not isinstance(raw_positions, list):
        issues.append("Positions response is missing or malformed")
        raw_positions = []

    currencies: set[str] = set()
    aggregated: dict[tuple[str, str], dict[str, Any]] = {}
    rejected: list[dict[str, str]] = []
    excluded: list[dict[str, str]] = []
    for index, raw in enumerate(raw_positions):
        if not isinstance(raw, dict):
            rejected.append({"row": str(index + 1), "reason": "malformed position"})
            continue
        symbol = str(raw.get("ticker") or "").strip().upper()
        market = str(raw.get("market") or "").strip().upper()
        sec_type = str(raw.get("sec_type") or "").strip().upper()
        currency = str(raw.get("currency") or "").strip().upper()
        if sec_type != "STK":
            if str(raw.get("query_type") or "").strip().upper() == "STK":
                rejected.append({"ticker": symbol or f"row {index + 1}", "market": market,
                                 "reason": f"stock positions query returned unexpected or missing instrument type {sec_type or 'unknown'}"})
                continue
            excluded.append({"ticker": symbol or f"row {index + 1}", "market": market,
                             "reason": f"not included in stock-only import ({sec_type or 'unknown'}); existing positions will be replaced"})
            continue
        if market != "US":
            rejected.append({"ticker": symbol or f"row {index + 1}", "market": market,
                             "reason": f"unsupported or missing market {market or 'unknown'}; only US symbols are mapped"})
            continue
        symbol = yahoo_ticker(symbol, market)
        if not symbol or not symbol.replace(".", "").replace("-", "").isalnum():
            rejected.append({"ticker": symbol or f"row {index + 1}", "reason": "missing or invalid symbol"})
            continue
        if not currency:
            rejected.append({"ticker": symbol, "reason": "currency missing"})
            continue
        try:
            quantity = float(raw.get("quantity"))
            average = float(raw.get("average_price"))
        except (TypeError, ValueError):
            rejected.append({"ticker": symbol, "reason": "quantity or average cost missing"})
            continue
        if not math.isfinite(quantity) or quantity == 0 or not math.isfinite(average) or average <= 0:
            rejected.append({"ticker": symbol, "reason": "invalid quantity or average cost"})
            continue
        if quantity < 0:
            rejected.append({"ticker": symbol, "market": market,
                             "reason": "short positions are unsupported by the current portfolio model"})
            continue
        currencies.add(currency)
        identity = (market, symbol)
        entry = aggregated.get(identity)
        if entry is None:
            aggregated[identity] = {"ticker": symbol, "quantity": quantity, "average_price": average}
        else:
            if entry["quantity"] * quantity < 0:
                rejected.append({"ticker": symbol, "reason": "duplicate positions have opposing quantities"})
                continue
            total = entry["quantity"] + quantity
            if total == 0:
                rejected.append({"ticker": symbol, "reason": "duplicate positions net to zero"})
                continue
            entry["average_price"] = (entry["quantity"] * entry["average_price"] + quantity * average) / total
            entry["quantity"] = total

    try:
        cash = float(snapshot.get("cash"))
    except (TypeError, ValueError):
        cash = math.nan
    cash_currency = str(snapshot.get("cash_currency") or "").strip().upper()
    if not math.isfinite(cash):
        issues.append("Cash balance is missing or invalid")
    elif cash != 0 and not cash_currency:
        issues.append("Cash currency is missing")
    elif cash != 0:
        currencies.add(cash_currency)
    if len(currencies) > 1:
        issues.append("Mixed currencies cannot be represented by the current portfolio book")
    if rejected:
        issues.append("One or more positions are unsupported or incomplete")
    currency = next(iter(currencies), cash_currency)
    book = {
        "cash": cash if math.isfinite(cash) else None,
        "currency": currency,
        "positions": sorted(aggregated.values(), key=lambda p: p["ticker"]),
    }
    return {
        "scope": "stocks_only",
        "book": book,
        "currency": currency,
        "fetched_at": fetched,
        "position_count": len(raw_positions),
        "supported_count": len(aggregated),
        "rejected": rejected,
        "excluded": excluded,
        "warnings": warnings,
        "issues": issues,
        "can_apply": not issues,
    }


def apply_replacement(path: Path, new_book: dict[str, Any], expected_version: str) -> Path | None:
    """Replace positions, preserving metadata and backing up an existing book."""
    if book_version(path) != expected_version:
        raise TigerImportError("Portfolio changed after preview; fetch a new preview before applying")
    if expected_version == "missing":
        if path.exists():
            raise TigerImportError("Portfolio was created after preview; fetch a new preview before applying")
        old_book: dict[str, Any] = {}
        backup = None
    else:
        try:
            old_book = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TigerImportError("Existing portfolio book is unreadable") from exc
        if not isinstance(old_book, dict):
            raise TigerImportError("Existing portfolio book is not an object")
        backup = path.with_name(f"{path.name}.bak_{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}")
        shutil.copy2(path, backup)
    merged = dict(old_book)
    merged.update(new_book)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(merged, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if expected_version == "missing" and path.exists():
            raise TigerImportError("Portfolio was created while import was being applied")
        os.replace(temporary, path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise
    return backup


def _prime_cash_balance(securities: Any) -> tuple[float, str]:
    """Extract a single-currency prime cash balance or reject ambiguous data."""
    currency_assets = getattr(securities, "currency_assets", None)
    if not isinstance(currency_assets, dict) or not currency_assets:
        raise TigerImportError("Tiger prime assets response lacks per-currency currency_assets")
    cash_by_currency: dict[str, float] = {}
    for code, value in currency_assets.items():
        raw_cash = getattr(value, "cash_balance", None)
        if raw_cash is None:
            raise TigerImportError(f"Tiger assets response lacks cash balance for {code}")
        try:
            currency_cash = float(raw_cash)
        except (TypeError, ValueError) as exc:
            raise TigerImportError(f"Tiger assets response has invalid cash balance for {code}") from exc
        if not math.isfinite(currency_cash):
            raise TigerImportError(f"Tiger assets response has invalid cash balance for {code}")
        cash_by_currency[str(code).upper()] = currency_cash
    nonzero = {code: value for code, value in cash_by_currency.items() if value != 0}
    if len(nonzero) > 1:
        raise TigerImportError("Tiger cash spans multiple currencies; the portfolio book cannot represent it")
    if nonzero:
        currency, amount = next(iter(nonzero.items()))
        return amount, currency

    currency = str(getattr(securities, "currency", "") or "").upper()
    if currency not in cash_by_currency:
        if len(cash_by_currency) != 1:
            raise TigerImportError("Tiger prime zero-cash currency is ambiguous")
        currency = next(iter(cash_by_currency))
    return 0.0, currency


def _global_cash_balance(asset: Any) -> tuple[float, str]:
    """Read global account cash by currency, rejecting totals that hide FX balances."""
    market_values = getattr(asset, "market_values", None)
    if not isinstance(market_values, dict) or not market_values:
        raise TigerImportError("Tiger global assets response lacks per-currency market_values")
    balances: dict[str, float] = {}
    for key, value in market_values.items():
        currency = str(getattr(value, "currency", None) or key or "").strip().upper()
        raw_cash = getattr(value, "cash_balance", None)
        if not currency or raw_cash is None:
            raise TigerImportError("Tiger global per-currency cash response is incomplete")
        try:
            cash = float(raw_cash)
        except (TypeError, ValueError) as exc:
            raise TigerImportError(f"Tiger global cash balance is invalid for {currency}") from exc
        if not math.isfinite(cash):
            raise TigerImportError(f"Tiger global cash balance is invalid for {currency}")
        balances[currency] = cash
    nonzero = {currency: cash for currency, cash in balances.items() if cash != 0}
    if len(nonzero) > 1:
        raise TigerImportError("Tiger global cash spans multiple currencies; the portfolio book cannot represent it")
    if nonzero:
        currency, cash = next(iter(nonzero.items()))
        return cash, currency
    summary = getattr(asset, "summary", None)
    summary_currency = str(getattr(summary, "currency", None) or "").strip().upper()
    if summary_currency and summary_currency in balances:
        return 0.0, summary_currency
    raise TigerImportError("Tiger global cash currency is ambiguous")


def _validate_unrepresented_prime_cash(segments: Any) -> None:
    """Reject cash in non-securities prime segments absent from the book model."""
    if not isinstance(segments, dict) or "S" not in segments:
        raise TigerImportError("Tiger prime assets response lacks its securities segment")
    for kind, segment in segments.items():
        if kind == "S":
            continue
        currency_assets = getattr(segment, "currency_assets", None)
        if not isinstance(currency_assets, dict) or not currency_assets:
            raise TigerImportError(f"Tiger {kind} segment lacks per-currency cash balances")
        balances = []
        for currency, asset in currency_assets.items():
            raw_cash = getattr(asset, "cash_balance", None)
            if raw_cash is None:
                raise TigerImportError(f"Tiger {kind} segment lacks {currency} cash balance")
            try:
                cash = float(raw_cash)
            except (TypeError, ValueError) as exc:
                raise TigerImportError(f"Tiger {kind} segment has invalid {currency} cash balance") from exc
            if not math.isfinite(cash):
                raise TigerImportError(f"Tiger {kind} segment has invalid {currency} cash balance")
            balances.append(cash)
        if any(cash != 0 for cash in balances):
            raise TigerImportError(f"Tiger {kind} segment has cash not represented in the portfolio book")
        aggregate = getattr(segment, "cash_balance", None)
        if aggregate is not None:
            try:
                aggregate = float(aggregate)
            except (TypeError, ValueError) as exc:
                raise TigerImportError(f"Tiger {kind} segment has invalid aggregate cash") from exc
            if not math.isfinite(aggregate) or aggregate != 0:
                raise TigerImportError(f"Tiger {kind} segment cash is ambiguous")


def oauth_trade_client():
    """Build the SDK client using its locally stored individual OAuth session."""
    try:
        from tigeropen.auth.oauth2 import OAuth2Authentication, OAuth2SessionManager
        from tigeropen.tiger_open_config import TigerOpenClientConfig
        from tigeropen.trade.trade_client import TradeClient
    except ImportError as exc:
        raise TigerImportError("Install tiger-requirements.txt in the Argus .venv first") from exc
    sessions = OAuth2SessionManager()
    config = TigerOpenClientConfig()
    config.authentication = OAuth2Authentication(sessions)
    config.log_level = 40  # ERROR; keep SDK diagnostics from leaking request context into dashboard logs.
    return TradeClient(config)


def read_accounts(client) -> list[dict[str, str]]:
    accounts = client.get_managed_accounts()
    if not isinstance(accounts, list) or not accounts:
        raise TigerImportError("Tiger returned no authorized accounts")
    result = []
    for account in accounts:
        raw_id = str(getattr(account, "account", "") or "")
        if not raw_id:
            continue
        result.append({"id": raw_id, "type": str(getattr(account, "account_type", "") or "unknown"),
                       "status": str(getattr(account, "status", "") or "")})
    if not result:
        raise TigerImportError("Tiger account response did not contain account identifiers")
    return result


def read_snapshot(client, account_id: str, account_type: str) -> dict[str, Any]:
    from tigeropen.common.consts import SecurityType

    # Tiger's SDK rejects SecurityType.ALL on some accounts. Query concrete
    # position classes individually. Keep successful rows for a useful preview,
    # but mark any failed class as incomplete so replacement remains disabled.
    position_types = (
        SecurityType.STK, SecurityType.OPT, SecurityType.FUT, SecurityType.WAR,
        SecurityType.FUND, SecurityType.FOP, SecurityType.IOPT, SecurityType.MLEG,
        SecurityType.CC,
    )
    rows = []
    query_errors = []
    excluded_categories = []
    for position_type in position_types:
        try:
            positions = client.get_positions(account=account_id, sec_type=position_type)
        except Exception as exc:
            # Do not expose the SDK's raw message, which may include account data.
            code = getattr(exc, "code", None)
            suffix = f" (Tiger API error {code})" if code is not None else ""
            error = (str(position_type), f"query failed{suffix}")
            (query_errors if position_type == SecurityType.STK else excluded_categories).append(error)
            continue
        if positions is None:
            error = (str(position_type), "Tiger returned no response")
            (query_errors if position_type == SecurityType.STK else excluded_categories).append(error)
            continue
        if not isinstance(positions, list):
            error = (str(position_type), "Tiger returned a malformed positions response")
            (query_errors if position_type == SecurityType.STK else excluded_categories).append(error)
            continue
        for position in positions:
            contract = getattr(position, "contract", None)
            contract_type = str(getattr(contract, "sec_type", "") or "").strip().upper()
            if position_type == SecurityType.STK and (contract is None or contract_type != "STK"):
                query_errors.append((str(position_type), "Tiger returned a malformed row or unexpected instrument type"))
                continue
            rows.append({
                "ticker": getattr(contract, "symbol", ""),
                "market": getattr(contract, "market", ""),
                "sec_type": contract_type or str(position_type),
                "query_type": str(position_type),
                "currency": getattr(contract, "currency", ""),
                "quantity": getattr(position, "position_qty", None) if getattr(position, "position_qty", None) is not None else getattr(position, "quantity", None),
                "average_price": getattr(position, "average_cost", None),
            })
    account_kind = account_type.strip().upper()
    is_prime = account_kind in {"PRIME", "STANDARD", "PAPER"} or "prime" in account_kind.lower() or "paper" in account_kind.lower()
    if is_prime:
        asset = client.get_prime_assets(account=account_id)
        segments = getattr(asset, "segments", {}) or {}
        securities = segments.get("S")
        if securities is None:
            raise TigerImportError("Tiger assets response lacks the securities segment")
        _validate_unrepresented_prime_cash(segments)
        cash, cash_currency = _prime_cash_balance(securities)
        timestamp = getattr(asset, "update_timestamp", None)
    else:
        assets = client.get_assets(account=account_id, segment=True, market_value=True)
        if not isinstance(assets, list) or len(assets) != 1:
            raise TigerImportError("Tiger assets response was empty or ambiguous")
        asset = assets[0]
        summary = getattr(asset, "summary", None)
        if summary is None:
            raise TigerImportError("Tiger assets response lacks account summary")
        cash, cash_currency = _global_cash_balance(asset)
        timestamp = getattr(summary, "timestamp", None)
    fetched = datetime.fromtimestamp(float(timestamp) / 1000, timezone.utc).isoformat() if timestamp else datetime.now(timezone.utc).isoformat()
    return {"scope": "stocks_only", "complete": not query_errors, "query_errors": query_errors,
            "excluded_categories": excluded_categories,
            "fetched_at": fetched, "positions": rows,
            "cash": cash, "cash_currency": cash_currency}
