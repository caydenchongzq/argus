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
        real_addons = HERE.parent / "TradingAgents" / "addons"
        (ta / "addons" / "portfolio_book.py").write_text(
            (real_addons / "portfolio_book.py").read_text(encoding="utf-8"), encoding="utf-8")
        (fm / "trade_validation.py").write_text(
            (real_addons / "fund_manager" / "trade_validation.py").read_text(encoding="utf-8"),
            encoding="utf-8")
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
        (data / "my_book.json").write_text(json.dumps({
            "positions": [{"ticker": "AAA", "quantity": 1}, {"ticker": "BBB", "quantity": 1}],
            "cash": 0, "currency": "USD"}), encoding="utf-8")
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
            "def reconcile_attempt_journals(data_root):\n"
            " p=pathlib.Path(os.environ['RECONCILIATION_CALLS_FILE'])\n"
            " with p.open('a') as f: f.write('reconcile\\n')\n"
            " with pathlib.Path(os.environ['BUDGET_EVENTS_FILE']).open('a') as f: f.write('reconcile\\n')\n"
            " return {'journal_count': 1, 'response_count': 1, 'reconciled_count': 1, 'failures': ['fixture failure'] if os.environ.get('RECONCILE_FAIL') else []}\n"
            "if __name__ == '__main__':\n"
            " args=sys.argv\n"
            " assert args[args.index('--date')+1] == datetime.datetime.now(datetime.timezone.utc).date().isoformat(), args\n"
            " p=pathlib.Path(os.environ['BUDGET_CALLS_FILE'])\n"
            " with p.open('a') as f: f.write(args[args.index('--kind')+1]+'\\n')\n"
            " with pathlib.Path(os.environ['BUDGET_EVENTS_FILE']).open('a') as f: f.write('budget:'+args[args.index('--kind')+1]+'\\n')\n"
            " if '--next' in args and float(args[args.index('--next')+1]) > float(os.environ.get('BUDGET_LIMIT','100')): sys.exit(9)\n"
            " print('BUDGET_OK')\n", encoding="utf-8")
        (fm / "run_native.py").write_text(
            "import os, pathlib, sys\n"
            "assert '--research-only' in sys.argv and '--no-checkpoint' in sys.argv, sys.argv\n"
            "assert '--portfolio' not in sys.argv, sys.argv\n"
            "assert os.environ.get('ARGUS_RESEARCH_ONLY') == '1'\n"
            "assert os.environ.get('TRADINGAGENTS_MEMORY_LOG_PATH', '').endswith('research_only_memory.md')\n"
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
        reconciliation_calls = root / "reconciliation-calls"
        budget_events = root / "budget-events"
        out = run("run_analysis.py", ta, data, {**os.environ, "BUDGET_CALLS_FILE": str(budget_calls),
                   "NATIVE_CALLS_FILE": str(native_calls), "RECONCILIATION_CALLS_FILE": str(reconciliation_calls),
                   "BUDGET_EVENTS_FILE": str(budget_events)}, "--analysis-date", "2001-01-02",
                  "--include-watchlist")
        assert "STAGE=native:CCC" in out, out
        assert "COST_JOURNALS_RECONCILED=1/1" in out, out
        assert reconciliation_calls.read_text().splitlines() == ["reconcile"] * 3
        assert budget_events.read_text().splitlines() == [
            "reconcile", "budget:manifest", "reconcile", "budget:native", "reconcile", "budget:fund_manager",
        ], budget_events.read_text()
        assert native_calls.read_text().splitlines() == ["CCC"]
        assert sorted(budget_calls.read_text().splitlines()) == ["fund_manager", "manifest", "native"]
        assert (data / "fund-manager-called").exists()
        assert not (data / "targets.json").exists(), "example allocation policy was copied into user data"

        # The aggregate allowance check blocks every paid stage before an insufficient bundle starts.
        (data / "fund-manager-called").unlink()
        native_before = native_calls.read_text().splitlines()
        blocked = run("run_analysis.py", ta, data, {**os.environ, "BUDGET_CALLS_FILE": str(budget_calls),
                        "NATIVE_CALLS_FILE": str(native_calls), "RECONCILIATION_CALLS_FILE": str(reconciliation_calls),
                        "BUDGET_EVENTS_FILE": str(budget_events), "BUDGET_LIMIT": "3"},
                      "--analysis-date", "2001-01-02", "--include-watchlist", allow_failure=True)
        assert "RUN_MANIFEST_BUDGET_BLOCKED=1" in blocked, blocked
        assert native_calls.read_text().splitlines() == native_before
        assert not (data / "fund-manager-called").exists()

        failed = run("run_analysis.py", ta, data, {**os.environ, "BUDGET_CALLS_FILE": str(budget_calls),
                      "NATIVE_CALLS_FILE": str(native_calls), "RECONCILIATION_CALLS_FILE": str(reconciliation_calls),
                      "BUDGET_EVENTS_FILE": str(budget_events), "FAIL_NATIVE": "1"},
                     "--analysis-date", "2001-01-02", "--include-watchlist", allow_failure=True)
        assert "Native analyses failed; stopping before fund manager: CCC" in failed, failed
        assert not (data / "fund-manager-called").exists(), "fund manager ran with incomplete selected ticker analysis"

        # Standalone ANL runs only the selected native stage and does not start REV.
        anl_only = run("run_analysis.py", ta, data, {**os.environ, "BUDGET_CALLS_FILE": str(budget_calls),
                         "NATIVE_CALLS_FILE": str(native_calls), "RECONCILIATION_CALLS_FILE": str(reconciliation_calls),
                         "BUDGET_EVENTS_FILE": str(budget_events)}, "--run-agents", "--anl-only",
                       "--tickers", "AAA", "--analysis-date", "2001-01-02")
        assert "ANL_ONLY_COMPLETE=AAA" in anl_only, anl_only
        assert native_calls.read_text().splitlines()[-1] == "AAA"
        assert not (data / "fund-manager-called").exists(), "ANL-only must stop before REV"

        # A fund-manager-only run reuses saved research without invoking any stock agent.
        native_before = native_calls.read_text().splitlines()
        manager_only = run("run_analysis.py", ta, data, {**os.environ, "BUDGET_CALLS_FILE": str(budget_calls),
                               "NATIVE_CALLS_FILE": str(native_calls), "RECONCILIATION_CALLS_FILE": str(reconciliation_calls),
                               "BUDGET_EVENTS_FILE": str(budget_events)}, "--analysis-date", "2001-01-02")
        assert "STAGE=fund_manager" in manager_only, manager_only
        assert native_calls.read_text().splitlines() == native_before, "fund-manager-only must not rerun stock agents"
        (data / "fund-manager-called").unlink()

        # A ledger reconciliation failure blocks before budget checks or paid stages.
        budget_before = budget_calls.read_text().splitlines()
        native_before = native_calls.read_text().splitlines()
        failed_reconcile = run("run_analysis.py", ta, data, {**os.environ, "BUDGET_CALLS_FILE": str(budget_calls),
                                "NATIVE_CALLS_FILE": str(native_calls), "RECONCILIATION_CALLS_FILE": str(reconciliation_calls),
                                "BUDGET_EVENTS_FILE": str(budget_events),
                                "RECONCILE_FAIL": "1"}, "--analysis-date", "2001-01-02", "--include-watchlist",
                               allow_failure=True)
        assert "RUN_COST_RECONCILIATION_FAILED=fixture failure" in failed_reconcile, failed_reconcile
        assert budget_calls.read_text().splitlines() == budget_before, "budget checks must not run after reconciliation failure"
        assert native_calls.read_text().splitlines() == native_before, "paid ticker analyses must not start after reconciliation failure"
        assert not (data / "fund-manager-called").exists(), "fund manager must not start after reconciliation failure"
        assert budget_events.read_text().splitlines()[-1] == "reconcile", "failed reconciliation must precede and block the budget call"
    print("argus runner budget offline check: ok (UTC gate, failure stop, standalone ANL, no-LLM and bundle scopes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
