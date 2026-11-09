"""Offline check for the watchlist change log, undo, and weekly spend endpoints.

Uses a temp TradingAgents root with a copy of the real add-ons. No network, no model call,
and the real data folder is not touched.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    default_ta = Path(r"D:\software development\trading\TradingAgents") if os.name == "nt" else HERE.parent / "TradingAgents"
    real_ta = Path(os.environ.get("TRADINGAGENTS_ROOT", str(default_ta)))
    tmp = Path(tempfile.mkdtemp(prefix="argus_check_"))
    try:
        shutil.copytree(real_ta / "addons", tmp / "addons", ignore=shutil.ignore_patterns(".git", "__pycache__", "*.bak*"))
        data = tmp / "data"
        (data / "fund_manager" / "run_costs").mkdir(parents=True)
        (data / "watchlist.json").write_text(json.dumps([{"ticker": "AAA", "sector": "X", "type": "stock"}]), encoding="utf-8")
        (data / "targets.json").write_text(json.dumps({"weekly_budget_usd": 25, "budget": {"enabled": False}}), encoding="utf-8")
        (data / "my_book.json").write_text(json.dumps({"cash": 0, "positions": []}), encoding="utf-8")
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        (data / "fund_manager" / "run_costs" / "AAA_x.json").write_text(json.dumps(
            {"ticker": "AAA", "generated_utc": now, "cost_usd": 1.25, "cost_source": "provider"}), encoding="utf-8")
        os.environ["TRADINGAGENTS_ROOT"] = str(tmp)
        os.environ["DASHBOARD_RUNS_DIR"] = str(tmp / "runs")
        sys.path.insert(0, str(HERE))
        from fastapi.testclient import TestClient
        import server

        c = TestClient(server.app, base_url="http://127.0.0.1")
        token = c.get("/api/session").json()["token"]
        headers = {"X-Argus-Confirm": token, "Origin": "http://127.0.0.1"}
        r = c.post("/api/watchlist", json={"ticker": "BBB", "sector": "Y", "type": "stock"}, headers=headers)
        assert r.status_code == 200, r.text
        r = c.delete("/api/watchlist/AAA", headers=headers)
        assert r.status_code == 200, r.text
        log = [json.loads(x) for x in (data / "watchlist_log.jsonl").read_text(encoding="utf-8").splitlines()]
        assert [e["action"] for e in log] == ["add", "drop"], log
        assert list(data.glob("*.bak*")) == [], list(data.glob("*.bak*"))
        r = c.post("/api/watchlist/undo", json={}, headers=headers)
        assert r.status_code == 200, r.text
        tickers = sorted(i["ticker"] for i in r.json()["items"])
        assert tickers == ["AAA", "BBB"], tickers
        r = c.post("/api/watchlist/undo", json={}, headers=headers)
        assert r.status_code == 200 and [i["ticker"] for i in r.json()["items"]] == ["AAA"], r.text
        r = c.post("/api/watchlist/undo", json={}, headers=headers)
        assert r.status_code == 404, r.text
        denied = c.post("/api/watchlist/undo", json={}, headers={**headers, "Origin": "http://evil.example"})
        assert denied.status_code == 403, denied.text
        s = c.get("/api/spend").json()
        assert s["spent_usd"] == 1.25 and s["budget_usd"] == 25 and s["budget_enabled"] is False, s
        current_settings = c.get("/api/settings").json()
        assert current_settings["max_adds_per_week"] is None
        assert current_settings["max_drops_per_week"] is None
        assert current_settings["cooldown_days"] == 14
        saved_settings = c.put("/api/settings", json={
            "weekly_budget_enabled": False, "weekly_budget_usd": 40,
            "max_adds_per_week": None, "max_drops_per_week": None,
            "max_candidates": 100, "max_stocks_per_sector": 10,
        }, headers=headers)
        assert saved_settings.status_code == 200, saved_settings.text
        targets = json.loads((data / "targets.json").read_text(encoding="utf-8"))
        assert targets["weekly_budget_usd"] == 40 and targets["budget"]["weekly_usd"] == 40, targets
        assert targets["budget"]["enabled"] is False
        assert c.get("/api/spend").json()["budget_usd"] == 40
        limited = c.put("/api/settings", json={
            "weekly_budget_enabled": False, "weekly_budget_usd": 40,
            "max_adds_per_week": None, "max_drops_per_week": None,
            "max_candidates": 1, "max_stocks_per_sector": 10,
        }, headers=headers)
        assert limited.status_code == 200, limited.text
        full = c.post("/api/watchlist", json={"ticker": "BBB", "sector": "Other", "type": "stock"}, headers=headers)
        assert full.status_code == 400 and "candidate limit" in full.text.lower(), full.text
        sector_limited = c.put("/api/settings", json={
            "weekly_budget_enabled": False, "weekly_budget_usd": 40,
            "max_adds_per_week": None, "max_drops_per_week": None,
            "max_candidates": 2, "max_stocks_per_sector": 1,
        }, headers=headers)
        assert sector_limited.status_code == 200, sector_limited.text
        sector_full = c.post("/api/watchlist", json={"ticker": "BBB", "sector": "X", "type": "stock"}, headers=headers)
        assert sector_full.status_code == 400 and "active stock" in sector_full.text.lower(), sector_full.text
        (data / "my_book.json").write_text(json.dumps({"positions": [{"ticker": "HELD"}]}), encoding="utf-8")
        server._validate_watchlist_add({"ticker": "HELD", "sector": "X", "type": "stock"},
                                       server._saved_watchlist_items())
        (data / "my_book.json").write_text(json.dumps({"positions": []}), encoding="utf-8")
        c.put("/api/settings", json={
            "weekly_budget_enabled": False, "weekly_budget_usd": 40,
            "max_adds_per_week": None, "max_drops_per_week": None,
            "max_candidates": 100, "max_stocks_per_sector": 10,
        }, headers=headers)

        # Holdings are derived monitor rows, never written back as candidates.
        (data / "my_book.json").write_text(json.dumps({"cash": 0, "positions": [
            {"ticker": "AAA", "quantity": 1, "average_price": 10},
            {"ticker": "BRK-B", "quantity": 2, "average_price": 20},
        ]}), encoding="utf-8")
        (data / "watchlist.json").write_text(json.dumps([
            {"ticker": "AAA", "sector": "Tech", "type": "stock"},
            {"ticker": "BRK-B", "sector": "Finance", "type": "stock"},
            {"ticker": "CCC", "sector": "Other", "type": "stock"},
        ]), encoding="utf-8")
        (data / "targets.json").write_text(json.dumps({"weights_pct": {"AAA": 50, "cash": 10}}), encoding="utf-8")
        portfolio = c.get("/api/portfolio").json()
        assert portfolio["targets"] == {} and portfolio["cash_target_pct"] is None, portfolio
        assert all(row["target_pct"] is None for row in portfolio["positions"]), portfolio
        monitor = c.get("/api/watchlist").json()["items"]
        by_ticker = {row["ticker"]: row for row in monitor}
        assert by_ticker["AAA"]["origins"] == ["held", "candidate"]
        assert by_ticker["BRK-B"]["instrument_type"] == "Stock"
        assert by_ticker["CCC"]["origins"] == ["candidate"]
        # Selling a holding removes only the held origin; the saved candidate survives.
        book = json.loads((data / "my_book.json").read_text(encoding="utf-8"))
        book["positions"] = [row for row in book["positions"] if row["ticker"] != "AAA"]
        (data / "my_book.json").write_text(json.dumps(book), encoding="utf-8")
        assert next(row for row in c.get("/api/watchlist").json()["items"] if row["ticker"] == "AAA")["origins"] == ["candidate"]
        # Reholding then removing its candidate leaves the derived holding only.
        book["positions"].append({"ticker": "AAA", "quantity": 1, "average_price": 10})
        (data / "my_book.json").write_text(json.dumps(book), encoding="utf-8")
        r = c.delete("/api/watchlist/AAA", headers=headers)
        assert r.status_code == 200, r.text
        remaining = {row["ticker"]: row for row in r.json()["items"]}
        assert remaining["AAA"]["origins"] == ["held"]
        stored = json.loads((data / "watchlist.json").read_text(encoding="utf-8"))
        assert [row["ticker"] for row in stored] == ["BRK-B", "CCC"], stored
        book["positions"] = [row for row in book["positions"] if row["ticker"] != "AAA"]
        (data / "my_book.json").write_text(json.dumps(book), encoding="utf-8")
        assert "AAA" not in {row["ticker"] for row in c.get("/api/watchlist").json()["items"]}
        (data / "targets.json").write_text(json.dumps({"weights_pct": {"AAA": 50},
                                                       "approved_targets_pct": {"AAA": 40, "cash": 15},
                                                       "weekly_budget_usd": 25,
                                                       "budget": {"enabled": False}}), encoding="utf-8")
        portfolio = c.get("/api/portfolio").json()
        assert portfolio["targets"] == {"AAA": 40, "cash": 15}, portfolio
        assert portfolio["cash_target_pct"] == 15, portfolio
        assert server._instrument_type("NOTETF", {"type": "ETN"}) == "ETN"
        app_js = (HERE / "static" / "app.js").read_text(encoding="utf-8")
        assert "target.push(data.targets?.[t] ?? null)" in app_js
        assert "target.push(data.cash_target_pct ?? null)" in app_js

        # Paid scope preview is immutable by hash and records exact stages/seats.
        (data / "my_book.json").write_text(json.dumps({"cash": 1000, "positions": [
            {"ticker": "BBB", "quantity": 1, "average_price": 1},
        ]}), encoding="utf-8")
        (data / "watchlist.json").write_text(json.dumps([
            {"ticker": "CCC", "sector": "Technology", "type": "stock"},
        ]), encoding="utf-8")
        prior_report = data / "logs" / "reports" / "BBB_20261103_120000"
        prior_report.mkdir(parents=True)
        (prior_report / "complete_report.md").write_text("Analysis date: 2026-11-03\n", encoding="utf-8")
        original_spawn = server._spawn_run
        server._spawn_run = lambda _meta, _args: None
        try:
            rev_request = {"confirm": False, "run_agents": False, "include_watchlist": False,
                           "no_llm": False, "analysis_date": "2026-11-08", "since": "", "tickers": []}
            rev_preview = c.post("/api/runs/manifest", json=rev_request).json()
            rev_manifest = rev_preview["manifest"]
            assert rev_manifest["input_fingerprint"]["sha256"]
            assert rev_manifest["mode"] == "REV"
            assert [stage["id"] for stage in rev_manifest["stages"]] == ["REV:DRAFT", "REV:RISK:1", "REV:FINAL"]
            assert rev_manifest["cost_estimate"]["is_hard_ceiling"] is False
            assert rev_manifest["cost_estimate"]["kind"] == "configured_budget_planning_placeholder"
            assert "not a model-priced estimate" in rev_manifest["cost_estimate"]["note"]
            assert rev_manifest["model_price_inventory"]["verified_current"] is False
            app_js = (HERE / "static" / "app.js").read_text(encoding="utf-8")
            assert "Configured budget-planning placeholder:" in app_js
            assert "not model-priced and not a provider price quote" in app_js
            assert rev_manifest["portfolio_report_inputs"]["BBB"]["status"] == "reused"
            assert rev_manifest["portfolio_report_inputs"]["BBB"]["analysis_date"] == "2026-11-03"
            changed = {**rev_request, "no_macro": True, "manifest_sha256": rev_preview["manifest_sha256"], "confirm": True}
            assert c.post("/api/runs", json=changed, headers=headers).status_code == 409
            book_bytes = (data / "my_book.json").read_bytes()
            changed_book = json.loads(book_bytes)
            changed_book["positions"][0]["quantity"] = 2
            (data / "my_book.json").write_text(json.dumps(changed_book), encoding="utf-8")
            changed_input = c.post("/api/runs", json={**rev_request,
                "manifest_sha256": rev_preview["manifest_sha256"], "confirm": True}, headers=headers)
            assert changed_input.status_code == 409, changed_input.text
            (data / "my_book.json").write_bytes(book_bytes)
            rev_start = c.post("/api/runs", json={**rev_request,
                "manifest_sha256": rev_preview["manifest_sha256"], "confirm": True}, headers=headers)
            assert rev_start.status_code == 200, rev_start.text
            assert rev_start.json()["run"]["manifest"]["mode"] == "REV"
            rev_args = rev_start.json()["run"]["args"]
            assert "--manifest-input-fingerprint" in rev_args and "--manifest-analysis-tickers-json" in rev_args
            assert rev_args[rev_args.index("--manifest-analysis-tickers-json") + 1] == "[]"

            anl_request = {"confirm": False, "run_agents": True, "analysis_only": True,
                           "include_watchlist": False, "no_llm": False, "analysis_date": "",
                           "since": "", "tickers": ["BBB"]}
            anl_preview = c.post("/api/runs/manifest", json=anl_request)
            assert anl_preview.status_code == 200, anl_preview.text
            anl_manifest = anl_preview.json()["manifest"]
            assert anl_manifest["mode"] == "ANL" and anl_manifest["fresh_analysis_tickers"] == ["BBB"]
            assert len(anl_manifest["stages"]) == 1 and anl_manifest["stages"][0]["id"] == "ANL:BBB"
            anl_start = c.post("/api/runs", json={**anl_request,
                "manifest_sha256": anl_preview.json()["manifest_sha256"], "confirm": True}, headers=headers)
            assert anl_start.status_code == 200, anl_start.text
            assert "--anl-only" in anl_start.json()["run"]["args"]

            bundle_request = {**anl_request, "analysis_only": False}
            bundle_preview = c.post("/api/runs/manifest", json=bundle_request).json()
            assert bundle_preview["manifest"]["mode"] == "ANL+REV"
            assert [stage["id"] for stage in bundle_preview["manifest"]["stages"]][-3:] == [
                "REV:DRAFT", "REV:RISK:1", "REV:FINAL"]

            snapshot_preview = c.post("/api/runs/manifest", json={**rev_request, "no_llm": True,
                                                                   "run_agents": True, "tickers": ["BBB"]}).json()
            assert snapshot_preview["manifest"]["mode"] == "snapshot"
            assert not any(stage["paid"] for stage in snapshot_preview["manifest"]["stages"])
            assert snapshot_preview["manifest"]["fresh_analysis_tickers"] == []
        finally:
            server._spawn_run = original_spawn

        # A proposal carries the exact scout-time candidate fingerprint.
        watch = [{"ticker": "AAA", "sector": "Technology", "type": "stock"},
                 {"ticker": "BBB", "sector": "Technology", "type": "stock"}]
        (data / "watchlist.json").write_text(json.dumps(watch), encoding="utf-8")
        (data / "my_book.json").write_text(json.dumps({"positions": [{"ticker": "BBB"}]}), encoding="utf-8")
        proposal_dir = data / "theme_scout" / "2026-11-08"
        proposal_dir.mkdir(parents=True)
        version = server._watchlist_version(server._saved_watchlist_items())
        proposal = {
            "date": "2026-11-08", "sectors": ["XLK"], "shadow": True,
            "ranking_status": "partial", "ranking_count": 33,
            "ranking_expected_count": 166, "ranking_missing_tickers": ["CCC"],
            "ranking_warnings": ["duplicate row CCC"],
            "base_watchlist_version": version,
            "changes": [
                {"action": "add", "ticker": "NVDA", "reason": "fresh candidate"},
                {"action": "drop", "ticker": "AAA", "reason": "weak relative strength"},
                {"action": "drop", "ticker": "BBB", "reason": "held protection fixture"},
            ],
            "proposed": [
                {"ticker": "BBB", "sector": "Technology", "type": "stock"},
                {"ticker": "NVDA", "sector": "Technology", "type": "stock"},
            ],
        }
        (proposal_dir / "watchlist_proposals.json").write_text(json.dumps(proposal), encoding="utf-8")
        view = c.get("/api/watchlist/proposal").json()
        assert view["applicable"] and view["base_watchlist_version"] == version and len(view["proposal_sha256"]) == 64, view
        assert view["coverage"]["ranking_status"] == "partial"
        assert view["coverage"]["ranking_count"] == 33 and view["coverage"]["ranking_expected_count"] == 166
        assert view["coverage"]["ranking_missing_tickers"] == ["CCC"]
        held_change = next(row for row in view["review_changes"] if row["ticker"] == "BBB")
        assert held_change["blocked_reason"]
        app_js = (Path(server.__file__).resolve().parent / "static" / "app.js").read_text(encoding="utf-8")
        assert "partial ranking" in app_js and "expected names were omitted" in app_js
        assert "All expected names were returned, but validation conflicts" in app_js
        assert "Validation warnings:" in app_js
        mutated = dict(proposal, note="same base, replacement contents")
        (proposal_dir / "watchlist_proposals.json").write_text(json.dumps(mutated), encoding="utf-8")
        replaced = c.post("/api/watchlist/proposal/apply", json={
            "date": "2026-11-08", "base_watchlist_version": version,
            "proposal_sha256": view["proposal_sha256"], "add": ["NVDA"], "confirm": True,
        }, headers=headers)
        assert replaced.status_code == 409, replaced.text
        (proposal_dir / "watchlist_proposals.json").write_text(json.dumps(proposal), encoding="utf-8")
        # A field change after scouting invalidates the proposal even at the same list size.
        stale_watch = [dict(watch[0], sector="Communication Services"), watch[1]]
        (data / "watchlist.json").write_text(json.dumps(stale_watch), encoding="utf-8")
        stale = c.post("/api/watchlist/proposal/apply", json={
            "date": "2026-11-08", "base_watchlist_version": version,
            "proposal_sha256": view["proposal_sha256"],
            "add": ["NVDA"], "drop": ["AAA"], "confirm": True,
        }, headers=headers)
        assert stale.status_code == 409, stale.text
        (data / "watchlist.json").write_text(json.dumps(watch), encoding="utf-8")
        held = c.post("/api/watchlist/proposal/apply", json={
            "date": "2026-11-08", "base_watchlist_version": version,
            "proposal_sha256": view["proposal_sha256"],
            "drop": ["BBB"], "confirm": True,
        }, headers=headers)
        assert held.status_code == 409, held.text
        applied = c.post("/api/watchlist/proposal/apply", json={
            "date": "2026-11-08", "base_watchlist_version": version,
            "proposal_sha256": view["proposal_sha256"],
            "add": ["NVDA"], "drop": ["AAA"], "confirm": True,
        }, headers=headers)
        assert applied.status_code == 200, applied.text
        applied_names = {row["ticker"] for row in applied.json()["items"]}
        assert applied_names == {"BBB", "NVDA"}, applied.json()
        events = [json.loads(line) for line in (data / "watchlist_log.jsonl").read_text(encoding="utf-8").splitlines()]
        assert events[-2]["source"] == events[-1]["source"] == "scout_review"
        assert events[-2]["action"] == "drop" and events[-1]["action"] == "add"
        # A reviewed proposal is undone as one grouped transaction.
        undone = c.post("/api/watchlist/undo", json={}, headers=headers)
        assert undone.status_code == 200 and {row["ticker"] for row in undone.json()["items"]} == {"AAA", "BBB"}

        # A pending journal is recovered under the next write lock before newer edits.
        wrapped = {"candidates": watch, "metadata": "preserve me"}
        (data / "watchlist.json").write_text(json.dumps(wrapped), encoding="utf-8")
        before_recovery = server._saved_watchlist_items()
        recovered_row = {"ticker": "RECOVERED", "sector": "Utilities", "type": "stock"}
        txn_id = "offline-recovery"
        server._write_json(server._watchlist_txn_path(), {
            "transaction_id": txn_id, "before": before_recovery,
            "after": before_recovery + [recovered_row],
            "events": [{"as_of": "2026-11-08", "action": "add", "ticker": "RECOVERED",
                        "source": "scout_review", "row": recovered_row}],
        })
        recovered_add = c.post("/api/watchlist", json={"ticker": "FRESH", "sector": "Utilities", "type": "stock"}, headers=headers)
        assert recovered_add.status_code == 200, recovered_add.text
        wrapped_after = json.loads((data / "watchlist.json").read_text(encoding="utf-8"))
        assert wrapped_after["metadata"] == "preserve me"
        assert {row["ticker"] for row in wrapped_after["candidates"]} >= {"RECOVERED", "FRESH"}
        assert not server._watchlist_txn_path().exists()
        assert any(row.get("transaction_id") == txn_id for row in __import__("watchlist_log").read_events(data))

        # A third-party edit that matches neither journal state fails closed.
        current = server._saved_watchlist_items()
        server._write_json(server._watchlist_txn_path(), {
            "transaction_id": "offline-conflict", "before": current,
            "after": current + [{"ticker": "PENDING", "sector": "Utilities", "type": "stock"}], "events": [],
        })
        (data / "watchlist.json").write_text(json.dumps([{"ticker": "EXTERNAL", "sector": "Other", "type": "stock"}]), encoding="utf-8")
        conflicted = c.post("/api/watchlist", json={"ticker": "NOPE", "sector": "Other", "type": "stock"}, headers=headers)
        assert conflicted.status_code == 409, conflicted.text
        assert [row["ticker"] for row in server._saved_watchlist_items()] == ["EXTERNAL"]
        server._watchlist_txn_path().unlink()

        assert server._canonical_sector_key("Technology") == server._canonical_sector_key("Information Technology")
        assert server._canonical_sector_key("XLK") == server._canonical_sector_key("Technology")

        assert server._validate_scout_sectors(list(server.SCOUT_SECTOR_LABELS)) == list(server.SCOUT_SECTOR_LABELS)
        try:
            server._validate_scout_sectors([*server.SCOUT_SECTOR_LABELS, "INVALID"])
            raise AssertionError("unknown discovery sector should be rejected")
        except server.HTTPException as exc:
            assert exc.status_code == 400
        six = [{"ticker": f"STK{i}", "sector": "Technology", "type": "stock"} for i in range(6)]
        (data / "watchlist.json").write_text(json.dumps(six), encoding="utf-8")
        (data / "my_book.json").write_text(json.dumps({"positions": []}), encoding="utf-8")
        wide_scope = c.post("/api/runs/manifest", json={
            "confirm": False, "run_agents": False, "analysis_only": True,
            "include_watchlist": True, "no_llm": False, "analysis_date": "",
            "since": "", "tickers": [row["ticker"] for row in six] + ["STK0"],
        })
        assert wide_scope.status_code == 200, wide_scope.text
        assert wide_scope.json()["manifest"]["fresh_analysis_tickers"] == [row["ticker"] for row in six]
        assert [stage["id"] for stage in wide_scope.json()["manifest"]["stages"]] == [
            f"ANL:{row['ticker']}" for row in six]
        sector_aliases = ["Technology", "Information Technology", "XLK"]
        ten = [{"ticker": f"STK{i}", "sector": sector_aliases[i % len(sector_aliases)], "type": "stock"}
               for i in range(10)]
        (data / "watchlist.json").write_text(json.dumps(ten), encoding="utf-8")
        assert len(server._sector_stock_tickers("Technology")) == 10
        assert len(server._sector_stock_tickers("XLK")) == 10
        capped = c.post("/api/watchlist", json={"ticker": "STK10", "sector": "Technology", "type": "stock"}, headers=headers)
        assert capped.status_code == 400, capped.text
        etf_at_stock_cap = c.post("/api/watchlist", json={"ticker": "TECHF", "sector": "Technology", "type": "etf"}, headers=headers)
        assert etf_at_stock_cap.status_code == 200, etf_at_stock_cap.text
        original_spawn = server._spawn_run
        spawned = []
        server._spawn_run = lambda _meta, _args: spawned.append(_args)
        original_public_payload = server.agent_config.public_payload
        def scout_without_price():
            payload = original_public_payload()
            for seat in payload.get("seats", []):
                if seat.get("id") == "theme_scout":
                    seat["est_cost_usd"] = None
            return payload
        server.agent_config.public_payload = scout_without_price
        try:
            scout_request = {"mode": "weekly", "include_llm": True, "single_call": True,
                             "sectors": ["XLK", "XLY", "XLV"]}
            scout_preview = c.post("/api/theme-scout/manifest", json=scout_request)
            assert scout_preview.status_code == 200, scout_preview.text
            scout_manifest = scout_preview.json()["manifest"]
            assert scout_manifest["single_call"] and scout_manifest["model"]
            assert scout_manifest["cost_estimate"]["verified_current"] is False
            assert scout_manifest["cost_estimate"]["amount_usd"] is None
            assert scout_manifest["cost_estimate"]["source"] == "unavailable"
            assert "no local price and token estimate" in scout_manifest["cost_estimate"]["note"]
            assert scout_manifest["spending_controls"]["weekly_budget_enabled"] is False
            scout_scope = scout_manifest["model_scope"]
            assert scout_scope["selected_sector_etfs"] == [
                {"ticker": "XLK", "sector": "Information Technology"},
                {"ticker": "XLY", "sector": "Consumer Cyclical"},
                {"ticker": "XLV", "sector": "Healthcare"},
            ], scout_scope
            assert "STK0" in scout_scope["saved_candidates"] and "TECHF" in scout_scope["saved_candidates"], scout_scope
            assert scout_scope["dynamic_discovery"]["max_stock_tickers_per_sector"] == 20
            app_js = (HERE / "static" / "app.js").read_text(encoding="utf-8")
            assert "Selected sector ETFs:" in app_js and "Current holdings in model context:" in app_js
            assert "Weekly spending check:" in app_js and 'spending.weekly_budget_enabled === false ? "disabled"' in app_js
            assert "Possible new stock symbols:" in app_js and "not known at confirmation" in app_js
            html = (HERE / "static" / "index.html").read_text(encoding="utf-8")
            assert "configured scout model" in html and "Include the Sol call" not in html
            assert "Model-based estimate:" in app_js
            assert '"Sol call is paid"' not in app_js
            assert "Weekly scout included the configured model call" in app_js
            server_py = (HERE / "server.py").read_text(encoding="utf-8")
            assert "weekly configured model call" in server_py
            queued = c.post("/api/theme-scout", json={**scout_request,
                "manifest_sha256": scout_preview.json()["manifest_sha256"], "confirm": True}, headers=headers)
            assert queued.status_code == 200, queued.text
            run_args = queued.json()["run"]["args"]
            sector_start = run_args.index("--scout-sectors")
            assert run_args[sector_start + 1:sector_start + 3] == ["XLK", "XLY"], run_args
            assert "--scout-single-call" in run_args and "--manifest-input-fingerprint" in run_args
            stale_scout = c.post("/api/theme-scout", json={**scout_request,
                "manifest_sha256": scout_preview.json()["manifest_sha256"], "confirm": True}, headers=headers)
            assert stale_scout.status_code == 200, stale_scout.text
            scout_changed = c.post("/api/theme-scout", json={**scout_request, "sectors": ["XLY", "XLK"],
                "manifest_sha256": scout_preview.json()["manifest_sha256"], "confirm": True}, headers=headers)
            assert scout_changed.status_code == 409, scout_changed.text
            too_many_sectors = c.post("/api/theme-scout", json={"mode": "screen", "sectors":
                                                                 [*server.SCOUT_SECTOR_LABELS, "ZZZ"],
                                                                 "confirm": True}, headers=headers)
            assert too_many_sectors.status_code == 400, too_many_sectors.text
        finally:
            server.agent_config.public_payload = original_public_payload
            server._spawn_run = original_spawn

        # Restore the runner fixture after API-specific portfolio assertions.
        (data / "my_book.json").write_text(json.dumps({"positions": [{"ticker": "AAA"}]}), encoding="utf-8")
        (data / "watchlist.json").write_text(json.dumps([{"ticker": "AAA"}]), encoding="utf-8")

        # Exercise the runner using fake add-on scripts: no provider/network access.
        fake_ta = tmp / "fake-ta"
        fm = fake_ta / "addons" / "fund_manager"
        fm.mkdir(parents=True)
        symbols = fake_ta / "tradingagents" / "dataflows"
        symbols.mkdir(parents=True)
        (fake_ta / "tradingagents" / "__init__.py").write_text("\n", encoding="utf-8")
        (symbols / "__init__.py").write_text("\n", encoding="utf-8")
        (symbols / "symbols.py").write_text("def normalize_symbol(value): return value\ndef safe_ticker_component(value): return value\n", encoding="utf-8")
        (fake_ta / "pandas.py").write_text("\n", encoding="utf-8")
        (fake_ta / "yfinance.py").write_text("\n", encoding="utf-8")
        for module in ("langchain_core", "langgraph", "langchain_openai", "langchain_anthropic",
                       "langchain_google_genai", "stockstats"):
            (fake_ta / f"{module}.py").write_text("\n", encoding="utf-8")
        (fake_ta / "addons" / "cost_ledger.py").write_text("raise SystemExit('must not price no-LLM run')\n", encoding="utf-8")
        (fm / "preflight.py").write_text(
            "import sys\nprint('ANALYSIS_DATE=2025-01-02')\nprint('PREFLIGHT_STATUS=ok')\n", encoding="utf-8")
        (fm / "fund_manager.py").write_text(
            "import os, pathlib, sys\n"
            "assert '--no-llm' in sys.argv\n"
            "assert pathlib.Path(os.environ['TRADINGAGENTS_RESULTS_DIR']).is_absolute()\n"
            "pathlib.Path(os.environ['FM_DATA_ROOT'], 'offline-run.txt').write_text('ok')\n", encoding="utf-8")
        (fm / "my_book.json").write_text("{}", encoding="utf-8")
        (fm / "targets.json").write_text("{}", encoding="utf-8")
        (fake_ta / "addons" / "agent_config.py").write_text(
            "from pathlib import Path\n"
            "def config_path(): return Path(__file__).with_name('agent_config.json')\n"
            "def models_path(): return Path(__file__).with_name('openrouter_models.json')\n",
            encoding="utf-8")
        (fake_ta / "addons" / "agent_config.json").write_text("{}\n", encoding="utf-8")
        (fake_ta / "addons" / "openrouter_models.json").write_text("{}\n", encoding="utf-8")
        (data / "my_book.json").write_text(json.dumps({"positions": [{"ticker": "AAA"}]}), encoding="utf-8")
        run = subprocess.run([
            sys.executable, str(HERE / "run_analysis.py"), "--ta-root", str(fake_ta), "--no-llm",
            "--run-agents", "--include-watchlist", "--tickers", "AAA",
        ], env={**os.environ, "FM_DATA_ROOT": str(data)}, cwd=fake_ta, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20)
        assert run.returncode == 0, run.stdout
        assert "STAGE=native:" not in run.stdout, run.stdout
        assert (data / "offline-run.txt").is_file(), run.stdout
        assert (data / "offline-run.txt").read_text(encoding="utf-8") == "ok", run.stdout
        from run_inputs import fingerprint as fingerprint_run_inputs
        expected_inputs = fingerprint_run_inputs(data, fake_ta, {
            "agent_config": fake_ta / "addons" / "agent_config.json",
            "model_rates": fake_ta / "addons" / "openrouter_models.json",
        })["sha256"]
        verified = subprocess.run([
            sys.executable, str(HERE / "run_analysis.py"), "--ta-root", str(fake_ta),
            "--data-root", str(data), "--manifest-input-fingerprint", expected_inputs,
            "--manifest-analysis-tickers-json", "[]", "--no-llm",
        ], env=os.environ.copy(), cwd=fake_ta, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20)
        assert verified.returncode == 0, verified.stdout
        wrong_scope = subprocess.run([
            sys.executable, str(HERE / "run_analysis.py"), "--ta-root", str(fake_ta),
            "--data-root", str(data), "--manifest-input-fingerprint", expected_inputs,
            "--manifest-analysis-tickers-json", '["BBB"]', "--run-agents", "--tickers", "AAA",
        ], env=os.environ.copy(), cwd=fake_ta, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20)
        assert wrong_scope.returncode == 78 and "selected ticker scope changed" in wrong_scope.stdout, wrong_scope.stdout
        before_book = (data / "my_book.json").read_bytes()
        changed_book = json.loads(before_book)
        changed_book["positions"][0]["quantity"] = 99
        (data / "my_book.json").write_text(json.dumps(changed_book), encoding="utf-8")
        rejected = subprocess.run([
            sys.executable, str(HERE / "run_analysis.py"), "--ta-root", str(fake_ta),
            "--data-root", str(data), "--manifest-input-fingerprint", expected_inputs,
            "--manifest-analysis-tickers-json", "[]", "--no-llm",
        ], env=os.environ.copy(), cwd=fake_ta, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20)
        assert rejected.returncode == 78 and "changed after review" in rejected.stdout, rejected.stdout
        (data / "my_book.json").write_bytes(before_book)
        scout_dir = fake_ta / "addons" / "theme_scout"
        scout_dir.mkdir(parents=True)
        (scout_dir / "theme_scout.py").write_text(
            "import json, os, pathlib, sys\n"
            "pathlib.Path(os.environ['FM_DATA_ROOT'], 'scout-args.json').write_text(json.dumps(sys.argv))\n",
            encoding="utf-8")
        scoped = subprocess.run([
            sys.executable, str(HERE / "run_analysis.py"), "--ta-root", str(fake_ta),
            "--scout-mode", "screen", "--scout-sectors", "XLK", "XLY",
        ], env={**os.environ, "FM_DATA_ROOT": str(data)}, cwd=fake_ta, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20)
        assert scoped.returncode == 0, scoped.stdout
        scout_args = json.loads((data / "scout-args.json").read_text(encoding="utf-8"))
        sector_at = scout_args.index("--sectors")
        assert scout_args[sector_at + 1:sector_at + 3] == ["XLK", "XLY"] and "--screen" in scout_args, scout_args
        print("argus check_offline: ok")
        print(f"  log events {len(log) + 2}, spend {s['spent_usd']} of {s['budget_usd']}")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
