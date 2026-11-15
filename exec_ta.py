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
    # Match ``python /path/to/script.py``: imports beside the entry point take
    # precedence, while the TradingAgents root remains available for packages.
    import_paths = list(dict.fromkeys((str(script.parent), str(root))))
    sys.path[:] = import_paths + [entry for entry in sys.path if entry not in import_paths]
    sys.argv = [str(script), *sys.argv[3:]]
    runpy.run_path(str(script), run_name="__main__")


if __name__ == "__main__":
    main()
