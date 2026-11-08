"""Run one TradingAgents Python entry point with its local runtime environment."""
from __future__ import annotations

import runpy
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) < 3:
        raise SystemExit("usage: exec_ta.py TRADINGAGENTS_ROOT SCRIPT [ARGS...]")
    root = Path(sys.argv[1]).resolve()
    script = Path(sys.argv[2]).resolve()
    if not script.is_relative_to(root):
        raise SystemExit("TradingAgents script must be inside TRADINGAGENTS_ROOT")
    try:
        from dotenv import load_dotenv
    except ImportError as exc:
        raise SystemExit("python-dotenv is required by the TradingAgents environment") from exc
    load_dotenv(root / ".env", override=False)
    load_dotenv(root / ".env.enterprise", override=False)
    sys.path.insert(0, str(root))
    sys.argv = [str(script), *sys.argv[3:]]
    runpy.run_path(str(script), run_name="__main__")


if __name__ == "__main__":
    main()
