"""Read-only Moomoo Singapore adapter for US stock account snapshots.

The SDK is optional. This module exposes read-only positions and USD cash.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any


class MoomooImportError(ValueError):
    pass


_OPTION_SUFFIX = re.compile(r"\d{6}[CP]\d{8}$", re.IGNORECASE)


def _sdk():
    try:
        import moomoo as moo
    except ImportError as exc:
        raise MoomooImportError("Install moomoo-requirements.txt and start Moomoo OpenD to import Moomoo accounts") from exc
    return moo


def _ok(moo, result, operation: str):
    if not isinstance(result, tuple) or len(result) < 2:
        raise MoomooImportError(f"Moomoo {operation} returned an invalid response")
    ret, data = result[0], result[1]
    if ret != getattr(moo, "RET_OK", 0):
        raise MoomooImportError(f"Moomoo {operation} failed; check OpenD connection and authorization")
    return data


def _rows(data: Any) -> list[dict[str, Any]]:
    if hasattr(data, "to_dict"):
        try:
            return data.to_dict(orient="records")
        except TypeError:
            pass
    if isinstance(data, list):
        if any(not isinstance(row, dict) for row in data):
            raise MoomooImportError("Moomoo returned a malformed row in account or position data")
        return data
    raise MoomooImportError("Moomoo returned malformed account or position rows")


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _account_id(row: dict[str, Any]) -> str:
    for key in ("acc_id", "account_id"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _is_real_stock(row: dict[str, Any], code: str) -> tuple[bool, bool]:
    """Return (is stock, is ambiguous) using explicit type then option syntax."""
    symbol = code.split(".", 1)[-1] if "." in code else code
    if _OPTION_SUFFIX.search(symbol):
        return False, False
    explicit = str(row.get("security_type") or row.get("sec_type") or row.get("type") or "").strip().upper()
    explicit = explicit.rsplit(".", 1)[-1]
    if explicit:
        if explicit in {"STK", "STOCK", "EQUITY", "ETF"}:
            return True, False
        if explicit in {"OPT", "OPTION", "DRVT", "FUT", "FUTURE", "IDX", "WARRANT",
                        "BWRT", "BOND", "CRYPTO", "FOREX", "PLATE", "PLATESET", "NON_STOCK"}:
            return False, False
    return False, True


def oauth_trade_client():
    """Connect to local OpenD using the SDK's US-filtered Singapore trade context."""
    moo = _sdk()
    firm = getattr(getattr(moo, "SecurityFirm", object), "FUTUSG", None)
    if firm is None:
        raise MoomooImportError("Installed Moomoo SDK does not expose the FUTUSG Singapore security firm")
    try:
        trd_market = getattr(getattr(moo, "TrdMarket", object), "US", None)
        if trd_market is None:
            raise MoomooImportError("Installed Moomoo SDK does not expose the US trading market")
        return moo.OpenSecTradeContext(filter_trdmarket=trd_market, host="127.0.0.1", port=11111,
                                       security_firm=firm)
    except Exception as exc:
        raise MoomooImportError("Could not connect to local Moomoo OpenD; verify it is running and authorized") from exc


def read_accounts(client) -> list[dict[str, str]]:
    moo = _sdk()
    try:
        rows = _rows(_ok(moo, client.get_acc_list(), "account lookup"))
    except MoomooImportError:
        raise
    except Exception as exc:
        raise MoomooImportError("Moomoo account lookup failed; check OpenD and account authorization") from exc
    real = str(getattr(getattr(moo, "TrdEnv", object), "REAL", "REAL")).rsplit(".", 1)[-1].upper()
    found = []
    for row in rows:
        acc_id = _account_id(row)
        env = str(row.get("trd_env") or row.get("env") or "").rsplit(".", 1)[-1].upper()
        if not acc_id or env not in {real, "REAL"}:
            continue
        status = str(row.get("acc_status") or row.get("status") or "").rsplit(".", 1)[-1].upper()
        if status not in {"ACTIVE", "NORMAL", "1", "TRUE"}:
            continue
        market_auth = row.get("trdmarket_auth") or row.get("trd_market_auth") or []
        auth_text = " ".join(map(str, market_auth)) if isinstance(market_auth, (list, tuple, set)) else str(market_auth)
        if "US" not in auth_text.upper():
            continue
        firm = str(row.get("security_firm") or "").rsplit(".", 1)[-1].upper()
        if firm and firm not in {"FUTUSG", "SECURITYFIRM.FUTUSG"}:
            continue
        found.append({"id": acc_id, "type": str(row.get("acc_type") or "STOCK"), "status": status or "ACTIVE"})
    if not found:
        raise MoomooImportError("No authorized real Moomoo trading accounts were returned")
    return found


