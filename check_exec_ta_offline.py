"""Isolated regression tests for the TradingAgents script execution bridge."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REAL_TA_ADDONS = ROOT.parent / "TradingAgents" / "addons"


def _run(command: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, env=env, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="argus_exec_ta_check_") as folder:
        temp = Path(folder)
        ta = temp / "fake-ta"
        script_dir = ta / "addons" / "fund_manager"
        script_dir.mkdir(parents=True)
        root_package = ta / "tradingagents"
        root_package.mkdir()
        (root_package / "__init__.py").write_text("VALUE = 'from-ta-root'\n", encoding="utf-8")

        # This is the real sibling module which failed to import in production.
        trade_validation = REAL_TA_ADDONS / "fund_manager" / "trade_validation.py"
        (script_dir / "trade_validation.py").write_text(
            trade_validation.read_text(encoding="utf-8"), encoding="utf-8")

        # A local dotenv shim keeps this fixture independent of installed
        # packages while exercising both files and override=False semantics.
        (ta / "dotenv.py").write_text(
            "import os\n"
            "from pathlib import Path\n"
            "def load_dotenv(path, override=False):\n"
            "    for line in Path(path).read_text(encoding='utf-8').splitlines():\n"
            "        if not line.strip() or line.strip().startswith('#') or '=' not in line:\n"
            "            continue\n"
            "        key, value = line.split('=', 1)\n"
            "        if override or key not in os.environ:\n"
            "            os.environ[key] = value\n",
            encoding="utf-8")
        (ta / ".env").write_text("EXEC_TA_FROM_FILE=primary\nEXEC_TA_INHERITED=from-dotenv\n", encoding="utf-8")
        (ta / ".env.enterprise").write_text("EXEC_TA_FROM_FILE=enterprise\n", encoding="utf-8")

        script = script_dir / "fund_manager.py"
        result_path = temp / "bridge-result.json"
        script.write_text(
            "import json, os, pathlib, sys\n"
            "import tradingagents\n"
            "from trade_validation import parse_trade_policy\n"
            "result = {\n"
            "  'argv': sys.argv,\n"
            "  'script_dir_first': pathlib.Path(sys.path[0]).resolve() == pathlib.Path(__file__).parent.resolve(),\n"
            "  'ta_root_import': tradingagents.VALUE,\n"
            "  'trade_validation_file': pathlib.Path(__import__('trade_validation').__file__).resolve().as_posix(),\n"
            "  'policy': parse_trade_policy({}),\n"
            "  'inherited': os.environ.get('EXEC_TA_INHERITED'),\n"
            "  'from_file': os.environ.get('EXEC_TA_FROM_FILE'),\n"
            "}\n"
            "pathlib.Path(sys.argv[sys.argv.index('--result') + 1]).write_text(json.dumps(result), encoding='utf-8')\n",
            encoding="utf-8")

        args = ["--mode", "fixture", "two words", "--result", str(result_path)]
        clean_env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
        env = {**clean_env, "PYTHONPATH": str(ta), "EXEC_TA_INHERITED": "parent-value"}

        # Reproduce the old bridge behavior. run_path alone does not make the
        # script's containing directory importable, so the sibling import fails.
        pre_fix = _run([
            sys.executable, "-c",
            "import runpy,sys; sys.argv=sys.argv[1:]; runpy.run_path(sys.argv[0], run_name='__main__')",
            str(script), *args,
        ], cwd=ta, env=env)
        assert pre_fix.returncode != 0 and "No module named 'trade_validation'" in pre_fix.stdout, pre_fix.stdout
        assert not result_path.exists(), "the failing pre-fix invocation unexpectedly ran the entry point"

        bridged = _run([sys.executable, str(ROOT / "exec_ta.py"), str(ta), str(script), *args], cwd=ta, env=env)
        assert bridged.returncode == 0, bridged.stdout
        result = json.loads(result_path.read_text(encoding="utf-8"))
        assert result["argv"] == [str(script), *args], result["argv"]
        assert result["script_dir_first"] is True, result
        assert result["ta_root_import"] == "from-ta-root", result
        assert Path(result["trade_validation_file"]).resolve() == (script_dir / "trade_validation.py").resolve(), result
        assert result["policy"] == {
            "fee_per_order_usd": 3.0,
            "min_buy_notional_usd": 1000.0,
            "min_residual_notional_usd": 1000.0,
        }, result
        assert result["inherited"] == "parent-value", result
        assert result["from_file"] == "primary", result

        marker = temp / "outside-script-ran.txt"
        outside = temp / "outside.py"
        outside.write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('bad')\n", encoding="utf-8")
        rejected = _run([sys.executable, str(ROOT / "exec_ta.py"), str(ta), str(outside)], cwd=ta, env=env)
        assert rejected.returncode != 0 and "must be inside TRADINGAGENTS_ROOT" in rejected.stdout, rejected.stdout
        assert not marker.exists(), "outside-root script executed despite the path guard"

    print("argus exec_ta offline check: ok (sibling imports, TA root imports, argv, dotenv precedence, root guard)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
