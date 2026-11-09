"""
Argus — local dashboard for TradingAgents.
Reads TradingAgents data; never modifies TradingAgents source.
Binds to 127.0.0.1 only. Never exposes .env values.
"""
from __future__ import annotations

import json
import math
import hashlib
import os
import re
import sys
import secrets
import subprocess
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

if os.name == "nt":
    import msvcrt
else:
    import fcntl

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
DEFAULT_TA = Path(r"D:\software development\trading\TradingAgents") if os.name == "nt" else ROOT.parent / "TradingAgents"
TA_ROOT = Path(os.environ.get("TRADINGAGENTS_ROOT", str(DEFAULT_TA))).resolve()
DATA = TA_ROOT / "data"
BOOK = DATA / "my_book.json"
TARGETS = DATA / "targets.json"
WATCHLIST = DATA / "watchlist.json"
THEMES = TA_ROOT / "addons" / "fund_manager" / "themes.json"
ADDONS = TA_ROOT / "addons"
if str(ADDONS) not in sys.path:
    sys.path.insert(0, str(ADDONS))
import agent_config  # noqa: E402
from run_inputs import fingerprint as _fingerprint_run_inputs  # noqa: E402
SUBTHEME_ORDER = (
    "ai_energy",
    "ai_memory_storage",
    "ai_compute_semis",
    "ai_network_fibre",
    "ai_cloud_software",
    "physical_ai",
)
REPORTS_DIR = DATA / "logs" / "reports"
FUND_DIR = DATA / "fund_manager"
RUNNER = ROOT / "run_analysis.py"
RUNS_DIR = Path(os.environ.get("DASHBOARD_RUNS_DIR", str(ROOT / "runs"))).resolve()
RUNS_DIR.mkdir(parents=True, exist_ok=True)

RATING_RE = re.compile(r"(?im)^-\s*Rating:\s*(.+?)\s*$")
REPORT_DIR_RE = re.compile(r"^(.+)_(\d{8})_(\d{6})$")

app = FastAPI(title="Argus", docs_url=None, redoc_url=None)

DEFAULT_MAX_CANDIDATES = 100
DEFAULT_MAX_STOCKS_PER_SECTOR = 10


@app.on_event("startup")
def recover_watchlist_transaction_on_startup():
    if _watchlist_txn_path().is_file():
        with _data_write_lock():
            _recover_watchlist_transaction()

# Per-process confirm token. The page reads it from GET /api/session (same origin only)
# and must send it back as X-Argus-Confirm on POST /api/runs. A foreign page cannot
# read it, and the host check below rejects a DNS-rebinding Host.
CONFIRM_TOKEN = secrets.token_urlsafe(32)
_ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1"}
_BIND_HOST = os.environ.get("ARGUS_HOST", "127.0.0.1").strip()
if _BIND_HOST in ("0.0.0.0", "::", ""):
    raise RuntimeError("ARGUS_HOST must be a specific interface address; wildcard binding is disabled")
_ALLOWED_HOSTS.add(_BIND_HOST.lower())


class _LocalHostMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        host = (request.headers.get("host") or "").strip().lower()
        if host.startswith("["):
            name = host.split("]")[0].strip("[]")
        else:
            name = host.split(":")[0]
        if name not in _ALLOWED_HOSTS:
            return JSONResponse({"detail": "Host not allowed"}, status_code=400)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            if origin:
                expected = f"{request.url.scheme}://{host}"
                if origin.rstrip("/").lower() != expected.lower():
                    return JSONResponse({"detail": "Origin not allowed"}, status_code=403)
        return await call_next(request)


app.add_middleware(_LocalHostMiddleware)


def _require_confirm_token(request: Request) -> None:
    got = request.headers.get("x-argus-confirm") or ""
    if len(got) != len(CONFIRM_TOKEN) or not secrets.compare_digest(got, CONFIRM_TOKEN):
        raise HTTPException(401, "This action requires the X-Argus-Confirm token from GET /api/session")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> Any:
    if not path.exists():
        raise HTTPException(404, f"Not found: {path.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def _write_watchlist_items(items: list[dict]) -> None:
    """Replace rows while retaining an existing JSON wrapper and its metadata."""
    payload: Any = items
    if WATCHLIST.is_file():
        raw = _read_json(WATCHLIST)
        if isinstance(raw, dict):
            key = next((name for name in ("items", "candidates", "watchlist", "tickers")
                        if isinstance(raw.get(name), list)), "items")
            payload = {**raw, key: items}
    _write_json(WATCHLIST, payload)


def _watchlist_txn_path() -> Path:
    return DATA / ".watchlist_transaction.json"


def _recover_watchlist_transaction() -> None:
    """Finish a prepared watchlist replacement and its event group after a crash."""
    journal = _watchlist_txn_path()
    if not journal.is_file():
        return
    state = _read_json(journal)
    current = _saved_watchlist_items()
    encode = lambda rows: json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    current_state = encode(current)
    before_state = encode(state["before"])
    after_state = encode(state["after"])
    if current_state not in {before_state, after_state}:
        raise HTTPException(409, "A pending watchlist transaction conflicts with the saved list; resolve it before making changes")
    if current_state == before_state:
        _write_watchlist_items(state["after"])
    import watchlist_log
    events = watchlist_log.read_events(DATA)
    present = {(row.get("transaction_id"), row.get("transaction_index")) for row in events}
    for index, event in enumerate(state.get("events") or []):
        key = (state["transaction_id"], index)
        if key in present:
            continue
        watchlist_log.append_event(DATA, {**event, "transaction_id": key[0], "transaction_index": index})
    journal.unlink(missing_ok=True)


def _commit_watchlist_transaction(before: list[dict], after: list[dict], events: list[dict], transaction_id: str) -> None:
    _write_json(_watchlist_txn_path(), {"transaction_id": transaction_id, "before": before,
                                       "after": after, "events": events})
    _recover_watchlist_transaction()


@contextmanager
def _data_write_lock():
    """Coordinate short portfolio-data writes with the long-running analysis runner."""
    path = DATA / ".argus-run.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as lock:
        if os.name == "nt":
            lock.seek(0)
            if lock.read(1) == b"":
                lock.write(b"0")
                lock.flush()
            lock.seek(0)
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise HTTPException(409, "An analysis is running; try again after it finishes") from exc
        else:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise HTTPException(409, "An analysis is running; try again after it finishes") from exc
        try:
            _recover_watchlist_transaction()
            yield
        finally:
            if os.name == "nt":
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _safe_ticker(t: str) -> str:
    t = (t or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9.\-]{1,12}", t):
        raise HTTPException(400, f"Invalid ticker: {t!r}")
    return t


def _first_file(folder: Path, names: list[str]) -> Optional[Path]:
    for name in names:
        p = folder / name
        if p.is_file():
            return p
    return None


def _newest_file(folder: Path, names: list[str]) -> Optional[Path]:
    existing = [folder / name for name in names if (folder / name).is_file()]
    if not existing:
        return None
    return max(existing, key=lambda p: p.stat().st_mtime)


def _fm_runs() -> list[dict]:
    """Legacy date folders and timestamped date/HHMMSS_id folders, newest file first."""
    if not FUND_DIR.exists():
        return []
    found = []
    for date_dir in FUND_DIR.iterdir():
        if not date_dir.is_dir() or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_dir.name):
            continue
        folders = [date_dir]
        for child in date_dir.iterdir():
            if child.is_dir() and re.fullmatch(r"\d{6}_[A-Za-z0-9]+", child.name):
                folders.append(child)
        for folder in folders:
            report = _first_file(folder, ["portfolio_report.json", "portfolio_snapshot.json"])
            md = _first_file(folder, ["portfolio_report.md", "portfolio_snapshot.md"])
            stats = _newest_file(folder, ["portfolio_stats.json", "snapshot_portfolio_stats.json"])
            mtimes = [p.stat().st_mtime for p in (report, md, stats) if p is not None]
            if not mtimes:
                continue
            rel = str(folder.relative_to(FUND_DIR)).replace("\\", "/")
            found.append({
                "rel": rel,
                "date": date_dir.name,
                "folder": folder,
                "report_json": report,
                "markdown_path": md,
                "stats_path": stats,
                "mtime": max(mtimes),
                "kind": "report" if report is not None and report.name == "portfolio_report.json" else "snapshot",
            })
    found.sort(key=lambda r: r["mtime"], reverse=True)
    return found


def _load_run_view(run: dict) -> dict:
    out: dict[str, Any] = {"date": run["date"], "path": run["rel"], "kind": run["kind"]}
    if run["report_json"] is not None:
        try:
            out["json"] = _read_json(run["report_json"])
        except Exception:
            out["json"] = None
    if run["markdown_path"] is not None:
        out["markdown"] = run["markdown_path"].read_text(encoding="utf-8", errors="replace")
    return out


def _decision_bundle(js: Optional[dict]) -> dict:
    """The add-on writes final/draft and final_check, not a decision key."""
    js = js or {}
    decision = js.get("final") or js.get("draft") or js.get("decision")
    check = None
    if js.get("final") is not None:
        check = js.get("final_check") or {}
    elif js.get("draft") is not None:
        check = js.get("draft_check") or {}
    else:
        check = js.get("final_check") or js.get("draft_check") or {}
    trades = (check or {}).get("trades") or (decision or {}).get("trades") or []
    return {
        "decision": decision,
        "trades": trades,
        "warnings": (check or {}).get("warnings") or [],
        "cash_decision": (decision or {}).get("cash_decision") if isinstance(decision, dict) else None,
        "ending_cash": (check or {}).get("ending_cash"),
        "ending_cash_pct": (check or {}).get("ending_cash_pct"),
        "post_trade_risk": (check or {}).get("post_trade_risk"),
    }


def _latest_stats() -> Optional[dict]:
    for run in _fm_runs():
        if run["stats_path"] is None:
            continue
        try:
            return {"date": run["date"], "path": str(run["stats_path"]), "run": run["rel"], **_read_json(run["stats_path"])}
        except Exception:
            continue
    return None


