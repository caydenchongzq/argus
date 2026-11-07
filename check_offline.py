"""Offline check for the watchlist change log, undo, and weekly spend endpoints.

Uses a temp TradingAgents root with a copy of the real add-ons. No network, no model call,
and the real data folder is not touched.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    real_ta = Path(os.environ.get("TRADINGAGENTS_ROOT", r"D:\software development\trading\TradingAgents"))
    tmp = Path(tempfile.mkdtemp(prefix="argus_check_"))
    try:
        shutil.copytree(real_ta / "addons", tmp / "addons", ignore=shutil.ignore_patterns(".git", "__pycache__", "*.bak*"))
        data = tmp / "data"
        (data / "fund_manager" / "run_costs").mkdir(parents=True)
        (data / "watchlist.json").write_text(json.dumps([{"ticker": "AAA", "sector": "X", "type": "stock"}]), encoding="utf-8")
        (data / "targets.json").write_text(json.dumps({"weekly_budget_usd": 25}), encoding="utf-8")
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
        r = c.post("/api/watchlist", json={"ticker": "BBB", "sector": "Y", "type": "stock"})
        assert r.status_code == 200, r.text
        r = c.delete("/api/watchlist/AAA")
        assert r.status_code == 200, r.text
        log = [json.loads(x) for x in (data / "watchlist_log.jsonl").read_text(encoding="utf-8").splitlines()]
        assert [e["action"] for e in log] == ["add", "drop"], log
        assert list(data.glob("*.bak*")) == [], list(data.glob("*.bak*"))
        r = c.post("/api/watchlist/undo", json={})
        assert r.status_code == 200, r.text
        tickers = sorted(i["ticker"] for i in r.json()["items"])
        assert tickers == ["AAA", "BBB"], tickers
        r = c.post("/api/watchlist/undo", json={})
        assert r.status_code == 200 and [i["ticker"] for i in r.json()["items"]] == ["AAA"], r.text
        r = c.post("/api/watchlist/undo", json={})
        assert r.status_code == 404, r.text
        s = c.get("/api/spend").json()
        assert s["spent_usd"] == 1.25 and s["budget_usd"] == 25, s
        print("argus check_offline: ok")
        print(f"  log events {len(log) + 2}, spend {s['spent_usd']} of {s['budget_usd']}")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
