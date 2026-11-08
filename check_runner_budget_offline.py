"""Verify budget dates use today and watchlist agent selection is independent."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(script, ta: Path, data: Path, env: dict[str, str], *args: str):
    result = subprocess.run([sys.executable, str(HERE / script), "--ta-root", str(ta), *args],
                            cwd=ta, env={**env, "FM_DATA_ROOT": str(data)}, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
    assert result.returncode == 0, result.stdout
    return result.stdout


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="argus_budget_check_") as folder:
        root = Path(folder)
        ta = root / "ta"
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
        (data / "watchlist.json").write_text(json.dumps([{"ticker": "AAA"}, {"ticker": "CCC"}]), encoding="utf-8")
        (data / "targets.json").write_text("{}\n", encoding="utf-8")
        (fm / "preflight.py").write_text(
            "import sys\n"
            "assert sys.argv[sys.argv.index('--tickers') + 1] == 'AAA,BBB,CCC', sys.argv\n"
            "print('ANALYSIS_DATE=2001-01-02')\n", encoding="utf-8")
        (ta / "addons" / "cost_ledger.py").write_text(
            "import datetime, json, os, pathlib, sys\n"
            "args=sys.argv\n"
            "assert args[args.index('--date')+1] == datetime.datetime.now(datetime.timezone.utc).date().isoformat(), args\n"
            "p=pathlib.Path(os.environ['BUDGET_CALLS_FILE'])\n"
            "with p.open('a') as f: f.write(args[args.index('--kind')+1]+'\\n')\n"
            "print('BUDGET_OK')\n", encoding="utf-8")
        (fm / "run_native.py").write_text(
            "import os, pathlib, sys\n"
            "p=pathlib.Path(os.environ['NATIVE_CALLS_FILE'])\n"
            "with p.open('a') as f: f.write(sys.argv[sys.argv.index('--ticker')+1]+'\\n')\n",
            encoding="utf-8")
        (fm / "fund_manager.py").write_text(
            "import os, pathlib, sys\n"
            "assert '--no-llm' not in sys.argv\n"
            "pathlib.Path(os.environ['FM_DATA_ROOT'], 'fund-manager-called').write_text('ok')\n",
            encoding="utf-8")
        (fm / "themes.json").write_text("{}\n", encoding="utf-8")
        budget_calls, native_calls = root / "budget-calls", root / "native-calls"
        out = run("run_analysis.py", ta, data, {**os.environ, "BUDGET_CALLS_FILE": str(budget_calls),
                   "NATIVE_CALLS_FILE": str(native_calls)}, "--analysis-date", "2001-01-02",
                  "--include-watchlist")
        assert "STAGE=native:CCC" in out, out
        assert native_calls.read_text().splitlines() == ["CCC"]
        assert sorted(budget_calls.read_text().splitlines()) == ["fund_manager", "native"]
        assert (data / "fund-manager-called").exists()
    print("argus runner budget offline check: ok (UTC budget date, historical analysis date, independent watchlist agents)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