def _latest_fund_report() -> Optional[dict]:
    runs = _fm_runs()
    chosen = next((r for r in runs if r["kind"] == "report"), None)
    if chosen is None and runs:
        chosen = runs[0]
    return _load_run_view(chosen) if chosen else None


def _script_flags() -> dict[str, bool]:
    """Capabilities of the Argus-owned native runner."""
    flags = {
        "RunAgents": True,
        "NoLLM": True,
        "AnalysisDate": True,
        "Tickers": True,
        "IncludeRisk": True,
        "NoMacro": True,
        "Since": True,
        "IncludeWatchlist": False,
        "Analysts": True,
        "Model": True,
        "ReasoningEffort": True,
    }
    flags["IncludeWatchlist"] = RUNNER.exists()
    return flags


def _parse_report_meta(dirname: str, report_path: Path) -> dict:
    m = REPORT_DIR_RE.match(dirname)
    ticker, ymd, hms = (m.group(1), m.group(2), m.group(3)) if m else (dirname, "", "")
    rating = None
    analysis_date = None
    generated = None
    try:
        head = report_path.read_text(encoding="utf-8", errors="replace")[:4000]
        rm = RATING_RE.search(head)
        if rm:
            rating = rm.group(1).strip()
        ad = re.search(r"(?im)^-\s*Analysis date:\s*(.+?)\s*$", head)
        if ad:
            analysis_date = ad.group(1).strip()
        gd = re.search(r"(?im)^-\s*Generated:\s*(.+?)\s*$", head)
        if gd:
            generated = gd.group(1).strip()
    except Exception:
        pass
    stamp = f"{ymd}_{hms}" if ymd else ""
    return {
        "id": dirname,
        "ticker": ticker,
        "stamp": stamp,
        "ymd": ymd,
        "hms": hms,
        "rating": rating,
        "analysis_date": analysis_date,
        "generated": generated,
        "path": str(report_path),
        "mtime": report_path.stat().st_mtime if report_path.exists() else None,
    }


def _list_reports() -> list[dict]:
    if not REPORTS_DIR.exists():
        return []
    items = []
    for d in REPORTS_DIR.iterdir():
        if not d.is_dir():
            continue
        md = d / "complete_report.md"
        if not md.exists():
            continue
        items.append(_parse_report_meta(d.name, md))
    items.sort(key=lambda x: (x.get("ymd") or "", x.get("hms") or ""), reverse=True)
    return items


def _run_meta_path(run_id: str) -> Path:
    return RUNS_DIR / run_id / "meta.json"


def _run_log_path(run_id: str) -> Path:
    return RUNS_DIR / run_id / "output.log"


def _load_run(run_id: str) -> dict:
    p = _run_meta_path(run_id)
    if not p.exists():
        raise HTTPException(404, f"Run not found: {run_id}")
    return _reconcile_run(json.loads(p.read_text(encoding="utf-8")))


def _save_run(meta: dict) -> None:
    rid = meta["id"]
    d = RUNS_DIR / rid
    d.mkdir(parents=True, exist_ok=True)
    target = _run_meta_path(rid)
    tmp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        tmp.replace(target)
    finally:
        tmp.unlink(missing_ok=True)


def _list_runs() -> list[dict]:
    if not RUNS_DIR.exists():
        return []
    out = []
    for d in RUNS_DIR.iterdir():
        if not d.is_dir():
            continue
        mp = d / "meta.json"
        if mp.exists():
            try:
                out.append(_reconcile_run(json.loads(mp.read_text(encoding="utf-8"))))
            except Exception:
                continue
    out.sort(key=lambda x: x.get("started_at") or "", reverse=True)
    return out


def _reconcile_run(meta: dict) -> dict:
    """After a web restart, retain a live child and mark an exited child interrupted."""
    if meta.get("status") != "running":
        return meta
    result_path = RUNS_DIR / str(meta["id"]) / "result.json"
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        result = None
    if isinstance(result, dict) and result.get("status") in ("succeeded", "failed", "skipped"):
        meta.update(result)
        meta.setdefault("finished_at", datetime.now(timezone.utc).isoformat())
        _save_run(meta)
        return meta
    if not meta.get("pid"):
        return meta
    pid = int(meta["pid"])
    try:
        os.kill(pid, 0)
    except OSError:
        alive = False
    else:
        alive = True
        if sys.platform.startswith("linux"):
            try:
                cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ")
                alive = str(RUNNER).encode() in cmdline
            except OSError:
                alive = False
    if not alive:
        meta["status"] = "interrupted"
        meta["finished_at"] = datetime.now(timezone.utc).isoformat()
        meta["error"] = "Analysis process exited before completion was recorded; inspect its log before retrying."
        _save_run(meta)
    return meta


# ---------------------------------------------------------------------------
# API models
# ---------------------------------------------------------------------------

class WatchlistItem(BaseModel):
    ticker: str
    sector: str = "Other"
    type: str = "stock"


class WatchlistAdd(BaseModel):
    ticker: str
    sector: str = "Other"
    type: str = Field(default="stock", pattern="^(stock|etf)$")
    sub_theme: str = ""


class ScoutRequest(BaseModel):
    mode: str = "screen"  # screen | weekly
    include_llm: bool = False
    confirm: bool = False
    sectors: list[str] = Field(default_factory=list)
    single_call: bool = False
    manifest_sha256: str = ""


class WatchlistProposalApply(BaseModel):
    date: str
    base_watchlist_version: str
    proposal_sha256: str
    add: list[str] = Field(default_factory=list)
    drop: list[str] = Field(default_factory=list)
    confirm: bool = False


class AgentSeatIn(BaseModel):
    model: str
    effort: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    system: str = ""


class AgentConfigIn(BaseModel):
    seats: dict[str, AgentSeatIn]
    unlock: list[str] = Field(default_factory=list)


class DashboardSettingsIn(BaseModel):
    weekly_budget_enabled: bool = False
    weekly_budget_usd: float = Field(ge=0, le=1_000_000)
    max_adds_per_week: int | None = Field(default=None, ge=1, le=10_000)
    max_drops_per_week: int | None = Field(default=None, ge=1, le=10_000)
    max_candidates: int | None = Field(default=None, ge=1, le=10_000)
    max_stocks_per_sector: int | None = Field(default=None, ge=1, le=1000)


class RunRequest(BaseModel):
    run_agents: bool = False
    analysis_only: bool = False
    no_llm: bool = False
    include_risk: bool = False
    no_macro: bool = False
    include_watchlist: bool = False
    analysis_date: str = ""
    since: str = ""
    tickers: list[str] = Field(default_factory=list)
    manifest_sha256: str = ""
    confirm: bool = False


class TigerPreviewRequest(BaseModel):
    account_key: str


class TigerApplyRequest(BaseModel):
    preview_id: str
    confirm: bool = False
    confirm_empty: bool = False
    confirm_stock_only: bool = False


_TIGER_ACCOUNTS: dict[str, dict[str, str]] = {}
_TIGER_ACCOUNTS_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Routes — meta / health
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {
        "ok": True,
        "app": "Argus",
        "tradingagents_root": str(TA_ROOT),
        "data_ok": BOOK.exists(),
        "script_ok": RUNNER.exists(),
        "flags": _script_flags(),
    }


@app.get("/api/config")
def config():
    return {
        "app": "Argus",
        "tradingagents_root": str(TA_ROOT),
        "flags": _script_flags(),
        "minutes_per_ticker": 3,
        "fund_manager_calls": 5,
        "models_note": "Fund manager and aggressive: openai/gpt-6.1-sol. Conservative: anthropic/claude-opus-5.5. Neutral: openai/gpt-6-luna.",
    }


@app.get("/api/session")
def session():
    return {"token": CONFIRM_TOKEN, "header": "X-Argus-Confirm"}


def _dashboard_settings(targets: dict | None = None) -> dict:
    if targets is None:
        targets = _read_json(TARGETS) if TARGETS.is_file() else {}
    raw_watch = targets.get("watchlist_curator") or {}
    raw_budget = targets.get("budget") or {}
    import cost_ledger
    budget = cost_ledger.budget_policy(targets)
    return {
        "weekly_budget_enabled": budget["enabled"],
        "weekly_budget_usd": budget["weekly_usd"],
        "max_adds_per_week": None,
        "max_drops_per_week": None,
        "cooldown_days": 14,
        "max_candidates": raw_watch.get("max_candidates", DEFAULT_MAX_CANDIDATES),
        "max_stocks_per_sector": raw_watch.get("max_stocks_per_sector", DEFAULT_MAX_STOCKS_PER_SECTOR),
        "supported_sectors": [{"ticker": ticker, "name": name}
                               for ticker, name in SCOUT_SECTOR_LABELS.items()],
    }


@app.get("/api/settings")
def settings_view():
    return _dashboard_settings()


@app.put("/api/settings")
def settings_save(body: DashboardSettingsIn, request: Request):
    _require_confirm_token(request)
    with _data_write_lock():
        current = _read_json(TARGETS) if TARGETS.is_file() else {}
        if not isinstance(current, dict):
            raise HTTPException(400, "Targets policy must be a JSON object")
        budget = dict(current.get("budget") or {})
        curator = dict(current.get("watchlist_curator") or {})
        budget.update({"enabled": body.weekly_budget_enabled,
                       "weekly_usd": body.weekly_budget_usd})
        curator.update({
            "max_adds_per_week": body.max_adds_per_week,
            "max_drops_per_week": body.max_drops_per_week,
            "max_candidates": body.max_candidates,
            "max_stocks_per_sector": body.max_stocks_per_sector,
        })
        updated = {**current, "budget": budget,
                   "weekly_budget_usd": body.weekly_budget_usd,
                   "watchlist_curator": curator}
        _write_json(TARGETS, updated)
        return _dashboard_settings(updated)


@app.get("/api/agents")
def agents_view():
    try:
        return agent_config.public_payload()
    except agent_config.AgentConfigError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.put("/api/agents")
