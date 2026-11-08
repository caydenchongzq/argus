"""Run the native runner end to end against fake TradingAgents scripts."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="argus_runner_check_") as folder:
        root = Path(folder)
        ta = root / "fake-ta"
        fm = ta / "addons" / "fund_manager"
        fm.mkdir(parents=True)
        symbols = ta / "tradingagents" / "dataflows"
        symbols.mkdir(parents=True)
        (ta / "tradingagents" / "__init__.py").write_text("\n", encoding="utf-8")
        (symbols / "__init__.py").write_text("\n", encoding="utf-8")
        (symbols / "symbols.py").write_text("def normalize_symbol(value): return value\ndef safe_ticker_component(value): return value\n", encoding="utf-8")
        (ta / "pandas.py").write_text("\n", encoding="utf-8")
        (ta / "yfinance.py").write_text("\n", encoding="utf-8")
        for module in ("langchain_core", "langgraph", "langchain_openai", "langchain_anthropic",
                       "langchain_google_genai", "stockstats"):
            (ta / f"{module}.py").write_text("\n", encoding="utf-8")
        data = root / "data"
        (data / "fund_manager" / "run_costs").mkdir(parents=True)
        (data / "my_book.json").write_text(json.dumps({"positions": [{"ticker": "AAA"}, {"ticker": "BBB"}]}), encoding="utf-8")
        (data / "watchlist.json").write_text(json.dumps([{"ticker": "CCC"}]), encoding="utf-8")
        (data / "targets.json").write_text("{}\n", encoding="utf-8")
        (ta / "addons" / "cost_ledger.py").write_text(
            "raise SystemExit('no-LLM run must not check budget')\n", encoding="utf-8")
        (fm / "preflight.py").write_text(
            "import sys\n"
            "assert sys.argv[sys.argv.index('--tickers') + 1] == 'AAA,BBB,CCC', sys.argv\n"
            "print('ANALYSIS_DATE=2025-01-02')\nprint('PREFLIGHT_STATUS=ok')\n", encoding="utf-8")
        (fm / "fund_manager.py").write_text(
            "import os, pathlib, sys\n"
            "assert '--no-llm' in sys.argv\n"
            "assert pathlib.Path(os.environ['TRADINGAGENTS_RESULTS_DIR']).is_absolute()\n"
            "pathlib.Path(os.environ['FM_DATA_ROOT'], 'runner-invoked.txt').write_text('ok')\n",
            encoding="utf-8")
        result_path = root / "runs" / "result.json"
        initial_state_path = root / "runs" / "meta.json"
        initial_state_path.parent.mkdir()
        original_state = {"id": "fixture", "status": "running", "pid": 123}
        initial_state_path.write_text(json.dumps(original_state), encoding="utf-8")
        proc = subprocess.run([
            sys.executable, str(HERE / "run_analysis.py"), "--ta-root", str(ta),
            "--no-llm", "--include-watchlist", "--tickers", "AAA",
        ], env={**os.environ, "FM_DATA_ROOT": str(data), "ARGUS_RUN_RESULT_FILE": str(result_path)},
            cwd=ta, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20)
        assert proc.returncode == 0, proc.stdout
        assert "STAGE=preflight" in proc.stdout and "STAGE=fund_manager" in proc.stdout, proc.stdout
        assert "STAGE=native:" not in proc.stdout and "STAGE=budget:" not in proc.stdout, proc.stdout
        assert (data / "runner-invoked.txt").read_text(encoding="utf-8") == "ok"
        assert json.loads(result_path.read_text(encoding="utf-8"))["status"] == "succeeded"
        assert json.loads(initial_state_path.read_text(encoding="utf-8")) == original_state
    print("argus runner offline check: ok (entry point, stages, no-paid path, result sidecar)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
