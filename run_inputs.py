"""Fingerprints for portfolio inputs that a confirmed run will consume."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping


def fingerprint(data_root: Path, ta_root: Path, config_paths: Mapping[str, Path]) -> dict:
    """Return stable content hashes for shared portfolio and model inputs.

    Only digests leave the process; input contents and credentials are never
    copied into run metadata. Missing files have an explicit stable marker.
    """
    paths = {
        "book": data_root / "my_book.json",
        "watchlist": data_root / "watchlist.json",
        "targets": data_root / "targets.json",
        "themes": ta_root / "addons" / "fund_manager" / "themes.json",
        **config_paths,
    }
    files = {}
    for name, path in sorted(paths.items()):
        try:
            files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        except FileNotFoundError:
            files[name] = None
    encoded = json.dumps(files, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return {"files": files, "sha256": hashlib.sha256(encoded).hexdigest()}