def agents_save(body: AgentConfigIn, request: Request):
    """Persist seat overrides. Requires the same confirm token as a run. No model call."""
    _require_confirm_token(request)
    payload = {"unlock": body.unlock, "seats": {k: v.model_dump() for k, v in body.seats.items()}}
    try:
        with _data_write_lock():
            return agent_config.validate_and_save(payload)
    except agent_config.AgentConfigError as exc:
        raise HTTPException(400, str(exc)) from exc


def _theme_file() -> dict:
    if not THEMES.exists():
        return {}
    data = _read_json(THEMES)
    return data if isinstance(data, dict) else {}


def _subtheme_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for name, members in (_theme_file().get("subthemes") or {}).items():
        for ticker in members or []:
            index[str(ticker).upper()] = str(name)
    return index


def _subtheme_labels() -> dict[str, str]:
    labels = {
        "ai_energy": "AI energy",
        "ai_memory_storage": "AI memory & storage",
        "ai_compute_semis": "AI compute & semis",
        "ai_network_fibre": "AI network & fibre",
        "ai_cloud_software": "AI cloud & software",
        "physical_ai": "Physical AI",
    }
    labels.update(_theme_file().get("subtheme_labels") or {})
    return labels


def _subtheme_table(rows: list[dict], weight_key: str = "weight_pct") -> list[dict]:
    """Direct exposure for holdings, or a name list for the watchlist."""
    labels = _subtheme_labels()
    index = _subtheme_index()
    defined = list((_theme_file().get("subthemes") or {}).keys()) or list(SUBTHEME_ORDER)
    buckets = {
        name: {"id": name, "label": labels.get(name, name), "weight_pct": 0.0,
               "market_value": 0.0, "count": 0, "tickers": []}
        for name in defined
    }
    for row in rows:
        ticker = str(row.get("ticker") or "").upper()
        name = row.get("sub_theme") or index.get(ticker)
        if not name:
            continue
        bucket = buckets.setdefault(name, {
            "id": name, "label": labels.get(name, name), "weight_pct": 0.0,
            "market_value": 0.0, "count": 0, "tickers": []})
        weight = row.get(weight_key)
        value = row.get("market_value")
        if isinstance(weight, (int, float)):
            bucket["weight_pct"] += float(weight)
        if isinstance(value, (int, float)):
            bucket["market_value"] += float(value)
        bucket["count"] += 1
        bucket["tickers"].append({
            "ticker": ticker,
            "weight_pct": round(float(weight), 1) if isinstance(weight, (int, float)) else None,
        })
    order = defined + [name for name in buckets if name not in defined]
    out = []
    for name in order:
        bucket = buckets[name]
        bucket["weight_pct"] = round(bucket["weight_pct"], 1)
        bucket["market_value"] = round(bucket["market_value"], 2)
        out.append(bucket)
    return out


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------

# Same set as fund_manager.KNOWN_ETFS. Any quote type "etf" also counts.
_ETF_TICKERS = {
    "SPY", "QQQ", "SMH", "IWM", "XLE", "XLF", "GLD", "XLV", "XLP", "XLU", "TLT", "DRAM", "DISK",
}
_CORE_ETF_WARN_PCT = 30.0
_CORE_ETF_BREACH_PCT = 32.0


def _instrument_type(ticker: str, info: dict | None) -> str:
    """Describe what an instrument is, independently of its portfolio role."""
    kind = str((info or {}).get("type") or "").strip().upper()
    if kind == "ETN":
        return "ETN"
    if kind == "ETF" or str(ticker or "").strip().upper() in _ETF_TICKERS:
        return "ETF"
    if kind in {"EQUITY", "STOCK"} or str(ticker or "").strip().upper() == "BRK-B":
        return "Stock"
    return f"Unknown ({kind})" if kind else "Unknown"


def _approved_target_weights(targets: dict) -> dict:
    raw = targets.get("approved_targets_pct") if isinstance(targets, dict) else None
    if not isinstance(raw, dict):
        return {}
    return {str(ticker): value for ticker, value in raw.items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(float(value)) and 0 <= float(value) <= 100}


def _sleeve(ticker: str, info: dict | None) -> str:
    instrument = _instrument_type(ticker, info)
    if instrument == "ETF":
        return "core_etf"
    if instrument == "Stock":
        return "swing"
    return "unclassified"


@app.get("/api/portfolio")
def portfolio():
    # A missing book is a valid first-import state. Keep GET read-only; the
    # Tiger replacement path creates it only after preview and confirmation.
    book = _read_json(BOOK) if BOOK.exists() else {"cash": 0, "currency": "", "positions": []}
    targets = _read_json(TARGETS) if TARGETS.exists() else {}
    approved_targets = _approved_target_weights(targets)
    stats = _latest_stats()
    price_map: dict[str, dict] = {}
    if stats:
        for p in stats.get("positions") or []:
            price_map[p["ticker"]] = p

    rows = []
    invested_cost = 0.0
    invested_mv = 0.0
    for pos in book.get("positions") or []:
        t = pos["ticker"]
        qty = float(pos.get("quantity") or 0)
        avg = float(pos.get("average_price") or 0)
        cost = qty * avg
        invested_cost += cost
        st = price_map.get(t) or {}
        price = st.get("price")
        # Value is today's quantity times the latest stats price. The stored
        # market_value and weight belong to whatever quantity the book had then.
        if price is not None:
            mv = qty * float(price)
            invested_mv += mv
            pnl = mv - cost
            pnl_pct = ((float(price) / avg - 1) * 100) if avg else None
        else:
            mv = pnl = pnl_pct = None
        rows.append({
            "ticker": t,
            "quantity": qty,
            "average_price": avg,
            "cost_basis": cost,
            "price": price,
            "market_value": mv,
            "unrealized_pnl": pnl,
            "unrealized_pnl_pct": pnl_pct,
            "weight_pct": None,
            "sector": st.get("sector"),
            "name": st.get("name"),
            "target_pct": approved_targets.get(t),
            "sub_theme": _subtheme_index().get(str(t).upper()),
            "instrument_type": _instrument_type(t, st),
            "sleeve": _sleeve(t, st),
        })

    cash = float(book.get("cash") or 0)
    total_cost = invested_cost + cash
    priced = [r for r in rows if r["market_value"] is not None]
    total_mv = (invested_mv + cash) if priced else None
    cash_pct = (100.0 * cash / total_mv) if total_mv else None
    if total_mv:
        for r in rows:
            if r["market_value"] is not None:
                r["weight_pct"] = 100.0 * float(r["market_value"]) / total_mv
    weights_current = [
        {"ticker": r["ticker"], "weight_pct": r["weight_pct"], "target_pct": r["target_pct"]}
        for r in rows
    ]
    book_newer = False
    stats_path = stats.get("path") if stats else None
    if stats_path and BOOK.exists():
        try:
            book_newer = BOOK.stat().st_mtime > Path(stats_path).stat().st_mtime + 1
        except OSError:
            book_newer = False
    sleeves = {
        "core_etf": {"label": "Core ETF", "weight_pct": 0.0, "market_value": 0.0, "unrealized_pnl": 0.0},
        "swing": {"label": "Swing", "weight_pct": 0.0, "market_value": 0.0, "unrealized_pnl": 0.0},
        "unclassified": {"label": "Unclassified", "weight_pct": 0.0, "market_value": 0.0, "unrealized_pnl": 0.0},
    }
    if total_mv:
        for r in rows:
            bucket = sleeves[r.get("sleeve") or "unclassified"]
            bucket["market_value"] += r["market_value"] or 0
            bucket["unrealized_pnl"] += r["unrealized_pnl"] or 0
            bucket["weight_pct"] += r["weight_pct"] or 0
        sleeves["swing"]["market_value"] += cash
        sleeves["swing"]["weight_pct"] += cash_pct or 0
        for bucket in sleeves.values():
            bucket["weight_pct"] = round(bucket["weight_pct"], 1)
            bucket["market_value"] = round(bucket["market_value"], 2)
            bucket["unrealized_pnl"] = round(bucket["unrealized_pnl"], 2)
    unrealized = sum(r["unrealized_pnl"] or 0 for r in rows) if priced else None
    account_out = {
        "total_value": round(total_mv, 2) if total_mv is not None else None,
        "invested": round(invested_mv, 2) if priced else None,
        "cash": cash,
        "cash_pct": round(cash_pct, 1) if cash_pct is not None else None,
        "unrealized_pnl": round(unrealized, 2) if unrealized is not None else None,
    }

    return {
        "currency": book.get("currency", "USD"),
        "cash": cash,
        "cash_pct": round(cash_pct, 1) if cash_pct is not None else None,
        "cash_target_pct": approved_targets.get("cash"),
        "positions": rows,
        "weights": weights_current,
        "targets": approved_targets,
        "account": account_out,
        "total_cost": total_cost,
        "total_market_value": account_out["total_value"],
        "stats_date": stats.get("date") if stats else None,
        "stats_run": stats.get("run") if stats else None,
        "prices_as_of": (stats.get("as_of_prices") if stats else None),
        "book_newer_than_stats": book_newer,
        "ai_subthemes": _subtheme_table(rows),
        "ai_sleeve_cap_pct": float((targets.get("ai_sleeve") or {}).get("cap_pct") or 50),
        "sleeves": sleeves,
        "core_etf_warn_pct": _CORE_ETF_WARN_PCT,
        "core_etf_breach_pct": _CORE_ETF_BREACH_PCT,
    }


# ---------------------------------------------------------------------------
# Watchlist
# ---------------------------------------------------------------------------

def _saved_watchlist_items() -> list[dict]:
    if not WATCHLIST.exists():
        return []
    data = _read_json(WATCHLIST)
    items = next((data.get(key) for key in ("items", "candidates", "watchlist", "tickers")
                  if isinstance(data.get(key), list)), []) if isinstance(data, dict) else data
    cleaned = []
    for item in items:
        row = {"ticker": item} if isinstance(item, str) else item
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("ticker") or "").upper()
        if ticker:
            cleaned.append({**row, "ticker": ticker})
    return cleaned


