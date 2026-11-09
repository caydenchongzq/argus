"""Native Linux runner shared by Argus dashboard run requests.

This translates the useful stages of TradingAgents' Windows portfolio wrapper
to local Python commands. It does not alter TradingAgents source or perform
orders. `--no-llm` suppresses every model stage in this complete pipeline.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import subprocess
import sys
import traceback
from datetime import date, datetime, timezone
from pathlib import Path
import importlib

from run_inputs import fingerprint as _fingerprint_run_inputs

ROOT = Path(__file__).resolve().parent

TA_RUNTIME_IMPORT_CHECK = (
    "import pandas, yfinance, langchain_core, langgraph, langchain_openai, "
    "langchain_anthropic, langchain_google_genai, stockstats; "
    "from tradingagents.dataflows.symbols import normalize_symbol, safe_ticker_component"
)

if os.name == "nt":
    import msvcrt
else:
    import fcntl


def _run(args: list[str], *, cwd: Path, env: dict[str, str], label: str) -> tuple[int, str]:
    print(f"STAGE={label}", flush=True)
    proc = subprocess.Popen(args, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, bufsize=1)
    output = []
    assert proc.stdout is not None
    for line in proc.stdout:
        print(line, end="", flush=True)
        output.append(line)
    return proc.wait(), "".join(output)


def _script_command(python: str, ta: Path, script: Path, *args: str) -> list[str]:
    """Load TradingAgents' runtime environment without emitting its contents."""
    env_files = (ta / ".env", ta / ".env.enterprise")
    if any(path.is_file() for path in env_files):
        return [python, str(ROOT / "exec_ta.py"), str(ta), str(script), *args]
    return [python, str(script), *args]


