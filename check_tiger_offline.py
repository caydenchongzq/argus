"""Credential-free fixture checks for Tiger snapshot normalization and book replacement."""
from __future__ import annotations

import json
import sys
import tempfile
import types
from pathlib import Path
from types import SimpleNamespace

from tiger_import import (TigerImportError, _global_cash_balance, _prime_cash_balance,
                          _validate_unrepresented_prime_cash, apply_replacement, book_version,
                          normalize_snapshot, read_snapshot)
from tiger_auth import authorize_with_device_code


def snapshot(positions, cash=10.5, cash_currency="USD"):
    return {"scope": "stocks_only", "complete": True, "fetched_at": "2026-11-08T00:00:00+00:00", "positions": positions,
            "cash": cash, "cash_currency": cash_currency}


def main() -> int:
    brk = normalize_snapshot(snapshot([
        {"ticker": "BRK.B", "market": "US", "sec_type": "STK", "currency": "USD", "quantity": 2, "average_price": 500},
    ]))
    assert brk["can_apply"]
    assert brk["book"]["positions"] == [{"ticker": "BRK-B", "quantity": 2, "average_price": 500}]

    fractional = normalize_snapshot(snapshot([
        {"ticker": "aapl", "market": "US", "sec_type": "STK", "currency": "USD", "quantity": 1.25, "average_price": 100},
        {"ticker": "AAPL", "market": "US", "sec_type": "STK", "currency": "USD", "quantity": 0.75, "average_price": 120},
    ]))
    assert fractional["can_apply"]
    assert fractional["book"]["positions"] == [{"ticker": "AAPL", "quantity": 2, "average_price": 107.5}]

    unsupported = normalize_snapshot(snapshot([
        {"ticker": "AAPL", "market": "US", "sec_type": "STK", "currency": "USD", "quantity": 1, "average_price": 100},
        {"ticker": "AAPL240119C00100000", "market": "US", "sec_type": "OPT", "currency": "USD", "quantity": 1, "average_price": 2},
    ]))
    assert unsupported["can_apply"] and unsupported["excluded"][0]["reason"].startswith("not included")

    short = normalize_snapshot(snapshot([
        {"ticker": "AAA", "market": "US", "sec_type": "STK", "currency": "USD", "quantity": -2, "average_price": 10},
    ]))
    assert not short["can_apply"] and "short positions" in short["rejected"][0]["reason"]

    mixed = normalize_snapshot(snapshot([
        {"ticker": "AAA", "market": "US", "sec_type": "STK", "currency": "USD", "quantity": 1, "average_price": 10},
        {"ticker": "BBB", "market": "US", "sec_type": "STK", "currency": "SGD", "quantity": 1, "average_price": 10},
    ], cash=0, cash_currency=""))
    assert not mixed["can_apply"] and any("Mixed currencies" in issue for issue in mixed["issues"])

    sg_same_symbol = normalize_snapshot(snapshot([
        {"ticker": "D05", "market": "SG", "sec_type": "STK", "currency": "SGD", "quantity": 100, "average_price": 30},
        {"ticker": "D05", "market": "US", "sec_type": "STK", "currency": "USD", "quantity": 1, "average_price": 30},
    ], cash=0, cash_currency=""))
    assert not sg_same_symbol["can_apply"]
    assert sg_same_symbol["book"]["positions"] == [{"ticker": "D05", "quantity": 1, "average_price": 30}]
    assert any(item.get("market") == "SG" for item in sg_same_symbol["rejected"])

    assert _prime_cash_balance(SimpleNamespace(
        currency_assets={"USD": SimpleNamespace(cash_balance=12), "SGD": SimpleNamespace(cash_balance=0)},
        currency="USD", cash_balance=12,
    )) == (12.0, "USD")

    _validate_unrepresented_prime_cash({
        "S": SimpleNamespace(),
        "C": SimpleNamespace(currency_assets={"USD": SimpleNamespace(cash_balance=0)}),
        "F": SimpleNamespace(currency_assets={"SGD": SimpleNamespace(cash_balance=0)}),
    })
    for segments in (
        {"S": SimpleNamespace(), "C": SimpleNamespace(currency_assets={"USD": SimpleNamespace(cash_balance=25)})},
        {"S": SimpleNamespace(), "F": SimpleNamespace(currency_assets={"SGD": SimpleNamespace(cash_balance=-3)})},
        {"S": SimpleNamespace(), "C": SimpleNamespace(currency_assets={}, cash_balance=0)},
        {"S": SimpleNamespace(), "C": SimpleNamespace(cash_balance=0)},
        {"S": SimpleNamespace(), "C": SimpleNamespace(cash_balance=12)},
        {"S": SimpleNamespace(), "C": SimpleNamespace()},
    ):
        try:
            _validate_unrepresented_prime_cash(segments)
        except TigerImportError:
            pass
        else:
            raise AssertionError("non-securities prime cash was accepted")
    for securities in (
        SimpleNamespace(currency_assets={"USD": SimpleNamespace(cash_balance=12), "SGD": SimpleNamespace(cash_balance=2)}),
        SimpleNamespace(currency_assets={"USD": SimpleNamespace()}),
        SimpleNamespace(currency_assets={}, currency="USD"),
        SimpleNamespace(currency_assets=None, currency="USD", cash_balance=500),
        SimpleNamespace(currency_assets={}, currency="USD", cash_balance=500),
    ):
        try:
            _prime_cash_balance(securities)
        except TigerImportError:
            pass
        else:
            raise AssertionError("ambiguous or missing Tiger cash was accepted")

    global_asset = SimpleNamespace(
        summary=SimpleNamespace(currency="USD", cash=1000),
        market_values={
            "USD": SimpleNamespace(currency="USD", cash_balance=800),
            "SGD": SimpleNamespace(currency="SGD", cash_balance=0),
        },
    )
    assert _global_cash_balance(global_asset) == (800.0, "USD")
    for asset in (
        SimpleNamespace(summary=SimpleNamespace(currency="USD", cash=1000), market_values=None),
        SimpleNamespace(summary=SimpleNamespace(currency="USD", cash=1000), market_values={
            "USD": SimpleNamespace(currency="USD", cash_balance=800),
            "SGD": SimpleNamespace(currency="SGD", cash_balance=20),
        }),
        SimpleNamespace(summary=SimpleNamespace(currency="USD", cash=1000), market_values={
            "USD": SimpleNamespace(currency="USD"),
        }),
    ):
        try:
            _global_cash_balance(asset)
        except TigerImportError:
            pass
        else:
            raise AssertionError("missing or mixed global currency cash was accepted")

    saved_modules = {name: sys.modules.get(name) for name in (
        "tigeropen", "tigeropen.common", "tigeropen.common.consts")}
    tiger_pkg = types.ModuleType("tigeropen")
    common_pkg = types.ModuleType("tigeropen.common")
    consts = types.ModuleType("tigeropen.common.consts")
    position_types = ("STK", "OPT", "FUT", "WAR", "FUND", "FOP", "IOPT", "MLEG", "CC")
    consts.SecurityType = SimpleNamespace(**{name: name for name in (*position_types, "ALL")})
    sys.modules.update({"tigeropen": tiger_pkg, "tigeropen.common": common_pkg,
                        "tigeropen.common.consts": consts})
    class FakeGlobalClient:
        def __init__(self):
            self.asset_args = None
            self.position_types = []
        def get_positions(self, **kwargs):
            self.position_types.append(kwargs["sec_type"])
            return []
        def get_assets(self, **kwargs):
            self.asset_args = kwargs
            return [global_asset]
    fake_client = FakeGlobalClient()
    try:
        global_snapshot = read_snapshot(fake_client, "U123", "GLOBAL")
        assert fake_client.asset_args == {"account": "U123", "segment": True, "market_value": True}
        assert fake_client.position_types == list(position_types)
        assert global_snapshot["cash"] == 800 and global_snapshot["cash_currency"] == "USD"

        class IncompletePositionClient(FakeGlobalClient):
            def get_positions(self, **kwargs):
                if kwargs["sec_type"] == "STK":
                    raise RuntimeError("fixture API error")
                if kwargs["sec_type"] == "FUT":
                    return [SimpleNamespace(contract=SimpleNamespace(
                        symbol="AAPL", market="US", sec_type="FUT", currency="USD"),
                        position_qty=2, average_cost=100)]
                return []
        partial = read_snapshot(IncompletePositionClient(), "U123", "GLOBAL")
        normalized_partial = normalize_snapshot(partial)
        assert partial["complete"] is False
        assert normalized_partial["book"]["positions"] == [
            ]
        assert not normalized_partial["can_apply"]
        assert any("STK" in issue for issue in normalized_partial["issues"])

        class StockScopeClient(FakeGlobalClient):
            def get_positions(self, **kwargs):
                kind = kwargs["sec_type"]
                if kind in {"FOP", "MLEG"}:
                    raise RuntimeError("fixture unsupported category")
                if kind == "STK":
                    return [SimpleNamespace(contract=SimpleNamespace(
                        symbol="AAPL", market="US", sec_type="STK", currency="USD"),
                        position_qty=2, average_cost=100)]
                return []
        stock_scope = normalize_snapshot(read_snapshot(StockScopeClient(), "U123", "GLOBAL"))
        assert stock_scope["can_apply"]
        assert stock_scope["book"]["positions"] == [
            {"ticker": "AAPL", "quantity": 2, "average_price": 100.0}]
        assert any("FOP excluded" in warning for warning in stock_scope["warnings"])
        assert any("MLEG excluded" in warning for warning in stock_scope["warnings"])

        class StockFailureClient(StockScopeClient):
            def get_positions(self, **kwargs):
                if kwargs["sec_type"] == "STK":
                    raise RuntimeError("fixture stock query failure")
                return super().get_positions(**kwargs)
        stock_failure = normalize_snapshot(read_snapshot(StockFailureClient(), "U123", "GLOBAL"))
        assert not stock_failure["can_apply"]
        assert any("STK" in issue for issue in stock_failure["issues"])

        for malformed_response in ({}, ""):
            class MalformedStockClient(FakeGlobalClient):
                def get_positions(self, **kwargs):
                    return malformed_response if kwargs["sec_type"] == "STK" else []
            malformed_stock = normalize_snapshot(read_snapshot(MalformedStockClient(), "U123", "GLOBAL"))
            assert not malformed_stock["can_apply"]
            assert any("STK" in issue and "malformed" in issue for issue in malformed_stock["issues"])

        class MissingStockTypeClient(FakeGlobalClient):
            def get_positions(self, **kwargs):
                if kwargs["sec_type"] == "STK":
                    return [SimpleNamespace(contract=SimpleNamespace(
                        symbol="AAPL", market="US", currency="USD"),
                        position_qty=2, average_cost=100)]
                return []
        missing_stock_type = normalize_snapshot(read_snapshot(MissingStockTypeClient(), "U123", "GLOBAL"))
        assert not missing_stock_type["can_apply"]
        assert any("unexpected instrument type" in issue for issue in missing_stock_type["issues"])

        class FakePrimeClient:
            def __init__(self, segments):
                self.asset = SimpleNamespace(segments=segments, update_timestamp=None)
            def get_positions(self, **kwargs):
                return []
            def get_prime_assets(self, **kwargs):
                return self.asset

        securities = SimpleNamespace(currency="USD", currency_assets={
            "USD": SimpleNamespace(cash_balance=100),
        })
        for segment in (
            SimpleNamespace(currency_assets={"USD": SimpleNamespace(cash_balance=25)}, cash_balance=25),
            SimpleNamespace(currency_assets={"SGD": SimpleNamespace(cash_balance=-3)}, cash_balance=-3),
            SimpleNamespace(currency_assets={}, cash_balance=0),
            SimpleNamespace(cash_balance=0),
        ):
            try:
                read_snapshot(FakePrimeClient({"S": securities, "C": segment}), "P123", "STANDARD")
            except TigerImportError as exc:
                assert "not represented" in str(exc) or "per-currency" in str(exc)
            else:
                raise AssertionError("Prime non-securities cash was imported")

        no_other_cash = read_snapshot(FakePrimeClient({
            "S": securities,
            "C": SimpleNamespace(currency_assets={"USD": SimpleNamespace(cash_balance=0)}, cash_balance=0),
            "F": SimpleNamespace(currency_assets={"SGD": SimpleNamespace(cash_balance=0)}, cash_balance=0),
        }), "P123", "STANDARD")
        assert no_other_cash["cash"] == 100 and no_other_cash["cash_currency"] == "USD"
    finally:
        for name, module in saved_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    output = []
    class FakeSessions:
        def login_with_device_code_if_needed(self, callback):
            callback(SimpleNamespace(verification_uri="https://tiger.example/device",
                                     verification_uri_complete=None, user_code="ABCD-1234",
                                     device_code="must-not-be-printed"))
    authorize_with_device_code(FakeSessions(), output.append)
    assert any("ABCD-1234" in line for line in output)
    assert all("must-not-be-printed" not in line for line in output)

    with tempfile.TemporaryDirectory(prefix="argus_tiger_fixture_") as folder:
        missing_book = Path(folder) / "first_import.json"
        assert book_version(missing_book) == "missing"
        first_import_backup = apply_replacement(missing_book, fractional["book"], "missing")
        assert first_import_backup is None
        assert json.loads(missing_book.read_text(encoding="utf-8"))["positions"] == fractional["book"]["positions"]

        book_path = Path(folder) / "my_book.json"
        original = {"cash": 25, "currency": "USD", "manual_note": "preserve", "positions": []}
        book_path.write_text(json.dumps(original), encoding="utf-8")
        version = book_version(book_path)
        backup = apply_replacement(book_path, fractional["book"], version)
        updated = json.loads(book_path.read_text(encoding="utf-8"))
        saved = json.loads(backup.read_text(encoding="utf-8"))
        assert updated["manual_note"] == "preserve" and len(updated["positions"]) == 1
        assert saved == original
        try:
            apply_replacement(book_path, {"positions": []}, version)
        except TigerImportError:
            pass
        else:
            raise AssertionError("stale book version was accepted")

    print("argus Tiger offline checks: ok (fractions, market identity, unsupported/mixed data, cash validation, backup, stale version)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
