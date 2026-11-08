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
        assert s["spent_usd"] == 1.25 and s["budget_usd"] == 25, s

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
        print("argus check_offline: ok")
        print(f"  log events {len(log) + 2}, spend {s['spent_usd']} of {s['budget_usd']}")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
