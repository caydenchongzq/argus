"""Credential-free checks for Moomoo Singapore import normalization."""
from __future__ import annotations

import sys
import types

from moomoo_import import normalize_snapshot, oauth_trade_client, read_accounts, read_snapshot


def main() -> int:
    good = normalize_snapshot({
        "scope": "stocks_only", "complete": True,
        "fetched_at": "2026-11-14T00:00:00+00:00", "cash": 99999,
        "positions": [
            {"code": "US.AAPL", "position_market": "US", "security_type": "STK",
             "currency": "USD", "position_side": "LONG", "qty": 2, "average_cost": 100, "cost_price": 102,
             "cost_price_valid": True, "can_sell_qty": 1.5},
            {"code": "US.BRK.B", "position_market": "US", "security_type": "STOCK",
             "currency": "USD", "position_side": "LONG", "qty": 1, "average_cost": "bad", "cost_price": 999,
             "cost_price_valid": False, "can_sell_qty": 1},
            {"code": "US.AAPL260116C00150000", "position_market": "US",
             "currency": "USD", "position_side": "LONG", "qty": 1, "average_cost": 2},
        ],
    })
    assert good["can_apply"]
    assert good["cash"] is None and good["positions"][0]["ticker"] == "AAPL"
    assert good["positions"][0]["average_price"] == 100
    assert good["positions"][0]["diluted_cost"] == 102
    assert good["positions"][1]["ticker"] == "BRK-B"
    assert good["positions"][1]["average_price"] is None
    assert good["positions"][1]["diluted_cost"] is None
    assert len(good["excluded"]) == 1

    ambiguous = normalize_snapshot({
        "scope": "stocks_only", "complete": True, "fetched_at": "now",
        "positions": [{"code": "US.NOTSURE", "position_market": "US", "currency": "USD",
                       "position_side": "LONG", "qty": 1}],
    })
    assert not ambiguous["can_apply"] and ambiguous["rejected"]

    invalid = normalize_snapshot({
        "scope": "stocks_only", "complete": True, "fetched_at": "now",
        "positions": [
            {"code": "US.AAPL", "position_market": "US", "currency": "USD", "security_type": "STK", "position_side": "LONG", "qty": -1},
            {"code": "SG.D05", "position_market": "SG", "currency": "SGD", "security_type": "STK", "position_side": "LONG", "qty": 1},
        ],
    })
    assert not invalid["can_apply"] and len(invalid["rejected"]) == 1 and len(invalid["excluded"]) == 1
    short = normalize_snapshot({
        "scope": "stocks_only", "complete": True, "fetched_at": "now",
        "positions": [{"code": "US.AAPL", "position_market": "US", "currency": "USD",
                       "position_side": "SHORT", "security_type": "STK", "qty": 10}],
    })
    assert not short["can_apply"] and "only long positions" in short["rejected"][0]["reason"]
    mixed_scope = normalize_snapshot({
        "scope": "stocks_only", "complete": True, "fetched_at": "now",
        "positions": [
            {"code": "US.AAPL", "position_market": "US", "currency": "USD", "position_side": "LONG", "security_type": "STK", "qty": 1},
            {"code": "US.AAPL260116C00150000", "position_market": "US", "currency": "USD", "position_side": "SHORT", "security_type": "DRVT", "qty": 1},
            {"code": "SG.D05", "position_market": "SG", "currency": "SGD", "qty": 1},
        ],
    })
    assert mixed_scope["can_apply"] and len(mixed_scope["positions"]) == 1
    assert len(mixed_scope["excluded"]) == 2 and not mixed_scope["rejected"]

    fake = types.ModuleType("moomoo")
    fake.RET_OK = 0
    fake.TrdEnv = types.SimpleNamespace(REAL="REAL")
    fake.SecurityFirm = types.SimpleNamespace(FUTUSG="FUTUSG")
    fake.TrdMarket = types.SimpleNamespace(US="US")
    fake.Currency = types.SimpleNamespace(USD="USD")
    fake.Market = types.SimpleNamespace(US="US")
    fake.SecurityType = types.SimpleNamespace(STOCK="STOCK", ETF="ETF")

    class Quote:
        closed = False
        def get_stock_basicinfo(self, *, market, code_list):
            assert market == "US"
            # SDK's code_list form returns mixed types regardless of stock_type.
            return (0, [
                {"code": "US.AAPL", "stock_type": "STOCK"},
                {"code": "US.SPY", "stock_type": "ETF"},
                {"code": "US.AAPL260116C00150000", "stock_type": "DRVT"},
            ])
        def close(self):
            self.closed = True

    quote = Quote()
    def open_quote(**kwargs):
        assert kwargs == {"host": "127.0.0.1", "port": 11111}
        return quote
    fake.OpenQuoteContext = open_quote
    sys.modules["moomoo"] = fake

    class Trade:
        closed = False
        funds = (0, [{"cash": 999999, "us_cash": 42.5, "power": 999999}])
        def get_acc_list(self):
            return (0, [
                {"acc_id": 1, "trd_env": "REAL", "acc_status": "ACTIVE", "trdmarket_auth": ["US"], "security_firm": "FUTUSG"},
                {"acc_id": 2, "trd_env": "SIMULATE", "acc_status": "ACTIVE", "trdmarket_auth": ["US"]},
                {"acc_id": 3, "trd_env": "REAL", "acc_status": "ACTIVE", "trdmarket_auth": ["HK"]},
                {"acc_id": 4, "trd_env": "REAL", "trdmarket_auth": ["US"]},
            ])
        def position_list_query(self, **kwargs):
            assert kwargs["trd_env"] == "REAL" and kwargs["acc_id"] == 1 and kwargs["refresh_cache"]
            return (0, [
                {"code": "US.AAPL", "position_market": "US", "currency": "USD", "position_side": "LONG", "qty": 2},
                {"code": "US.SPY", "position_market": "US", "currency": "USD", "position_side": "LONG", "qty": 1},
                {"code": "US.AAPL260116C00150000", "position_market": "US", "currency": "USD", "position_side": "LONG", "qty": 1},
            ])
        def accinfo_query(self, **kwargs):
            assert kwargs["currency"] == "USD" and kwargs["refresh_cache"]
            return self.funds
        def close(self):
            self.closed = True

    connected = Trade()
    fake.OpenSecTradeContext = lambda **kwargs: (
        (assert_context(kwargs), connected)[1]
    )
    def assert_context(kwargs):
        assert kwargs == {"filter_trdmarket": "US", "host": "127.0.0.1", "port": 11111,
                          "security_firm": "FUTUSG"}
        return None

    assert oauth_trade_client() is connected
    assert read_accounts(connected) == [{"id": "1", "type": "STOCK", "status": "ACTIVE"}]
    snap = read_snapshot(connected, "1")
    assert snap["cash"] == 42.5 and snap["positions"][0]["security_type"] == "STK"
    assert quote.closed
    assert not connected.closed
    classified = normalize_snapshot(snap)
    assert classified["can_apply"] and [p["ticker"] for p in classified["positions"]] == ["AAPL", "SPY"]
    assert len(classified["excluded"]) == 1
    assert classified["cash"] == 42.5 and not classified["warnings"]

    for usd_cash, expected in ((0, 0), (-25, -25), ("N/A", None), (float("nan"), None)):
        connected.funds = (0, [{"cash": 999999, "us_cash": usd_cash, "power": 999999}])
        refreshed = normalize_snapshot(read_snapshot(connected, "1"))
        assert refreshed["can_apply"] and refreshed["cash"] == expected
        assert bool(refreshed["warnings"]) == (expected is None)
    for unavailable in ((-1, "funds unavailable"), (0, [{"cash": 99, "currency": "USD", "power": 999}])):
        connected.funds = unavailable
        refreshed = normalize_snapshot(read_snapshot(connected, "1"))
        assert refreshed["can_apply"] and refreshed["cash"] is None and refreshed["warnings"]

    malformed = normalize_snapshot({"scope": "stocks_only", "complete": True, "fetched_at": "now",
                                    "positions": [{"code": "US.AAPL", "position_side": "LONG"}, None]})
    assert not malformed["can_apply"] and malformed["rejected"]
    sys.modules.pop("moomoo", None)
    print("argus Moomoo offline checks: ok (account authorization, basic-info stock scope, options, costs, unknown cash, ambiguous rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