def read_snapshot(client, account_id: str, account_type: str = "STOCK") -> dict[str, Any]:
    moo = _sdk()
    trd_env = getattr(getattr(moo, "TrdEnv", object), "REAL", "REAL")
    try:
        positions = _ok(moo, client.position_list_query(trd_env=trd_env, acc_id=int(account_id), refresh_cache=True), "position refresh")
    except MoomooImportError:
        raise
    except Exception as exc:
        raise MoomooImportError("Moomoo position refresh failed; no portfolio changes were made") from exc
    cash = None
    try:
        # The SDK maps us_cash from the USD entry in the per-currency cash list.
        # The generic cash field is reported in the display currency.
        currency = getattr(getattr(moo, "Currency", object), "USD", "USD")
        funds = _rows(_ok(moo, client.accinfo_query(trd_env=trd_env, acc_id=int(account_id),
                         refresh_cache=True, currency=currency), "USD cash refresh"))
        if len(funds) == 1:
            cash = _number(funds[0].get("us_cash"))
    except Exception:
        pass
    raw_positions = _rows(positions)
    quote = None
    classification_failed = False
    categories: dict[str, str] = {}
    codes = list(dict.fromkeys(str(row.get("code") or "") for row in raw_positions if row.get("code")))
    try:
        quote = moo.OpenQuoteContext(host="127.0.0.1", port=11111)
        categories = _classify_basicinfo(quote, moo, codes)
    except Exception:
        # Classification failure will make otherwise-untyped positions fail
        # closed in normalize_snapshot; never infer stock from a ticker string.
        classification_failed = True
    finally:
        if quote is not None:
            close = getattr(quote, "close", None)
            if callable(close):
                close()
    for row in raw_positions:
        code = str(row.get("code") or "").strip().upper()
        if not any(row.get(key) for key in ("security_type", "sec_type", "type")):
            row["security_type"] = categories.get(code, "UNKNOWN")
            if code not in categories and not _OPTION_SUFFIX.search(code.split(".", 1)[-1]):
                row["_classification_error"] = (
                    "US instrument classification query failed" if classification_failed
                    else "instrument was not confirmed as a US stock or ETF")
    return {"scope": "stocks_only", "complete": True, "fetched_at": datetime.now(timezone.utc).isoformat(),
            "positions": raw_positions, "cash": cash, "cash_currency": "USD" if cash is not None else None}


def _classify_basicinfo(quote, moo, codes: list[str]) -> dict[str, str]:
    """Classify codes only when US stock/ETF basic-info confirms the instrument."""
    if not codes:
        return {}
    market = getattr(getattr(moo, "Market", object), "US", "US")
    categories: dict[str, str] = {}
    data = _ok(moo, quote.get_stock_basicinfo(market=market, code_list=codes), "US instrument classification")
    supported_nonstock = {"DRVT", "FUTURE", "IDX", "WARRANT", "BWRT", "BOND",
                          "CRYPTO", "FOREX", "PLATE", "PLATESET"}
    for row in _rows(data):
        code = str(row.get("code") or "").strip().upper()
        stock_type = str(row.get("stock_type") or "").strip().upper().rsplit(".", 1)[-1]
        if code not in codes:
            continue
        if stock_type in {"STOCK", "STK", "EQUITY"}:
            categories[code] = "STK"
        elif stock_type == "ETF":
            categories[code] = "ETF"
        elif stock_type in supported_nonstock:
            categories[code] = "NON_STOCK"
    return categories