def _tickers(book_path: Path, watch_path: Path, selected: list[str], include_watchlist: bool) -> tuple[list[str], list[str]]:
    book = json.loads(book_path.read_text(encoding="utf-8"))
    holdings = list(dict.fromkeys(str(p.get("ticker", "")).strip().upper()
                                  for p in book.get("positions", []) if p.get("ticker")))
    watch = []
    if include_watchlist and watch_path.exists():
        raw = json.loads(watch_path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            raw = next((raw.get(key) for key in ("items", "candidates", "watchlist", "tickers")
                        if isinstance(raw.get(key), list)), [])
        watch = list(dict.fromkeys(str(p if isinstance(p, str) else p.get("ticker", "")).strip().upper()
                                     for p in raw if (p if isinstance(p, str) else p.get("ticker"))))
        # A held symbol is already covered by the holdings run, even when no
        # explicit ticker selection was supplied.
        watch = [ticker for ticker in watch if ticker not in holdings]
    if selected:
        allow = set(selected)
        holdings = [t for t in holdings if t in allow]
        watch = [t for t in watch if t in allow]
    return holdings, watch


def _budget(python: str, addons: Path, root: Path, day: str, kind: str, cwd: Path, env: dict[str, str],
            next_usd: float | None = None) -> int:
    command = _script_command(python, cwd, addons / "cost_ledger.py", "--data-root", str(root),
                              "--date", day, "--kind", kind)
    if next_usd is not None:
        command.extend(["--next", str(next_usd)])
    code, _ = _run(command, cwd=cwd, env=env, label=f"budget:{kind}")
    return code


def _set_run_state(status: str, **updates) -> None:
    raw = os.environ.get("ARGUS_RUN_RESULT_FILE")
    if not raw:
        return
    path = Path(raw)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({**updates, "status": status}, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def _check_ta_runtime(python: str, ta: Path, env: dict[str, str]) -> bool:
    """Fail before any stage when the selected interpreter lacks TA dependencies."""
    result = subprocess.run([python, "-c", TA_RUNTIME_IMPORT_CHECK], cwd=ta, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if result.returncode == 0:
        return True
    print(
        "TradingAgents runtime dependencies are missing for the selected Python. "
        "Run ./setup_tradingagents_env.sh or set TRADINGAGENTS_PYTHON to a prepared environment.",
        flush=True,
    )
    return False


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ta-root", required=True, type=Path)
    ap.add_argument("--data-root", type=Path, default=None,
                    help="portfolio data directory (defaults to FM_DATA_ROOT or <ta-root>/data)")
    ap.add_argument("--analysis-date", default="")
    ap.add_argument("--since", default="")
    ap.add_argument("--tickers", nargs="*", default=[])
    ap.add_argument("--run-agents", action="store_true")
    ap.add_argument("--anl-only", action="store_true", help="run selected ticker analyses and stop before portfolio review")
    ap.add_argument("--include-watchlist", action="store_true")
    ap.add_argument("--no-watchlist", action="store_true")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--include-risk", action="store_true")
    ap.add_argument("--no-macro", action="store_true")
    ap.add_argument("--scout-mode", choices=["screen", "weekly"])
    ap.add_argument("--scout-llm", action="store_true")
    ap.add_argument("--scout-sectors", nargs="*", default=[])
    ap.add_argument("--scout-single-call", action="store_true",
                    help="disable automatic scout model retries for an explicitly reviewed one-call run")
    ap.add_argument("--manifest-input-fingerprint", default="",
                    help="expected portfolio and model-input fingerprint from the reviewed manifest")
    ap.add_argument("--manifest-analysis-tickers-json", default="",
                    help="expected selected ticker execution scope from the reviewed manifest")
    args = ap.parse_args(argv)
    if args.anl_only and args.no_llm:
        ap.error("--anl-only requires paid ticker analysis and cannot be combined with --no-llm")
    if args.anl_only and not args.tickers:
        ap.error("--anl-only requires explicit --tickers")

    ta = args.ta_root.resolve()
    default_python = ta / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python")
    python = os.environ.get("TRADINGAGENTS_PYTHON") or (str(default_python) if default_python.is_file() else sys.executable)
    addons = ta / "addons"
    fm = addons / "fund_manager"
    root = (args.data_root or Path(os.environ.get("FM_DATA_ROOT", str(ta / "data")))).resolve()
    lock_path = root / ".argus-run.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as lock:
        try:
            if os.name == "nt":
                lock.seek(0, os.SEEK_END)
                if lock.tell() == 0:
                    lock.write("0")
                    lock.flush()
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("RUN_SKIPPED=busy: another Argus analysis is running", flush=True)
            return 75

        env = os.environ.copy()
        env.update({
            "FM_DATA_ROOT": str(root),
            "TRADINGAGENTS_RESULTS_DIR": str(root / "logs"),
            "TRADINGAGENTS_CACHE_DIR": str(root / "cache"),
            "TZ": "EST5EDT,M3.2.0,M11.1.0",
        })
        if args.manifest_input_fingerprint:
            addon_path = str(addons)
            if addon_path not in sys.path:
                sys.path.insert(0, addon_path)
            try:
                agent_config = importlib.import_module("agent_config")
                input_hash = _fingerprint_run_inputs(root, ta, {
                    "agent_config": Path(agent_config.config_path()),
                    "model_rates": Path(agent_config.models_path()),
                })["sha256"]
            except Exception as exc:
                print(f"RUN_MANIFEST_INVALID=agent configuration unavailable: {exc}", flush=True)
                return 78
            if input_hash != args.manifest_input_fingerprint:
                print("RUN_MANIFEST_INVALID=portfolio inputs or model configuration changed after review", flush=True)
                _set_run_state("failed", exit_code=78,
                               error="portfolio inputs or model configuration changed after review")
                return 78
            if not args.scout_mode and not args.manifest_analysis_tickers_json:
                print("RUN_MANIFEST_INVALID=expected ticker scope is missing", flush=True)
                return 78
        if not _check_ta_runtime(python, ta, env):
            _set_run_state("failed", exit_code=78, error="TradingAgents runtime dependencies missing")
            return 78
        root.mkdir(parents=True, exist_ok=True)
        (root / "logs" / "reports").mkdir(parents=True, exist_ok=True)
        (root / "cache").mkdir(parents=True, exist_ok=True)
        (root / "fund_manager").mkdir(parents=True, exist_ok=True)
        budget_day = datetime.now(timezone.utc).date().isoformat()
        # Theme scout can run its screen with an empty/missing portfolio book.
        if args.scout_mode:
            day = args.analysis_date or date.today().isoformat()
            if args.scout_mode == "weekly" and args.scout_llm:
                code = _budget(python, addons, root, budget_day, "check", ta, env, 0.3)
                if code:
                    return code
            scout = addons / "theme_scout" / "theme_scout.py"
            command = _script_command(python, ta, scout, "--data-root", str(root), "--date", day,
                                      "--themes", str(fm / "themes.json"))
            if args.scout_sectors:
                command.extend(["--sectors", *args.scout_sectors])
            if args.scout_mode == "screen":
                command.append("--screen")
            elif not args.scout_llm:
                command.append("--no-llm")
            if args.scout_single_call:
                if args.scout_mode != "weekly" or not args.scout_llm:
                    print("RUN_MANIFEST_INVALID=single-call is valid only for paid weekly scout", flush=True)
                    return 78
                command.append("--single-call")
            code, _ = _run(command, cwd=ta, env=env, label="theme_scout")
            return code

        book_path = root / "my_book.json"
        if not book_path.is_file():
            print(f"Portfolio book missing: {book_path}", flush=True)
            return 2
        watch_path = root / "watchlist.json"
        agent_holdings, agent_candidates = _tickers(book_path, watch_path, args.tickers,
                                                      not args.no_watchlist)
        agent_tickers = list(dict.fromkeys(
            (agent_holdings if args.run_agents else [])
            + (agent_candidates if args.include_watchlist else [])
        ))
        if args.anl_only and not agent_tickers:
            print("ANL-only selected scope contains no eligible tickers", flush=True)
            return 2
        if args.manifest_analysis_tickers_json:
            if args.no_llm:
                actual_tickers = []
            else:
                actual_tickers = agent_tickers
            try:
                expected_tickers = json.loads(args.manifest_analysis_tickers_json)
                if not isinstance(expected_tickers, list) or any(not isinstance(t, str) for t in expected_tickers):
                    raise ValueError("expected ticker scope must be a JSON list of strings")
            except (json.JSONDecodeError, ValueError) as exc:
                print(f"RUN_MANIFEST_INVALID=invalid ticker scope: {exc}", flush=True)
                return 78
            if actual_tickers != expected_tickers:
                print("RUN_MANIFEST_INVALID=selected ticker scope changed after review", flush=True)
                _set_run_state("failed", exit_code=78,
                               error="selected ticker scope changed after review")
                return 78
        if not watch_path.exists():
            watch_path.write_text("[]\n", encoding="utf-8")
        # Owner policy is user data. Never seed it from the example template;
        # the fund manager treats absent targets as no approved allocation mandate.

        # Preflight the full book and every watchlist row the fund manager may consume.
        # The ticker filter narrows native per-ticker analyses only.
        if args.anl_only:
            selected_holdings, selected_candidates = _tickers(book_path, watch_path, args.tickers,
                                                               not args.no_watchlist)
            all_tickers = list(dict.fromkeys(
                (selected_holdings if args.run_agents else [])
                + (selected_candidates if args.include_watchlist else [])
            ))
        else:
            holdings, candidates = _tickers(book_path, watch_path, [], not args.no_watchlist)
            all_tickers = list(dict.fromkeys(holdings + candidates))
        if not all_tickers:
            print("No tickers to preflight", flush=True)
            return 2
        day = args.analysis_date or "auto"
        preflight = _script_command(python, ta, fm / "preflight.py", "--tickers", ",".join(all_tickers),
                                    "--cache-dir", str(root / "cache"), "--out",
                                    str(root / "fund_manager" / "preflight_latest.json"))
        if day != "auto":
            preflight.extend(["--analysis-date", day])
        run_native_agents = (args.run_agents or args.include_watchlist) and not args.no_llm
        if run_native_agents:
            preflight.append("--block-intraday")
        code, output = _run(preflight, cwd=ta, env=env, label="preflight")
        if code:
            return code
        for line in output.splitlines():
            if line.startswith("ANALYSIS_DATE="):
                day = line.partition("=")[2].strip()
                break
        if day == "auto":
            day = date.today().isoformat()

        native_failed = []
        if not run_native_agents:
            agent_tickers = []
        if args.anl_only and not agent_tickers:
            print("ANL-only selected scope contains no eligible tickers", flush=True)
            return 2

        if not args.no_llm:
            try:
                targets = json.loads((root / "targets.json").read_text(encoding="utf-8")) if (root / "targets.json").is_file() else {}
            except json.JSONDecodeError:
                print("Could not read budget policy; stopping before paid stages", flush=True)
                return 2
            policy = targets.get("budget") or {}
            native_estimate = float(policy.get("native_run_estimate_usd", 2.0))
            fm_estimate = float(policy.get("fund_manager_estimate_usd", 1.5))
            planned_estimate = len(agent_tickers) * native_estimate + (0 if args.anl_only else fm_estimate)
            code = _budget(python, addons, root, budget_day, "manifest", ta, env, planned_estimate)
            if code:
                print("RUN_MANIFEST_BUDGET_BLOCKED=1; no paid stage was started", flush=True)
                return code

        if run_native_agents:
            for ticker in agent_tickers:
                code = _budget(python, addons, root, budget_day, "native", ta, env)
                if code:
                    return code
                native = _script_command(python, ta, fm / "run_native.py", "--ticker", ticker,
                                         "--date", day, "--analysts", "market,sentiment,news,fundamentals",
                                         "--portfolio", str(book_path), "--save", "--no-show")
                code, _ = _run(native, cwd=ta, env=env, label=f"native:{ticker}")
                if code:
                    native_failed.append(ticker)

            if native_failed:
                # A portfolio review must not present itself as complete when
                # one of its explicitly selected ticker analyses failed.
                print("Native analyses failed; stopping before fund manager: "
                      + ", ".join(native_failed), flush=True)
                return 1

        if args.anl_only:
            print("ANL_ONLY_COMPLETE=" + ",".join(args.tickers), flush=True)
            return 0

        fm_args = _script_command(python, ta, fm / "fund_manager.py", "--date", day,
                                  "--book", str(book_path), "--targets", str(root / "targets.json"),
                                  "--watchlist", str(watch_path), "--reports-dir", str(root / "logs" / "reports"),
                                  "--out-dir", str(root / "fund_manager"))
        if args.since:
            fm_args.extend(["--since", args.since])
        if args.include_risk:
            fm_args.append("--include-risk")
        if args.no_macro:
            fm_args.append("--no-macro")
        if args.no_watchlist:
            fm_args.append("--no-watchlist")
        if args.no_llm:
            # This guarantees no model calls in the full pipeline, including native stages.
            fm_args.append("--no-llm")
        else:
            code = _budget(python, addons, root, budget_day, "fund_manager", ta, env)
            if code:
                return code
        code, _ = _run(fm_args, cwd=ta, env=env, label="fund_manager")
        return 1 if native_failed and code == 0 else code


def main(argv: list[str] | None = None) -> int:
    code = 1
    error = None
    try:
        code = _main(argv)
    except Exception as exc:
        error = str(exc)
        traceback.print_exc()
        code = 1
    finally:
        status = "succeeded" if code == 0 else ("skipped" if code == 75 else "failed")
        updates = {"exit_code": code, "finished_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()}
        if error:
            updates["error"] = error
        _set_run_state(status, **updates)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