def _canonical_watchlist(items: list[dict]) -> list[dict]:
    """Fields the scout reads, normalized exactly like its load_watchlist helper."""
    rows = []
    seen = set()
    for item in items:
        ticker = str(item.get("ticker") or "").strip().upper()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        row = {"ticker": ticker, "sector": item.get("sector"), "type": item.get("type") or "stock"}
        for key in ("theme", "sub_theme", "note"):
            if item.get(key):
                row[key] = item[key]
        rows.append(row)
    return rows


def _watchlist_version(items: list[dict]) -> str:
    payload = json.dumps(_canonical_watchlist(items), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


SCOUT_SECTOR_LABELS = {
    "XLK": "Information Technology",
    "XLY": "Consumer Cyclical",
    "XLV": "Healthcare",
    "XLP": "Consumer Defensive",
    "XLU": "Utilities",
    "XLE": "Energy",
    "XLF": "Financial Services",
    "SMH": "Semiconductors",
}
SCOUT_SECTOR_ALIASES = {
    "XLK": {"information technology", "technology"},
    "XLY": {"consumer cyclical", "consumer discretionary"},
    "XLV": {"healthcare", "health care"},
    "XLP": {"consumer defensive", "consumer staples"},
    "XLU": {"utilities", "utility"},
    "XLE": {"energy"},
    "XLF": {"financial services", "financials"},
    "SMH": {"semiconductors", "technology"},
}
MAX_SCOUT_SECTORS = len(SCOUT_SECTOR_LABELS)


def _watchlist_settings() -> dict:
    return _dashboard_settings()


def _validate_scout_sectors(sectors: list[str]) -> list[str]:
    selected = list(dict.fromkeys(str(s).strip().upper() for s in sectors if str(s).strip()))
    unknown = sorted(set(selected) - set(SCOUT_SECTOR_LABELS))
    if unknown:
        raise HTTPException(400, "Unknown discovery sector(s): " + ", ".join(unknown))
    if not selected:
        raise HTTPException(400, "Choose at least one discovery sector")
    if len(selected) > MAX_SCOUT_SECTORS:
        raise HTTPException(400, f"Choose at most {MAX_SCOUT_SECTORS} discovery sectors")
    return selected


def _sector_stock_tickers(sector: str) -> set[str]:
    """Unique confirmed stock instruments in a sector across holdings and candidates."""
    counts = {}
    for row in get_watchlist()["items"]:
        name = _canonical_sector_key(row.get("sector"))
        if name != _canonical_sector_key(sector):
            continue
        instrument = row.get("instrument_type")
        saved_type = str(row.get("type") or "").strip().lower()
        if instrument == "Stock" or (not instrument or instrument == "Unknown") and saved_type == "stock":
            counts.setdefault(name, set()).add(row["ticker"])
    return counts.get(_canonical_sector_key(sector), set())


def _held_tickers() -> set[str]:
    held = set()
    if BOOK.is_file():
        try:
            held = {str(p.get("ticker") or "").upper()
                    for p in (_read_json(BOOK).get("positions") or [])}
        except Exception:
            held = set()
    return held


def _candidate_count(items: list[dict] | None = None) -> int:
    rows = items if items is not None else _saved_watchlist_items()
    held = _held_tickers()
    return len({str(row.get("ticker") or "").upper() for row in rows
                if row.get("ticker") and str(row.get("ticker")).upper() not in held})


def _candidate_sector_tickers(sector: str, items: list[dict] | None = None) -> set[str]:
    """Saved non-held stock candidates in a sector, excluding automatic holdings."""
    rows = items if items is not None else _saved_watchlist_items()
    held = set()
    if BOOK.is_file():
        try:
            held = {str(p.get("ticker") or "").upper()
                    for p in (_read_json(BOOK).get("positions") or [])}
        except Exception:
            held = set()
    sector_key = _canonical_sector_key(sector)
    names = set()
    for row in rows:
        ticker = str(row.get("ticker") or "").upper()
        kind = str(row.get("type") or "stock").lower()
        if (ticker and ticker not in held and kind == "stock"
                and _canonical_sector_key(row.get("sector")) == sector_key):
            names.add(ticker)
    return names


def _validate_watchlist_add(row: dict, items: list[dict]) -> None:
    settings = _watchlist_settings()
    ticker = str(row.get("ticker") or "").upper()
    is_held = ticker in _held_tickers()
    existing = _candidate_sector_tickers(str(row.get("sector") or "Other"), items)
    if (not is_held and str(row.get("type") or "stock").lower() == "stock"
            and settings["max_stocks_per_sector"] is not None
            and ticker not in existing
            and len(existing) >= settings["max_stocks_per_sector"]):
        raise HTTPException(400, f"{row.get('sector') or 'Other'} already has {settings['max_stocks_per_sector']} active stock names")
    maximum = settings["max_candidates"]
    if (maximum is not None and ticker not in {str(item.get("ticker") or "").upper() for item in items}
            and not is_held and _candidate_count(items) >= maximum):
        raise HTTPException(400, f"Saved candidate limit ({maximum}) reached; existing names are kept. Raise the limit or remove a candidate first.")


def _canonical_sector_key(sector: Any) -> str:
    raw = str(sector or "").strip().casefold()
    for code, aliases in SCOUT_SECTOR_ALIASES.items():
        if raw == code.casefold() or raw in aliases:
            return SCOUT_SECTOR_LABELS[code].casefold()
    return raw


def _staged_tickers() -> set[str]:
    base = FUND_DIR
    reports = [path for path in base.glob("*/*/portfolio_report.json") if path.is_file()] if base.is_dir() else []
    if not reports:
        return set()
    try:
        data = _read_json(max(reports, key=lambda path: path.stat().st_mtime))
    except Exception:
        return set()
    staged = set()
    for key in ("final", "draft"):
        for trade in (data.get(key) or {}).get("trades") or []:
            try:
                has_shares = int(trade.get("shares") or 0) != 0
            except (TypeError, ValueError):
                has_shares = False
            if str(trade.get("order_type") or "").lower() == "staged" and has_shares:
                staged.add(str(trade.get("ticker") or "").upper())
    return staged


@app.get("/api/watchlist")
def get_watchlist():
    index = _subtheme_index()
    stats = _latest_stats() or {}
    market = {str(p.get("ticker") or "").upper(): p for p in stats.get("positions") or []}
    candidates = {}
    for item in _saved_watchlist_items():
        row = dict(item)
        ticker = str(row.get("ticker") or "").upper()
        if not ticker:
            continue
        row["ticker"] = ticker
        row["sub_theme"] = row.get("sub_theme") or index.get(ticker)
        row["origin"] = "candidate"
        row["origins"] = ["candidate"]
        row["held"] = False
        info = market.get(ticker)
        saved_type = str(row.get("type") or "").lower()
        live_type = _instrument_type(ticker, info) if info else "Unknown"
        row["instrument_type"] = live_type if live_type.startswith(("ETF", "Stock")) else (
            "ETF" if saved_type == "etf" else "Stock" if saved_type == "stock" else "Unknown")
        candidates[ticker] = row

    book = _read_json(BOOK) if BOOK.exists() else {"positions": []}
    held_rows = []
    for position in book.get("positions") or []:
        ticker = str(position.get("ticker") or "").upper()
        if not ticker:
            continue
        info = market.get(ticker) or {}
        row = dict(candidates.get(ticker) or {
            "ticker": ticker, "sector": info.get("sector"), "type": None,
            "sub_theme": index.get(ticker),
        })
        row.update({
            "held": True,
            "origin": "held and candidate" if ticker in candidates else "held",
            "origins": ["held", "candidate"] if ticker in candidates else ["held"],
            "instrument_type": (_instrument_type(ticker, info)
                                if _instrument_type(ticker, info).startswith(("ETF", "Stock"))
                                else row.get("instrument_type", "Unknown")),
            "sleeve": (_sleeve(ticker, info)
                       if _instrument_type(ticker, info).startswith(("ETF", "Stock")) else None),
        })
        held_rows.append(row)
    held_tickers = {row["ticker"] for row in held_rows}
    cleaned = held_rows + [row for ticker, row in candidates.items() if ticker not in held_tickers]
    return {"items": cleaned, "subthemes": _subtheme_table(cleaned)}


def _watch_log(action: str, ticker: str, row: dict, reason: str = "") -> None:
    import watchlist_log
    watchlist_log.append_event(DATA, {
        "as_of": datetime.now().strftime("%Y-%m-%d"),
        "action": action,
        "ticker": ticker,
        "reason": reason,
        "source": "argus",
        "row": row,
    })


@app.post("/api/watchlist")
def add_watchlist(item: WatchlistAdd, request: Request):
    _require_confirm_token(request)
    with _data_write_lock():
        ticker = _safe_ticker(item.ticker)
        current = _saved_watchlist_items()
        for it in current:
            if str(it.get("ticker", "")).upper() == ticker:
                raise HTTPException(409, f"{ticker} already on watchlist")
        entry = {"ticker": ticker, "sector": item.sector.strip() or "Other", "type": item.type}
        _validate_watchlist_add(entry, current)
        if item.sub_theme:
            if item.sub_theme not in _subtheme_labels() and item.sub_theme not in SUBTHEME_ORDER:
                raise HTTPException(400, f"Unknown sub_theme {item.sub_theme}")
            entry["sub_theme"] = item.sub_theme
        current.append(entry)
        _write_watchlist_items(current)
        _watch_log("add", ticker, entry, "added in Argus")
        return {"ok": True, "items": get_watchlist()["items"]}


@app.delete("/api/watchlist/{ticker}")
def remove_watchlist(ticker: str, request: Request):
    _require_confirm_token(request)
    with _data_write_lock():
        ticker = _safe_ticker(ticker)
        if not WATCHLIST.exists():
            raise HTTPException(404, "Watchlist empty")
        current = _saved_watchlist_items()
        removed = next((it for it in current if str(it.get("ticker", "")).upper() == ticker), None)
        new = [it for it in current if str(it.get("ticker", "")).upper() != ticker]
        if removed is None:
            raise HTTPException(404, f"{ticker} not on watchlist")
        _write_watchlist_items(new)
        _watch_log("drop", ticker, removed, "removed in Argus")
        return {"ok": True, "items": get_watchlist()["items"]}


@app.post("/api/watchlist/undo")
def undo_watchlist(request: Request):
    _require_confirm_token(request)
    with _data_write_lock():
        import watchlist_log
        events = watchlist_log.read_events(DATA)
        event = watchlist_log.last_undoable(events)
        if event is None:
            raise HTTPException(404, "Nothing to undo")
        current = _saved_watchlist_items()
        group = event.get("transaction_events") if isinstance(event.get("transaction_events"), list) else [event]
        updated = current
        for source_event in reversed(group):
            updated = watchlist_log.undo_items(updated, source_event)
        undo_events = []
        for source_event in group:
            undo_events.append({
                "as_of": datetime.now().strftime("%Y-%m-%d"),
                "action": "undo",
                "ticker": source_event.get("ticker"),
                "reason": f"undo {source_event.get('action')}",
                "source": "argus",
                "undo_of": source_event.get("id"),
                "row": source_event.get("row"),
            })
        undo_transaction_id = uuid.uuid4().hex
        _commit_watchlist_transaction(current, updated, undo_events, undo_transaction_id)
        undone = [row for row in watchlist_log.read_events(DATA)
                  if row.get("transaction_id") == undo_transaction_id]
        return {"ok": True, "undone": undone, "items": get_watchlist()["items"]}


@app.get("/api/spend")
def spend():
    import cost_ledger
    targets = _read_json(TARGETS) if TARGETS.exists() else {}
    return cost_ledger.weekly_spend(DATA, datetime.now().date(), targets)


@app.get("/api/tiger/accounts")
def tiger_accounts():
    """List authorized account aliases; never return account identifiers to the browser."""
    from tiger_import import TigerImportError, oauth_trade_client, read_accounts
    try:
        records = read_accounts(oauth_trade_client())
    except TigerImportError as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, "Tiger account lookup failed; check OAuth authorization and retry") from exc
    out = []
    aliases: dict[str, dict[str, str]] = {}
    for index, record in enumerate(records, 1):
        key = secrets.token_urlsafe(18)
        label = f"Account {index}"
        aliases[key] = {**record, "label": label}
        out.append({"account_key": key, "label": label,
                    "account_type": record["type"], "status": record["status"]})
    with _TIGER_ACCOUNTS_LOCK:
        _TIGER_ACCOUNTS.clear()
        _TIGER_ACCOUNTS.update(aliases)
    return {"accounts": out}


