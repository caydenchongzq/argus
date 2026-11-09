"""Verify budget dates use today and watchlist agent selection is independent."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run_analysis import _tickers


def run(script, ta: Path, data: Path, env: dict[str, str], *args: str, allow_failure: bool = False):
    result = subprocess.run([sys.executable, str(HERE / script), "--ta-root", str(ta), *args],
                            cwd=ta, env={**env, "FM_DATA_ROOT": str(data)}, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
    if not allow_failure:
        assert result.returncode == 0, result.stdout
    else:
        assert result.returncode != 0, result.stdout
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
        wrapper_watch = data / "wrapper-watchlist.json"
        wrapper_book = data / "wrapper-book.json"
        wrapper_book.write_text(json.dumps({"positions": [{"ticker": "AAA"}]}), encoding="utf-8")
        wrapper_watch.write_text(json.dumps({"items": [], "candidates": [{"ticker": "IGNORED"}]}), encoding="utf-8")
        assert _tickers(wrapper_book, wrapper_watch, [], True) == (["AAA"], [])
        wrapper_watch.write_text(json.dumps({"items": None, "candidates": [{"ticker": "CCC"}]}), encoding="utf-8")
        assert _tickers(wrapper_book, wrapper_watch, [], True) == (["AAA"], ["CCC"])
        # A template is available, but must not be copied into user data.
        (fm / "targets.json").write_text(json.dumps({"weights_pct": {"EXAMPLE": 50}}), encoding="utf-8")
        (fm / "preflight.py").write_text(
            "import sys\n"
            "assert sys.argv[sys.argv.index('--tickers') + 1] in ('AAA,BBB,CCC','AAA'), sys.argv\n"
            "print('ANALYSIS_DATE=2001-01-02')\n", encoding="utf-8")
        (ta / "addons" / "cost_ledger.py").write_text(
            "import datetime, json, os, pathlib, sys\n"
            "args=sys.argv\n"
            "assert args[args.index('--date')+1] == datetime.datetime.now(datetime.timezone.utc).date().isoformat(), args\n"
            "p=pathlib.Path(os.environ['BUDGET_CALLS_FILE'])\n"
            "with p.open('a') as f: f.write(args[args.index('--kind')+1]+'\\n')\n"
            "if '--next' in args and float(args[args.index('--next')+1]) > float(os.environ.get('BUDGET_LIMIT','100')): sys.exit(9)\n"
            "print('BUDGET_OK')\n", encoding="utf-8")
        (fm / "run_native.py").write_text(
            "import os, pathlib, sys\n"
            "p=pathlib.Path(os.environ['NATIVE_CALLS_FILE'])\n"
            "with p.open('a') as f: f.write(sys.argv[sys.argv.index('--ticker')+1]+'\\n')\n"
            "if os.environ.get('FAIL_NATIVE'): sys.exit(7)\n",
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
        assert sorted(budget_calls.read_text().splitlines()) == ["fund_manager", "manifest", "native"]
        assert (data / "fund-manager-called").exists()
        assert not (data / "targets.json").exists(), "example allocation policy was copied into user data"

        # The aggregate allowance check blocks every paid stage before an insufficient bundle starts.
        (data / "fund-manager-called").unlink()
        native_before = native_calls.read_text().splitlines()
        blocked = run("run_analysis.py", ta, data, {**os.environ, "BUDGET_CALLS_FILE": str(budget_calls),
                        "NATIVE_CALLS_FILE": str(native_calls), "BUDGET_LIMIT": "3"},
                      "--analysis-date", "2001-01-02", "--include-watchlist", allow_failure=True)
        assert "RUN_MANIFEST_BUDGET_BLOCKED=1" in blocked, blocked
        assert native_calls.read_text().splitlines() == native_before
        assert not (data / "fund-manager-called").exists()

        failed = run("run_analysis.py", ta, data, {**os.environ, "BUDGET_CALLS_FILE": str(budget_calls),
                      "NATIVE_CALLS_FILE": str(native_calls), "FAIL_NATIVE": "1"},
                     "--analysis-date", "2001-01-02", "--include-watchlist", allow_failure=True)
        assert "Native analyses failed; stopping before fund manager: CCC" in failed, failed
        assert not (data / "fund-manager-called").exists(), "fund manager ran with incomplete selected ticker analysis"

        # Standalone ANL runs only the selected native stage and does not start REV.
        anl_only = run("run_analysis.py", ta, data, {**os.environ, "BUDGET_CALLS_FILE": str(budget_calls),
                         "NATIVE_CALLS_FILE": str(native_calls)}, "--run-agents", "--anl-only",
                       "--tickers", "AAA", "--analysis-date", "2001-01-02")
        assert "ANL_ONLY_COMPLETE=AAA" in anl_only, anl_only
        assert native_calls.read_text().splitlines()[-1] == "AAA"
        assert not (data / "fund-manager-called").exists(), "ANL-only must stop before REV"
    print("argus runner budget offline check: ok (UTC gate, failure stop, standalone ANL, no-LLM and bundle scopes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