def normalize_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    excluded: list[dict[str, str]] = []
    rejected: list[dict[str, str]] = []
    if snapshot.get("scope") != "stocks_only" or snapshot.get("complete") is not True:
        issues.append("Moomoo did not return a complete US stock positions snapshot")
    positions = snapshot.get("positions")
    if not isinstance(positions, list):
        positions = []
        issues.append("Moomoo positions response is missing or malformed")
    by_ticker: dict[str, dict[str, Any]] = {}
    for i, row in enumerate(positions):
        if not isinstance(row, dict):
            rejected.append({"row": str(i + 1), "reason": "malformed position"})
            continue
        code = str(row.get("code") or row.get("ticker") or "").strip().upper()
        market = str(row.get("position_market") or row.get("market") or "").strip().upper()
        code_market = code.split(".", 1)[0] if "." in code else ""
        other_markets = {"SG", "HK", "SH", "SZ", "JP", "AU", "CA", "MY"}
        is_other_code = code_market in other_markets
        is_other_market = market in other_markets
        if is_other_code or is_other_market:
            if ((is_other_code and market in {"", code_market})
                    or (is_other_market and code_market in {"", market})):
                excluded.append({"ticker": code or f"row {i + 1}",
                                 "reason": "non-US position excluded from the US stock scope"})
            else:
                rejected.append({"ticker": code or f"row {i + 1}",
                                 "reason": "position code and market conflict; cannot confirm US scope"})
            continue
        if market == "US" and not code.startswith("US."):
            rejected.append({"ticker": code or f"row {i + 1}", "reason": "US position lacks a confirmed US code prefix"})
            continue
        if code.startswith("US.") and market != "US":
            rejected.append({"ticker": code, "reason": "US code lacks a confirmed US position market"})
            continue
        if market != "US" or not code.startswith("US."):
            rejected.append({"ticker": code or f"row {i + 1}",
                             "reason": f"unsupported or missing market {market or 'unknown'}; only confirmed US stocks are mapped"})
            continue
        stock, ambiguous = _is_real_stock(row, code)
        if not stock:
            if ambiguous:
                detail = str(row.get("_classification_error") or "instrument type is missing or ambiguous")
                rejected.append({"ticker": code or f"row {i + 1}",
                                 "reason": f"{detail}; cannot safely classify as a US stock"})
            else:
                excluded.append({"ticker": code or f"row {i + 1}", "reason": "non-stock instrument excluded from US stock scope"})
            continue
        side = str(row.get("position_side") or "").strip().upper().rsplit(".", 1)[-1]
        if side != "LONG":
            rejected.append({"ticker": code or f"row {i + 1}",
                             "reason": f"position side is {side or 'missing or unknown'}; only long positions are supported"})
            continue
        currency = str(row.get("currency") or "").strip().upper()
        if currency != "USD":
            rejected.append({"ticker": code, "reason": f"position currency is {currency or 'missing'}; only verified USD positions are supported"})
            continue
        ticker = code.split(".", 1)[-1] if "." in code else code
        ticker = {"BRK.B": "BRK-B"}.get(ticker, ticker)
        if not ticker or not ticker.replace("-", "").replace(".", "").isalnum():
            rejected.append({"ticker": code or f"row {i + 1}", "reason": "missing or invalid stock symbol"})
            continue
        quantity = _number(row.get("qty", row.get("quantity")))
        if quantity is None or quantity <= 0:
            rejected.append({"ticker": ticker, "reason": "quantity missing, invalid, or nonpositive"})
            continue
        average = _number(row.get("average_cost"))
        if average is None or average <= 0:
            average = None
        sellable = _number(row.get("can_sell_qty", row.get("sellable_quantity")))
        if sellable is not None and not 0 <= sellable <= quantity:
            rejected.append({"ticker": ticker, "reason": "sellable quantity is outside the held quantity"})
            continue
        diluted = _number(row.get("diluted_cost"))
        if diluted is None and row.get("cost_price_valid") is True:
            diluted = _number(row.get("cost_price"))
        item = {"ticker": ticker, "market": "US", "currency": "USD", "quantity": quantity,
                "average_price": average,
                "cost_method": "average_cost" if average is not None else None,
                "cost_source": "moomoo_average_cost" if average is not None else None,
                "diluted_cost": diluted,
                "sellable_quantity": sellable}
        if ticker in by_ticker:
            prior = by_ticker[ticker]
            total = prior["quantity"] + quantity
            if prior["average_price"] is not None and average is not None:
                prior["average_price"] = (prior["quantity"] * prior["average_price"] + quantity * average) / total
            else:
                prior["average_price"] = prior["cost_method"] = prior["cost_source"] = None
            prior["quantity"] = total
            prior["sellable_quantity"] = None if sellable is None or prior["sellable_quantity"] is None else prior["sellable_quantity"] + sellable
        else:
            by_ticker[ticker] = item
    if rejected:
        issues.append("One or more Moomoo positions are incomplete or unsupported")
    fetched = snapshot.get("fetched_at")
    if not isinstance(fetched, str) or not fetched:
        issues.append("Moomoo snapshot timestamp is missing")
    rows = sorted(by_ticker.values(), key=lambda p: p["ticker"])
    cash = _number(snapshot.get("cash")) if snapshot.get("cash_currency") == "USD" else None
    return {"scope": "stocks_only", "positions": rows, "fetched_at": fetched,
            "position_count": len(positions), "supported_count": len(rows),
            "cash": cash, "currency": "USD", "rejected": rejected, "excluded": excluded,
            "warnings": ["Moomoo USD cash could not be verified; actionable trades for this account will be rejected"]
                        if cash is None else [],
            "issues": issues, "can_apply": not issues}