@app.post("/api/tiger/preview")
def tiger_preview(body: TigerPreviewRequest, request: Request):
    _require_confirm_token(request)
    from tiger_import import (TigerImportError, book_version, normalize_snapshot,
                              oauth_trade_client, read_snapshot)
    with _TIGER_ACCOUNTS_LOCK:
        account = _TIGER_ACCOUNTS.get(body.account_key)
    if account is None:
        raise HTTPException(400, "Refresh the Tiger account list and select an account")
    try:
        client = oauth_trade_client()
        snapshot = read_snapshot(client, account["id"], account["type"])
        normalized = normalize_snapshot(snapshot)
    except TigerImportError as exc:
        raise HTTPException(502, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, "Tiger positions or assets query failed; no portfolio changes were made") from exc
    preview_id = secrets.token_urlsafe(24)
    record = {
        "id": preview_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "book_version": book_version(BOOK),
        "snapshot": normalized,
    }
    preview_dir = RUNS_DIR / "tiger-previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    (preview_dir / f"{preview_id}.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return {"preview_id": preview_id, "created_at": record["created_at"],
            "account_key": body.account_key, "account_label": account["label"],
            "scope": normalized["scope"],
            "fetched_at": normalized["fetched_at"], "currency": normalized["currency"],
            "position_count": normalized["position_count"], "positions": normalized["book"]["positions"],
            "cash": normalized["book"]["cash"], "rejected": normalized["rejected"],
            "excluded": normalized["excluded"], "warnings": normalized["warnings"],
            "issues": normalized["issues"], "can_apply": normalized["can_apply"],
            "replaces_existing_positions": True,
            "empty_positions_require_confirmation": not normalized["book"]["positions"]}


@app.post("/api/tiger/apply")
def tiger_apply(body: TigerApplyRequest, request: Request):
    _require_confirm_token(request)
    if not body.confirm:
        raise HTTPException(400, "Set confirm=true after reviewing the replacement preview")
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,80}", body.preview_id):
        raise HTTPException(400, "Invalid preview id")
    from tiger_import import TigerImportError, apply_replacement
    preview_path = RUNS_DIR / "tiger-previews" / f"{body.preview_id}.json"
    if not preview_path.is_file():
        raise HTTPException(404, "Preview not found; fetch a fresh Tiger snapshot")
    try:
        record = json.loads(preview_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(400, "Preview is unreadable; fetch a fresh Tiger snapshot") from exc
    created = datetime.fromisoformat(record["created_at"])
    if (datetime.now(timezone.utc) - created).total_seconds() > 1800:
        raise HTTPException(409, "Preview expired; fetch a fresh Tiger snapshot")
    snapshot = record["snapshot"]
    if snapshot.get("scope") == "stocks_only" and not body.confirm_stock_only:
        raise HTTPException(400, "Confirm explicitly that this replacement imports stocks only")
    if not snapshot.get("can_apply"):
        raise HTTPException(400, {"message": "Snapshot contains unsupported or incomplete data", "issues": snapshot.get("issues"),
                                  "rejected": snapshot.get("rejected")})
    if not snapshot["book"]["positions"] and not body.confirm_empty:
        raise HTTPException(400, "Confirm explicitly to replace the portfolio with zero positions")
    try:
        with _data_write_lock():
            backup = apply_replacement(BOOK, snapshot["book"], record["book_version"])
    except TigerImportError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"ok": True, "backup": backup.name if backup else None, "positions": len(snapshot["book"]["positions"]),
            "currency": snapshot["book"]["currency"]}


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

@app.get("/api/reports")
def reports(ticker: Optional[str] = None):
    items = _list_reports()
    if ticker:
        t = _safe_ticker(ticker)
        items = [i for i in items if i["ticker"].upper() == t]
    # latest rating per ticker
    latest: dict[str, dict] = {}
    for i in items:
        tk = i["ticker"]
        if tk not in latest:
            latest[tk] = i
    return {"reports": items, "latest_by_ticker": latest}


@app.get("/api/reports/{report_id}")
def report_detail(report_id: str):
    if not re.fullmatch(r"[A-Za-z0-9.\-_]+", report_id):
        raise HTTPException(400, "Invalid report id")
    d = REPORTS_DIR / report_id
    md = d / "complete_report.md"
    if not md.exists():
        raise HTTPException(404, "Report not found")
    meta = _parse_report_meta(report_id, md)
    text = md.read_text(encoding="utf-8", errors="replace")
    return {"meta": meta, "markdown": text}


# ---------------------------------------------------------------------------
# Fund manager
# ---------------------------------------------------------------------------

def _history_row(run: dict) -> dict:
    return {
        "date": run["date"],
        "path": run["rel"],
        "kind": run["kind"],
        "has_report": run["kind"] == "report",
        "has_json": run["report_json"] is not None,
        "has_stats": run["stats_path"] is not None,
    }


def _fund_payload(run: Optional[dict]) -> dict:
    history = [_history_row(r) for r in _fm_runs()]
    if run is None:
        return {"date": None, "path": None, "markdown": None, "decision": None, "trades": [],
                "warnings": [], "history": history}
    view = _load_run_view(run)
    bundle = _decision_bundle(view.get("json"))
    return {
        "date": view.get("date"),
        "path": view.get("path"),
        "kind": view.get("kind"),
        "markdown": view.get("markdown"),
        "decision": bundle["decision"],
        "trades": bundle["trades"],
        "warnings": bundle["warnings"],
        "cash_decision": bundle["cash_decision"],
        "ending_cash": bundle["ending_cash"],
        "ending_cash_pct": bundle["ending_cash_pct"],
        "post_trade_risk": bundle["post_trade_risk"],
        "history": history,
    }


@app.get("/api/fund-manager")
def fund_manager():
    runs = _fm_runs()
    chosen = next((r for r in runs if r["kind"] == "report"), None)
    if chosen is None and runs:
        chosen = runs[0]
    return _fund_payload(chosen)


@app.get("/api/fund-manager/at")
def fund_manager_at(path: str):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:/\d{6}_[A-Za-z0-9]+)?", path):
        raise HTTPException(400, "Invalid path")
    run = next((r for r in _fm_runs() if r["rel"] == path), None)
    if run is None:
        raise HTTPException(404, "No fund manager run at that path")
    return _fund_payload(run)


@app.get("/api/fund-manager/{date}")
def fund_manager_date(date: str):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise HTTPException(400, "Invalid date")
    runs = [r for r in _fm_runs() if r["date"] == date]
    if not runs:
        raise HTTPException(404, "No fund manager run for that date")
    chosen = next((r for r in runs if r["kind"] == "report"), runs[0])
    return _fund_payload(chosen)


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

