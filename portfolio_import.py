"""Shared preview and guarded account-scoped portfolio import operations."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class PortfolioImportError(ValueError):
    pass


def account_identity(broker: str, broker_account_id: str) -> str:
    """Create a stable opaque id without exposing broker identifiers."""
    key = f"{broker.strip().lower()}:{str(broker_account_id).strip()}".encode()
    return f"{broker.strip().lower()}_{hashlib.sha256(key).hexdigest()[:24]}"


def book_version(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return "missing"


def load_book(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PortfolioImportError("Existing portfolio book is unreadable") from exc
    if not isinstance(value, dict):
        raise PortfolioImportError("Existing portfolio book is not an object")
    return value


def account_snapshot(*, broker: str, broker_account_id: str, label: str,
                     currency: str, cash: float | None, available_cash: float | None,
                     positions: list[dict[str, Any]], fetched_at: str,
                     scope: str = "US_STOCKS") -> dict[str, Any]:
    return {
        "account_id": account_identity(broker, broker_account_id),
        "broker": broker.strip().lower(), "label": label,
        "scope": scope, "currency": currency.strip().upper(),
        "cash": cash, "available_cash": available_cash,
        "fetched_at": fetched_at, "positions": positions,
    }


def apply_account(path: Path, account: dict[str, Any], expected_version: str,
                  *, replace_legacy: bool = False) -> Path | None:
    """Version-check, back up, normalize and atomically replace one account."""
    if book_version(path) != expected_version:
        raise PortfolioImportError("Portfolio changed after preview; fetch a fresh snapshot")
    old = load_book(path)
    if expected_version == "missing" and path.exists():
        raise PortfolioImportError("Portfolio was created after preview; fetch a fresh snapshot")
    if expected_version == "missing":
        old = {"schema_version": 2, "accounts": []}
    try:
        from portfolio_book import normalize_book, replace_account
        updated = replace_account(old, account, replace_legacy=replace_legacy)
        updated = normalize_book(updated)
    except (ImportError, ValueError) as exc:
        raise PortfolioImportError(str(exc)) from exc
    backup = None
    if path.exists():
        backup = path.with_name(f"{path.name}.bak_{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}")
        shutil.copy2(path, backup)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(updated, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if book_version(path) != expected_version:
            raise PortfolioImportError("Portfolio changed while import was being applied")
        os.replace(temporary, path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise
    return backup
