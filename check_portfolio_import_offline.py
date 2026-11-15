"""Offline tests for atomic account-scoped portfolio imports."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "TradingAgents" / "addons"))

from portfolio_import import PortfolioImportError, account_identity, apply_account, book_version
from portfolio_book import normalize_book


def main() -> int:
    with tempfile.TemporaryDirectory() as directory:
        fresh_path = Path(directory) / "fresh.json"
        fresh = {
            "account_id": account_identity("moomoo", "fresh-id"),
            "broker": "moomoo_sg", "label": "Moomoo account 1", "scope": "US_STOCKS",
            "currency": "USD", "cash": None, "available_cash": None,
            "fetched_at": "2026-11-14T00:00:00Z",
            "positions": [{"ticker": "MSFT", "quantity": 1, "average_price": None}],
        }
        apply_account(fresh_path, fresh, "missing")
        first_import = normalize_book(json.loads(fresh_path.read_text(encoding="utf-8")))
        assert len(first_import["accounts"]) == 1 and first_import["cash"] is None

        path = Path(directory) / "my_book.json"
        path.write_text(json.dumps({"cash": 500, "currency": "USD", "positions": [
            {"ticker": "AAPL", "quantity": 2, "average_price": 100},
        ], "note": "keep"}), encoding="utf-8")
        account = {
            "account_id": account_identity("tiger", "private-account-id"),
            "broker": "tiger", "label": "Account 1", "scope": "US_STOCKS",
            "currency": "USD", "cash": 250, "available_cash": None,
            "fetched_at": "2026-11-14T00:00:00Z",
            "positions": [{"ticker": "AAPL", "market": "US", "currency": "USD",
                           "quantity": 3, "average_price": None,
                           "cost_method": None, "cost_source": None}],
        }
        version = book_version(path)
        backup = apply_account(path, account, version, replace_legacy=False)
        assert backup and backup.exists()
        merged = json.loads(path.read_text(encoding="utf-8"))
        assert merged["note"] == "keep" and len(merged["accounts"]) == 2
        assert merged["cash"] == 750
        assert merged["positions"][0]["quantity"] == 5
        assert merged["positions"][0]["average_price"] is None
        assert merged["accounts"][1]["positions"][0]["average_price"] is None

        newer = dict(account, cash=None, fetched_at="2026-11-14T01:00:00Z")
        apply_account(path, newer, book_version(path), replace_legacy=False)
        merged2 = normalize_book(json.loads(path.read_text(encoding="utf-8")))
        assert len(merged2["accounts"]) == 2
        assert [a["account_id"] for a in merged2["accounts"]].count(account["account_id"]) == 1
        assert merged2["cash"] is None

        try:
            apply_account(path, account, "stale-version", replace_legacy=True)
        except PortfolioImportError:
            pass
        else:
            raise AssertionError("stale account import overwrote the current book")

        apply_account(path, account, book_version(path), replace_legacy=True)
        replaced = normalize_book(json.loads(path.read_text(encoding="utf-8")))
        assert len(replaced["accounts"]) == 1
        assert replaced["accounts"][0]["account_id"] == account["account_id"]
    print("argus portfolio import offline checks: ok (legacy binding, account isolation, unknown cost/cash, stale version)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