def _spawn_run(meta: dict, args: list[str]) -> None:
    """Background worker: run native pipeline, stream stdout to log."""
    rid = meta["id"]
    log_path = _run_log_path(rid)
    meta["status"] = "running"
    meta["pid"] = None
    _save_run(meta)

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0

    try:
        with open(log_path, "w", encoding="utf-8", errors="replace") as log:
            log.write(f"# Argus run {rid}\n# cmd: {' '.join(args)}\n# started {meta['started_at']}\n\n")
            log.flush()
            run_env = os.environ.copy()
            run_env["ARGUS_RUN_RESULT_FILE"] = str(RUNS_DIR / rid / "result.json")
            proc = subprocess.Popen(
                args,
                cwd=str(TA_ROOT),
                env=run_env,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=creationflags,
            )
            meta["pid"] = proc.pid
            _save_run(meta)
            code = proc.wait()
            meta["exit_code"] = code
            meta["status"] = "succeeded" if code == 0 else ("skipped" if code == 75 else "failed")
            meta["finished_at"] = datetime.now(timezone.utc).isoformat()
            _save_run(meta)
            log.write(f"\n# finished status={meta['status']} exit={code}\n")
    except Exception as e:
        meta["status"] = "failed"
        meta["error"] = str(e)
        meta["finished_at"] = datetime.now(timezone.utc).isoformat()
        _save_run(meta)
        try:
            with open(log_path, "a", encoding="utf-8") as log:
                log.write(f"\n# ERROR: {e}\n")
        except Exception:
            pass


@app.get("/api/runs")
def runs_list():
    return {"runs": _list_runs(), "flags": _script_flags()}


@app.get("/api/runs/{run_id}")
def runs_get(run_id: str):
    meta = _load_run(run_id)
    log_path = _run_log_path(run_id)
    log_tail = ""
    if log_path.exists():
        text = log_path.read_text(encoding="utf-8", errors="replace")
        log_tail = text[-20000:]
    return {"meta": meta, "log_tail": log_tail}


@app.get("/api/runs/{run_id}/log")
def runs_log_stream(run_id: str, from_byte: int = Query(0, ge=0)):
    """SSE-ish plain text stream: returns new log bytes (poll-friendly)."""
    _load_run(run_id)
    log_path = _run_log_path(run_id)
    if not log_path.exists():
        return {"offset": 0, "chunk": "", "done": False}

    data = log_path.read_bytes()
    chunk = data[from_byte:].decode("utf-8", errors="replace")
    meta = _load_run(run_id)
    done = meta.get("status") in ("succeeded", "failed", "skipped", "interrupted")
    return {"offset": len(data), "chunk": chunk, "done": done, "status": meta.get("status")}


SCOUT_SCRIPT = TA_ROOT / "addons" / "theme_scout" / "run_theme_scout.ps1"
SCOUT_DIR = DATA / "theme_scout"


def _latest_theme_scout() -> dict:
    if not SCOUT_DIR.exists():
        return {"report": None, "screen": None, "markdown": "", "date": None}
    dates = sorted([p for p in SCOUT_DIR.iterdir() if p.is_dir()], key=lambda p: p.name, reverse=True)
    chosen = None
    for folder in dates:
        if (folder / "report.json").exists() or (folder / "screen.json").exists():
            chosen = folder
            break
    if chosen is None:
        return {"report": None, "screen": None, "markdown": "", "date": None}
    report = _read_json(chosen / "report.json") if (chosen / "report.json").exists() else None
    screen = _read_json(chosen / "screen.json") if (chosen / "screen.json").exists() else None
    md_path = chosen / "report.md"
    if not md_path.exists():
        md_path = chosen / "screen.md"
    markdown = md_path.read_text(encoding="utf-8", errors="replace") if md_path.exists() else ""
    return {
        "date": chosen.name,
        "report": report,
        "screen": screen.get("ranked") if isinstance(screen, dict) else None,
        "tier_candidates": (screen or {}).get("tier_candidates") if isinstance(screen, dict) else None,
        "markdown": markdown,
        "relative_strength": (report or {}).get("relative_strength") if isinstance(report, dict) else None,
        "changes": (report or {}).get("changes") if isinstance(report, dict) else None,
        "model_skipped": (report or {}).get("model_skipped") if isinstance(report, dict) else True,
    }


@app.get("/api/theme-scout")
def theme_scout_view():
    return _latest_theme_scout()


def _latest_watchlist_proposal() -> Path | None:
    if not SCOUT_DIR.is_dir():
        return None
    folders = sorted((p for p in SCOUT_DIR.iterdir() if p.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.name)),
                     key=lambda p: p.name, reverse=True)
    return next((folder / "watchlist_proposals.json" for folder in folders
                 if (folder / "watchlist_proposals.json").is_file()), None)


