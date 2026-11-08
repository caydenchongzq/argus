"""
Argus — local dashboard for TradingAgents.
Reads TradingAgents data; never modifies TradingAgents source.
Binds to 127.0.0.1 only. Never exposes .env values.
"""
from __future__ import annotations

import json
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


class AgentSeatIn(BaseModel):
    model: str
    effort: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    system: str = ""


class AgentConfigIn(BaseModel):
    seats: dict[str, AgentSeatIn]
    unlock: list[str] = Field(default_factory=list)


class RunRequest(BaseModel):
    run_agents: bool = False
    no_llm: bool = False
    include_risk: bool = False
    no_macro: bool = False
    include_watchlist: bool = False
    analysis_date: str = ""
    since: str = ""
    tickers: list[str] = Field(default_factory=list)
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


def _sleeve(ticker: str, info: dict | None) -> str:
    kind = str((info or {}).get("type") or "").strip().lower()
    if kind == "etf" or str(ticker or "").strip().upper() in _ETF_TICKERS:
        return "core_etf"
    return "swing"


@app.get("/api/portfolio")
def portfolio():
    # A missing book is a valid first-import state. Keep GET read-only; the
    # Tiger replacement path creates it only after preview and confirmation.
    book = _read_json(BOOK) if BOOK.exists() else {"cash": 0, "currency": "", "positions": []}
    targets = _read_json(TARGETS) if TARGETS.exists() else {"weights_pct": {}}
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
            "target_pct": (targets.get("weights_pct") or {}).get(t),
            "sub_theme": _subtheme_index().get(str(t).upper()),
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
    }
    if total_mv:
        for r in rows:
            bucket = sleeves.get(r.get("sleeve") or "swing", sleeves["swing"])
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
        "cash_target_pct": (targets.get("weights_pct") or {}).get("cash"),
        "positions": rows,
        "weights": weights_current,
        "targets": targets.get("weights_pct") or {},
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

@app.get("/api/watchlist")
def get_watchlist():
    if not WATCHLIST.exists():
        return {"items": [], "subthemes": _subtheme_table([])}
    data = _read_json(WATCHLIST)
    if isinstance(data, dict):
        items = data.get("items") or data.get("tickers") or []
    else:
        items = data
    index = _subtheme_index()
    cleaned = []
    for item in items:
        if isinstance(item, str):
            item = {"ticker": item}
        if not isinstance(item, dict):
            continue
        row = dict(item)
        ticker = str(row.get("ticker") or "").upper()
        row["sub_theme"] = row.get("sub_theme") or index.get(ticker)
        cleaned.append(row)
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
        current = get_watchlist()["items"]
        for it in current:
            if str(it.get("ticker", "")).upper() == ticker:
                raise HTTPException(409, f"{ticker} already on watchlist")
        entry = {"ticker": ticker, "sector": item.sector.strip() or "Other", "type": item.type}
        if item.sub_theme:
            if item.sub_theme not in _subtheme_labels() and item.sub_theme not in SUBTHEME_ORDER:
                raise HTTPException(400, f"Unknown sub_theme {item.sub_theme}")
            entry["sub_theme"] = item.sub_theme
        current.append(entry)
        _write_json(WATCHLIST, current)
        _watch_log("add", ticker, entry, "added in Argus")
        return {"ok": True, "items": current}


@app.delete("/api/watchlist/{ticker}")
def remove_watchlist(ticker: str, request: Request):
    _require_confirm_token(request)
    with _data_write_lock():
        ticker = _safe_ticker(ticker)
        if not WATCHLIST.exists():
            raise HTTPException(404, "Watchlist empty")
        current = get_watchlist()["items"]
        removed = next((it for it in current if str(it.get("ticker", "")).upper() == ticker), None)
        new = [it for it in current if str(it.get("ticker", "")).upper() != ticker]
        if removed is None:
            raise HTTPException(404, f"{ticker} not on watchlist")
        _write_json(WATCHLIST, new)
        _watch_log("drop", ticker, removed, "removed in Argus")
        return {"ok": True, "items": new}


@app.post("/api/watchlist/undo")
def undo_watchlist(request: Request):
    _require_confirm_token(request)
    with _data_write_lock():
        import watchlist_log
        events = watchlist_log.read_events(DATA)
        event = watchlist_log.last_undoable(events)
        if event is None:
            raise HTTPException(404, "Nothing to undo")
        current = get_watchlist()["items"] if WATCHLIST.exists() else []
        updated = watchlist_log.undo_items(current, event)
        _write_json(WATCHLIST, updated)
        undone = watchlist_log.append_event(DATA, {
            "as_of": datetime.now().strftime("%Y-%m-%d"),
            "action": "undo",
            "ticker": event.get("ticker"),
            "reason": f"undo {event.get('action')}",
            "source": "argus",
            "undo_of": event.get("id"),
            "row": event.get("row"),
        })
        return {"ok": True, "undone": undone, "items": updated}


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


@app.post("/api/theme-scout")
def theme_scout_run(body: ScoutRequest, request: Request):
    _require_confirm_token(request)
    if not body.confirm:
        raise HTTPException(400, "Set confirm=true after acknowledging the screen or the weekly Sol call")
    if body.mode not in ("screen", "weekly"):
        raise HTTPException(400, "mode must be screen or weekly")
    if not RUNNER.exists():
        raise HTTPException(500, f"Native runner missing: {RUNNER}")
    args = [sys.executable, str(RUNNER), "--ta-root", str(TA_ROOT), "--scout-mode", body.mode]
    if body.include_llm:
        args.append("--scout-llm")
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


@app.post("/api/runs")
def runs_start(body: RunRequest, request: Request):
    _require_confirm_token(request)
    if not body.confirm:
        raise HTTPException(400, "Set confirm=true after acknowledging cost/time warning")
    if not RUNNER.exists():
        raise HTTPException(500, f"Native runner missing: {RUNNER}")

    flags = _script_flags()
    tickers = [_safe_ticker(t) for t in body.tickers] if body.tickers else []

    # Cost/time estimate for UI echo
    n = len(tickers) if tickers else 0
    if body.run_agents and n == 0:
        try:
            n = len((_read_json(BOOK).get("positions") or []))
        except Exception:
            n = 0
    # Observed per-ticker runs were about 2.5 minutes. The fund-manager step is 5 calls
    # (draft, three risk voices, final). The conservative voice is Opus.
    est_min = 0 if body.no_llm else (int(round(n * 2.5)) if body.run_agents else 9)

    args = [sys.executable, str(RUNNER), "--ta-root", str(TA_ROOT)]
    if body.run_agents:
        args.append("--run-agents")
    if body.no_llm:
        args.append("--no-llm")
    if body.include_risk:
        args.append("--include-risk")
    if body.no_macro:
        args.append("--no-macro")
    if body.include_watchlist:
        args.append("--include-watchlist")
    if body.analysis_date:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", body.analysis_date):
            raise HTTPException(400, "analysis_date must be YYYY-MM-DD")
        args.extend(["--analysis-date", body.analysis_date])
    if body.since:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", body.since):
            raise HTTPException(400, "since must be YYYY-MM-DD")
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