def _proposal_payload_hash(proposal: dict) -> str:
    payload = json.dumps(proposal, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@app.get("/api/watchlist/proposal")
def watchlist_proposal_view():
    path = _latest_watchlist_proposal()
    if path is None:
        return {"proposal": None, "applicable": False, "reason": "No scout proposal is available."}
    proposal = _read_json(path)
    coverage = {key: proposal.get(key) for key in (
        "ranking_status", "ranking_count", "ranking_expected_count",
        "ranking_missing_tickers", "ranking_warnings") if key in proposal}
    saved = _saved_watchlist_items()
    current_version = _watchlist_version(saved)
    base_version = proposal.get("base_watchlist_version")
    book = _read_json(BOOK) if BOOK.exists() else {"positions": []}
    held = {str(row.get("ticker") or "").upper() for row in book.get("positions") or []}
    staged = _staged_tickers()
    saved_by = {row["ticker"]: row for row in saved}
    proposed_by = {str(row.get("ticker") or "").upper(): row for row in proposal.get("proposed") or []
                   if isinstance(row, dict)}
    review_changes = []
    for change in proposal.get("changes") or []:
        if not isinstance(change, dict) or change.get("action") not in {"add", "drop"}:
            continue
        ticker = str(change.get("ticker") or "").upper()
        row = proposed_by.get(ticker) if change["action"] == "add" else saved_by.get(ticker)
        blocked = ""
        if change["action"] == "drop" and ticker in held:
            blocked = "This instrument is currently held."
        elif change["action"] == "drop" and ticker in staged:
            blocked = "This instrument has a staged order."
        review_changes.append({**change, "sector": (row or {}).get("sector"),
                               "type": (row or {}).get("type"), "blocked_reason": blocked})
    if not base_version:
        return {"proposal": proposal, "review_changes": review_changes, "coverage": coverage,
                "date": path.parent.name, "base_watchlist_version": None,
                "current_watchlist_version": current_version, "applicable": False,
                "reason": "This proposal predates watchlist versioning. Run the scout again to review it safely."}
    stale = base_version != current_version
    proposal_sha256 = _proposal_payload_hash(proposal)
    return {"proposal": proposal, "review_changes": review_changes, "coverage": coverage,
            "date": path.parent.name,
            "base_watchlist_version": base_version, "current_watchlist_version": current_version,
            "proposal_sha256": proposal_sha256,
            "applicable": not stale,
            "reason": "The watchlist changed after this proposal was generated." if stale else ""}


@app.post("/api/watchlist/proposal/apply")
def apply_watchlist_proposal(body: WatchlistProposalApply, request: Request):
    _require_confirm_token(request)
    if not body.confirm:
        raise HTTPException(400, "Set confirm=true after reviewing the selected proposal changes")
    try:
        proposal_date = datetime.strptime(body.date, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise HTTPException(400, "date must be YYYY-MM-DD") from exc
    adds = [_safe_ticker(t) for t in body.add]
    drops = [_safe_ticker(t) for t in body.drop]
    if len(set(adds)) != len(adds) or len(set(drops)) != len(drops) or set(adds) & set(drops):
        raise HTTPException(400, "Proposal selections must be unique and cannot add and drop the same ticker")

    with _data_write_lock():
        path = SCOUT_DIR / proposal_date / "watchlist_proposals.json"
        if not path.is_file():
            raise HTTPException(404, "Scout proposal not found")
        proposal = _read_json(path)
        proposal_version = proposal.get("base_watchlist_version")
        current = _saved_watchlist_items()
        current_version = _watchlist_version(current)
        if not proposal_version or proposal_version != body.base_watchlist_version or current_version != proposal_version:
            raise HTTPException(409, "The watchlist changed after this proposal was generated. Rerun the scout before applying it.")
        if not re.fullmatch(r"[0-9a-f]{64}", body.proposal_sha256) or _proposal_payload_hash(proposal) != body.proposal_sha256:
            raise HTTPException(409, "The scout proposal changed after review. Review the current proposal before applying it.")
        sectors = _validate_scout_sectors(proposal.get("sectors") or [])
        changes = {(str(row.get("action") or ""), str(row.get("ticker") or "").upper()): row
                   for row in proposal.get("changes") or [] if isinstance(row, dict)}
        if any(("add", ticker) not in changes for ticker in adds):
            raise HTTPException(400, "An add selection is not part of this proposal")
        if any(("drop", ticker) not in changes for ticker in drops):
            raise HTTPException(400, "A drop selection is not part of this proposal")
        if not adds and not drops:
            raise HTTPException(400, "Select at least one proposal change to apply")

        book = _read_json(BOOK) if BOOK.exists() else {"positions": []}
        held = {str(row.get("ticker") or "").upper() for row in book.get("positions") or []}
        staged = _staged_tickers()
        protected = (set(drops) & held) | (set(drops) & staged)
        if protected:
            raise HTTPException(409, "Held or staged names cannot be removed: " + ", ".join(sorted(protected)))

        proposed = {str(row.get("ticker") or "").upper(): row for row in proposal.get("proposed") or []
                    if isinstance(row, dict) and row.get("ticker")}
        current_by_ticker = {row["ticker"]: row for row in current}
        missing_drops = set(drops) - set(current_by_ticker)
        if missing_drops:
            raise HTTPException(409, "Proposal drops are no longer on the watchlist: " + ", ".join(sorted(missing_drops)))
        if any(ticker not in proposed for ticker in adds):
            raise HTTPException(400, "An add selection has no proposed candidate row")
        updated = [row for row in current if row["ticker"] not in set(drops)]
        updated_tickers = {row["ticker"] for row in updated}
        for ticker in adds:
            if ticker in updated_tickers:
                raise HTTPException(409, f"{ticker} is already on the watchlist")
            row = dict(proposed[ticker])
            row["ticker"] = _safe_ticker(ticker)
            sector = str(row.get("sector") or "").strip()
            if not sector:
                raise HTTPException(400, f"{ticker} has no sector classification")
            if row.get("type", "stock") not in ("stock", "etf"):
                raise HTTPException(400, f"{ticker} has an unsupported instrument type")
            sector_key = _canonical_sector_key(sector)
            selected_group = next((code for code in sectors
                                   if sector_key == _canonical_sector_key(code)), None)
            if selected_group is None:
                raise HTTPException(400, f"{ticker} is outside the selected discovery sectors")
            _validate_watchlist_add(row, updated)
            updated.append(row)
            updated_tickers.add(ticker)

        import watchlist_log
        event_group = []
        for ticker in drops:
            event_group.append({
                "as_of": datetime.now().strftime("%Y-%m-%d"), "action": "drop", "ticker": ticker,
                "reason": changes[("drop", ticker)].get("reason") or "approved from scout proposal",
                "source": "scout_review", "row": current_by_ticker[ticker],
            })
        for ticker in adds:
            event_group.append({
                "as_of": datetime.now().strftime("%Y-%m-%d"), "action": "add", "ticker": ticker,
                "reason": changes[("add", ticker)].get("reason") or "approved from scout proposal",
                "source": "scout_review", "row": proposed[ticker],
            })
        _commit_watchlist_transaction(current, updated, event_group, uuid.uuid4().hex)
        return {"ok": True, "items": get_watchlist()["items"],
                "watchlist_version": _watchlist_version(updated), "added": adds, "dropped": drops}


@app.post("/api/theme-scout")
def theme_scout_run(body: ScoutRequest, request: Request):
    _require_confirm_token(request)
    if not body.confirm:
        raise HTTPException(400, "Set confirm=true after acknowledging the screen or the weekly configured model call")
    if body.mode not in ("screen", "weekly"):
        raise HTTPException(400, "mode must be screen or weekly")
    preview = _build_scout_manifest(body)
    if (not body.manifest_sha256 or
            not secrets.compare_digest(body.manifest_sha256, preview["manifest_sha256"])):
        raise HTTPException(409, "Scout inputs or configuration changed after review. Review the current scout manifest and confirm again.")
    sectors = preview["manifest"]["sectors"]
    if not RUNNER.exists():
        raise HTTPException(500, f"Native runner missing: {RUNNER}")
    args = [sys.executable, str(RUNNER), "--ta-root", str(TA_ROOT), "--data-root", str(DATA),
            "--scout-mode", body.mode, "--manifest-input-fingerprint",
            preview["manifest"]["input_fingerprint"]["sha256"]]
    if body.include_llm:
        args.append("--scout-llm")
    if body.single_call:
        args.append("--scout-single-call")
    args.extend(["--scout-sectors", *sectors])
    est_min = 3 if body.mode == "screen" or not body.include_llm else 6
    rid = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    meta = {
        "id": rid,
        "status": "queued",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "exit_code": None,
        "pid": None,
        "args": args,
        "options": body.model_dump(),
        "estimate_minutes": est_min,
        "ticker_count": 0,
        "kind": "theme_scout",
    }
    (RUNS_DIR / rid).mkdir(parents=True, exist_ok=True)
    _save_run(meta)
    _run_log_path(rid).write_text("", encoding="utf-8")
    threading.Thread(target=_spawn_run, args=(meta, args), daemon=True).start()
    return {"run": meta}


def _build_scout_manifest(body: ScoutRequest) -> dict:
    if body.mode not in ("screen", "weekly"):
        raise HTTPException(400, "mode must be screen or weekly")
    if body.include_llm and body.mode != "weekly":
        raise HTTPException(400, "A paid scout call is available only in weekly mode")
    sectors = _validate_scout_sectors(body.sectors or list(SCOUT_SECTOR_LABELS)[:MAX_SCOUT_SECTORS])
    seat_payload = agent_config.public_payload()
    scout_seat = next((seat for seat in seat_payload.get("seats", []) if seat.get("id") == "theme_scout"), None)
    if body.include_llm and scout_seat is None:
        raise HTTPException(409, "Theme scout model configuration is unavailable")
    input_fingerprint = _execution_input_fingerprint()
    book = _read_json(BOOK) if BOOK.is_file() else {"positions": []}
    holdings = list(dict.fromkeys(str(row.get("ticker") or "").upper()
                                  for row in book.get("positions") or [] if row.get("ticker")))
    held = set(holdings)
    candidates = list(dict.fromkeys(str(row.get("ticker") or "").upper()
                                    for row in _saved_watchlist_items()
                                    if row.get("ticker") and str(row.get("ticker")).upper() not in held))
    sector_etfs = [{"ticker": ticker, "sector": SCOUT_SECTOR_LABELS[ticker]}
                   for ticker in sectors]
    estimate = ((float(scout_seat["est_cost_usd"])
                 if scout_seat.get("est_cost_usd") is not None else None)
                if body.include_llm else 0.0)
    import cost_ledger
    targets = _read_json(TARGETS) if TARGETS.is_file() else {}
    cost_policy = cost_ledger.budget_policy(targets)
    weekly_spend = cost_ledger.weekly_spend(DATA, datetime.now(timezone.utc).date(), targets)
    manifest = {
        "mode": body.mode,
        "sectors": sectors,
        "include_llm": body.include_llm,
        "single_call": bool(body.include_llm and body.single_call),
        "model": ({key: scout_seat.get(key) for key in
                   ("id", "label", "model", "effort", "max_tokens", "temperature", "est_cost_usd")}
                  if scout_seat else None),
        "retry_policy": "zero automatic retries" if body.include_llm and body.single_call else "configured runtime retry policy",
        "model_scope": {
            "holdings": holdings,
            "saved_candidates": candidates,
            "selected_sector_etfs": sector_etfs,
            "dynamic_discovery": {
                "source": "Yahoo sector screener plus free market-data screen",
                "max_stock_tickers_per_sector": 20,
                "maximum_stock_tickers": 20 * len(sectors),
                "actual_tickers_known_before_run": False,
                "note": "The free screen selects discovered stock symbols before the scout model request; the exact discovered symbols appear in the run report.",
            },
            "fixed_market_context": ["SPY", "QQQ", "SMH"],
        },
        "input_fingerprint": input_fingerprint,
        "cost_estimate": {
            "amount_usd": estimate,
            "is_hard_ceiling": False,
            "verified_current": False,
            "source": "local_model_price_and_token_estimate" if estimate is not None and body.include_llm
                      else "unavailable" if body.include_llm else "no_paid_model_call",
            "note": ("Local model-based estimate only; rates are not verified current and this is not a spending cap. Check actual provider cost after the call."
                     if body.include_llm and estimate is not None
                     else "Unavailable: the configured scout model has no local price and token estimate. Check actual provider cost after the call."
                     if body.include_llm
                     else "No paid model call is included."),
        },
        "spending_controls": {
            "weekly_budget_enabled": cost_policy.get("enabled", True),
            "weekly_budget_usd": cost_policy["weekly_usd"],
            "spent_usd": weekly_spend["spent_usd"],
            "note": ("Weekly spending check is disabled; usage is still recorded."
                     if not cost_policy.get("enabled", True)
                     else "Runner checks the weekly allowance before this request; the local estimate is not a provider-side cap."),
        },
    }
    request_values = body.model_dump()
    request_values.pop("confirm", None)
    request_values.pop("manifest_sha256", None)
    manifest["request"] = request_values
    digest = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":"),
                                              ensure_ascii=False).encode("utf-8")).hexdigest()
    return {"manifest": manifest, "manifest_sha256": digest}


def _execution_input_fingerprint() -> dict:
    return _fingerprint_run_inputs(DATA, TA_ROOT, {
        "agent_config": Path(agent_config.config_path()),
        "model_rates": Path(agent_config.models_path()),
    })


@app.post("/api/theme-scout/manifest")
def theme_scout_manifest(body: ScoutRequest):
    return _build_scout_manifest(body)


def _build_run_manifest(body: RunRequest) -> dict:
    if body.no_llm and body.analysis_only:
        raise HTTPException(400, "ANL-only requires paid ticker analysis; use snapshot mode for a no-LLM run")
    if body.analysis_date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", body.analysis_date):
        raise HTTPException(400, "analysis_date must be YYYY-MM-DD")
    if body.since and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", body.since):
        raise HTTPException(400, "since must be YYYY-MM-DD")
    requested = list(dict.fromkeys(_safe_ticker(t) for t in body.tickers))
    book = _read_json(BOOK) if BOOK.is_file() else {"positions": []}
    holdings = list(dict.fromkeys(str(row.get("ticker") or "").upper()
                                  for row in book.get("positions") or [] if row.get("ticker")))
    saved = _saved_watchlist_items()
    candidates = list(dict.fromkeys(str(row.get("ticker") or "").upper() for row in saved
                                    if row.get("ticker") and str(row.get("ticker")).upper() not in holdings))
    eligible = (holdings if body.run_agents else []) + (candidates if body.include_watchlist else [])
    eligible = list(dict.fromkeys(eligible))
    if requested:
        invalid = sorted(set(requested) - set(eligible))
        if invalid and not body.no_llm:
            raise HTTPException(400, "Selected tickers are outside the enabled ANL scope: " + ", ".join(invalid))
        analysis_tickers = [ticker for ticker in eligible if ticker in requested]
    else:
        analysis_tickers = eligible
    if body.analysis_only and not requested:
        raise HTTPException(400, "ANL-only requires explicit ticker selection")
    if body.analysis_only and not analysis_tickers:
        raise HTTPException(400, "ANL-only has no eligible selected tickers")
    if not body.no_llm and (body.run_agents or body.include_watchlist) and not analysis_tickers and not body.analysis_only:
        raise HTTPException(400, "The enabled ANL scope has no eligible tickers")

    if body.no_llm:
        mode = "snapshot"
    elif body.analysis_only:
        mode = "ANL"
    elif analysis_tickers:
        mode = "ANL+REV"
    else:
        mode = "REV"
    if mode == "snapshot":
        # Snapshot runs execute no fresh LLM ticker analysis even when the form
        # retains ticker selections from a prior paid run.
        analysis_tickers = []

    portfolio_tickers = holdings + candidates
    seat_payload = agent_config.public_payload()
    safe_fields = ("id", "label", "pipeline", "model", "max_tokens", "est_input_tokens", "est_output_tokens", "est_cost_usd")
    all_seats = [{**{key: seat.get(key) for key in safe_fields},
                  "max_tokens_setting": seat.get("max_tokens") if seat.get("max_tokens") is not None
                  else "not explicitly set; runtime default"}
                 for seat in seat_payload.get("seats") or []]
    native_seats = [seat for seat in all_seats if seat.get("pipeline") == "native"]
    fund_seats_by_id = {seat.get("id"): seat for seat in all_seats if seat.get("pipeline") == "fund"}
    stages = []
    if mode == "snapshot":
        stages = [
            {"id": "SCR", "name": "Market data preflight and screen", "paid": False},
            {"id": "REV-SNAPSHOT", "name": "No-LLM portfolio snapshot", "paid": False},
        ]
    if mode in {"ANL", "ANL+REV"}:
        stages.extend({"id": f"ANL:{ticker}", "name": f"Fresh ticker analysis: {ticker}", "paid": True,
                       "workflow": ["market", "sentiment", "news", "fundamentals", "bull/bear research",
                                    "research manager", "trader", "ticker risk committee", "portfolio manager"],
                       "configured_seats": native_seats}
                      for ticker in analysis_tickers)
    if mode in {"REV", "ANL+REV"}:
        stages.extend([
            {"id": "REV:DRAFT", "name": "Portfolio review draft", "paid": True,
             "seat": fund_seats_by_id.get("fm_manager")},
            {"id": "REV:RISK:1", "name": "Portfolio risk committee, round 1", "paid": True,
             "seats": [fund_seats_by_id.get(key) for key in
                       ("fm_aggressive", "fm_conservative", "fm_neutral")]},
            {"id": "REV:FINAL", "name": "Portfolio review final", "paid": True,
             "seat": fund_seats_by_id.get("fm_manager")},
        ])
    if body.include_risk:
        # This selects existing ticker risk notes as context; it is not another run stage.
        for stage in stages:
            if stage["id"] == "REV:DRAFT":
                stage["include_existing_ticker_risk_notes"] = True

    targets = _read_json(TARGETS) if TARGETS.is_file() else {}
    import cost_ledger
    cost_policy = cost_ledger.budget_policy(targets)
    expected_paid = len(analysis_tickers) if mode in {"ANL", "ANL+REV"} else 0
    include_rev = mode in {"REV", "ANL+REV"}
    cost_estimate = (expected_paid * cost_policy["native_run_estimate_usd"]
                     + (cost_policy["fund_manager_estimate_usd"] if include_rev else 0))
    spend = cost_ledger.weekly_spend(DATA, datetime.now(timezone.utc).date(), targets)
    report_sources = {}
    report_date_anchor = body.analysis_date or datetime.now(timezone.utc).date().isoformat()
    for ticker in portfolio_tickers:
        latest = None
        if REPORTS_DIR.is_dir():
            for folder in REPORTS_DIR.iterdir():
                match = re.fullmatch(r"(.+)_(\d{8}_\d{6})", folder.name)
                if folder.is_dir() and match and match.group(1).upper() == ticker and (folder / "complete_report.md").is_file():
                    if latest is None or match.group(2) > latest[0]:
                        latest = (match.group(2), folder)
        if latest is None:
            report_sources[ticker] = {"status": "missing", "analysis_date": None}
            continue
        stamp, folder = latest
        text_header = (folder / "complete_report.md").read_text(encoding="utf-8", errors="replace")[:1500]
        match_date = re.search(r"Analysis date:\s*(\S+)", text_header)
        source_date = match_date.group(1) if match_date else f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}"
        if ticker in holdings and body.since and stamp[:8] < body.since.replace("-", ""):
            status = "excluded_by_since"
        else:
            try:
                age = (datetime.strptime(report_date_anchor, "%Y-%m-%d").date()
                       - datetime.strptime(source_date, "%Y-%m-%d").date()).days
            except ValueError:
                age = None
            status = "unknown" if age is None else "future" if age < 0 else "current" if age == 0 else "reused" if age <= 7 else "stale"
        report_sources[ticker] = {"status": status, "analysis_date": source_date,
                                  "report_dir": folder.name}
    price_models = [{key: row.get(key) for key in ("id", "label", "usd_per_mtok_in", "usd_per_mtok_out")}
                    for row in seat_payload.get("models") or []]
    input_fingerprint = _execution_input_fingerprint()
    manifest = {
        "mode": mode,
        "request": {key: value for key, value in body.model_dump().items()
                    if key not in {"confirm", "manifest_sha256"}},
        "analysis_date": body.analysis_date or "auto (resolved by market preflight)",
        "since": body.since or None,
        "fresh_analysis_tickers": analysis_tickers,
        "portfolio_review_context_tickers": portfolio_tickers if include_rev else [],
        "portfolio_report_inputs": report_sources if include_rev else {},
        "stages": stages,
        "portfolio_context": {"holdings": holdings, "cash": book.get("cash"),
                              "saved_candidates": candidates} if include_rev or mode == "snapshot" else None,
        "input_fingerprint": input_fingerprint,
        "cost_estimate": {
            "amount_usd": round(cost_estimate, 4),
            "kind": "configured_budget_planning_placeholder",
            "assumptions": {"per_native_ticker_usd": cost_policy["native_run_estimate_usd"],
                            "per_fund_manager_run_usd": cost_policy["fund_manager_estimate_usd"],
                            "native_ticker_count": expected_paid, "fund_manager_runs": int(include_rev)},
            "is_hard_ceiling": False,
            "note": "Configured budget-planning placeholder from local weekly-ledger settings, not a model-priced estimate or provider price quote. Actual provider cost depends on model rates, tokens, tools, retries, and scope; check after the call.",
        },
        "spending_controls": {
            "weekly_budget_usd": cost_policy["weekly_usd"],
            "weekly_budget_enabled": cost_policy.get("enabled", True),
            "spent_usd": spend["spent_usd"],
            "unpriced_runs": spend.get("unpriced_runs", 0),
            "gate": "Runner checks allowance before every native ticker and before the fund-manager stage. It does not impose a provider-side hard ceiling.",
        },
        "model_price_inventory": {
            "rates": price_models,
            "pricing_note": seat_payload.get("pricing_note") or "No local model pricing note.",
            "verified_current": False,
            "warning": "Local rates are inventory only and have not been independently verified as current provider prices.",
        },
        "outputs": {"ticker_reports": "data/logs/reports/<ticker>_<date>_<time>/",
                    "portfolio_report": "data/fund_manager/<analysis-date>/<run-id>/",
                    "run_log": "Argus run history and log"},
    }
    digest = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":"),
                                      ensure_ascii=False).encode("utf-8")).hexdigest()
    return {"manifest": manifest, "manifest_sha256": digest}


@app.post("/api/runs/manifest")
def runs_manifest(body: RunRequest):
    return _build_run_manifest(body)


@app.post("/api/runs")
def runs_start(body: RunRequest, request: Request):
    _require_confirm_token(request)
    if not body.confirm:
        raise HTTPException(400, "Set confirm=true after acknowledging cost/time warning")
    if not RUNNER.exists():
        raise HTTPException(500, f"Native runner missing: {RUNNER}")
    approved_manifest = _build_run_manifest(body)
    if not body.manifest_sha256 or not secrets.compare_digest(body.manifest_sha256, approved_manifest["manifest_sha256"]):
        raise HTTPException(409, "The run scope or configuration changed after review. Review the current manifest and confirm again.")
    flags = _script_flags()
    manifest = approved_manifest["manifest"]
    tickers = manifest["fresh_analysis_tickers"]
    n = len(tickers)
    est_min = 0 if body.no_llm else (int(round(n * 2.5)) + (9 if manifest["mode"] in {"REV", "ANL+REV"} else 0))

    args = [sys.executable, str(RUNNER), "--ta-root", str(TA_ROOT), "--data-root", str(DATA),
            "--manifest-input-fingerprint", manifest["input_fingerprint"]["sha256"],
            "--manifest-analysis-tickers-json", json.dumps(tickers, separators=(",", ":"))]
    if body.run_agents:
        args.append("--run-agents")
    if body.analysis_only:
        args.append("--anl-only")
    if body.no_llm:
        args.append("--no-llm")
    if body.include_risk:
        args.append("--include-risk")
    if body.no_macro:
        args.append("--no-macro")
    if body.include_watchlist:
        args.append("--include-watchlist")
    if body.analysis_date:
        args.extend(["--analysis-date", body.analysis_date])
    if body.since:
        args.extend(["--since", body.since])
    if tickers:
        args.extend(["--tickers", *tickers])

    rid = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    meta = {
        "id": rid,
        "status": "queued",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "exit_code": None,
        "pid": None,
        "args": args,
        "options": body.model_dump(),
        "estimate_minutes": est_min,
        "ticker_count": n,
        "manifest": manifest,
        "manifest_sha256": approved_manifest["manifest_sha256"],
        "estimated_cost_usd": manifest["cost_estimate"]["amount_usd"],
    }
    (RUNS_DIR / rid).mkdir(parents=True, exist_ok=True)
    _save_run(meta)
    _run_log_path(rid).write_text("", encoding="utf-8")

    t = threading.Thread(target=_spawn_run, args=(meta, args), daemon=True)
    t.start()
    return {"ok": True, "run": meta}


# ---------------------------------------------------------------------------
# Static frontend
# ---------------------------------------------------------------------------

@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("ARGUS_PORT", "8787"))
    uvicorn.run(app, host=_BIND_HOST, port=port)
