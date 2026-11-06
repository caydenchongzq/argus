"""
Argus — local dashboard for TradingAgents.
Reads TradingAgents data; never modifies TradingAgents source.
Binds to 127.0.0.1 only. Never exposes .env values.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
DEFAULT_TA = Path(r"D:\software development\trading\TradingAgents")
TA_ROOT = Path(os.environ.get("TRADINGAGENTS_ROOT", str(DEFAULT_TA))).resolve()
DATA = TA_ROOT / "data"
BOOK = DATA / "my_book.json"
TARGETS = DATA / "targets.json"
WATCHLIST = DATA / "watchlist.json"
REPORTS_DIR = DATA / "logs" / "reports"
FUND_DIR = DATA / "fund_manager"
RUN_SCRIPT = TA_ROOT / "addons" / "fund_manager" / "run_portfolio.ps1"
RUNS_DIR = Path(os.environ.get("DASHBOARD_RUNS_DIR", str(ROOT / "runs"))).resolve()
RUNS_DIR.mkdir(parents=True, exist_ok=True)

RATING_RE = re.compile(r"(?im)^-\s*Rating:\s*(.+?)\s*$")
REPORT_DIR_RE = re.compile(r"^(.+)_(\d{8})_(\d{6})$")

app = FastAPI(title="Argus", docs_url=None, redoc_url=None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> Any:
    if not path.exists():
        raise HTTPException(404, f"Not found: {path.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _safe_ticker(t: str) -> str:
    t = (t or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9.\-]{1,12}", t):
        raise HTTPException(400, f"Invalid ticker: {t!r}")
    return t


def _latest_stats() -> Optional[dict]:
    if not FUND_DIR.exists():
        return None
    dates = sorted(
        [p for p in FUND_DIR.iterdir() if p.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.name)],
        reverse=True,
    )
    for d in dates:
        for name in ("portfolio_stats.json", "snapshot_portfolio_stats.json"):
            p = d / name
            if p.exists():
                try:
                    return {"date": d.name, "path": str(p), **_read_json(p)}
                except Exception:
                    continue
    return None


def _latest_fund_report() -> Optional[dict]:
    if not FUND_DIR.exists():
        return None
    dates = sorted(
        [p for p in FUND_DIR.iterdir() if p.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.name)],
        reverse=True,
    )
    for d in dates:
        md = d / "portfolio_report.md"
        js = d / "portfolio_report.json"
        if md.exists() or js.exists():
            out: dict[str, Any] = {"date": d.name}
            if js.exists():
                try:
                    out["json"] = _read_json(js)
                except Exception:
                    out["json"] = None
            if md.exists():
                out["markdown"] = md.read_text(encoding="utf-8", errors="replace")
            return out
    return None


def _script_flags() -> dict[str, bool]:
    """Detect which switches exist on run_portfolio.ps1 (e.g. -IncludeWatchlist)."""
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
    if RUN_SCRIPT.exists():
        text = RUN_SCRIPT.read_text(encoding="utf-8", errors="replace")
        flags["IncludeWatchlist"] = bool(re.search(r"\$IncludeWatchlist\b", text))
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
    return json.loads(p.read_text(encoding="utf-8"))


def _save_run(meta: dict) -> None:
    rid = meta["id"]
    d = RUNS_DIR / rid
    d.mkdir(parents=True, exist_ok=True)
    _run_meta_path(rid).write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


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
                out.append(json.loads(mp.read_text(encoding="utf-8")))
            except Exception:
                continue
    out.sort(key=lambda x: x.get("started_at") or "", reverse=True)
    return out


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
        "script_ok": RUN_SCRIPT.exists(),
        "flags": _script_flags(),
    }


@app.get("/api/config")
def config():
    return {
        "app": "Argus",
        "tradingagents_root": str(TA_ROOT),
        "flags": _script_flags(),
        "minutes_per_ticker": 7,
    }


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------

@app.get("/api/portfolio")
def portfolio():
    book = _read_json(BOOK)
    targets = _read_json(TARGETS) if TARGETS.exists() else {"weights_pct": {}}
    stats = _latest_stats()
    price_map: dict[str, dict] = {}
    account = None
    if stats:
        account = stats.get("account")
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
        st = price_map.get(t)
        price = st["price"] if st else None
        mv = st["market_value"] if st else (None)
        if mv is not None:
            invested_mv += float(mv)
        rows.append({
            "ticker": t,
            "quantity": qty,
            "average_price": avg,
            "cost_basis": cost,
            "price": price,
            "market_value": mv,
            "unrealized_pnl": st.get("unrealized_pnl") if st else None,
            "unrealized_pnl_pct": st.get("unrealized_pnl_pct") if st else None,
            "weight_pct": st.get("weight_pct") if st else None,
            "sector": st.get("sector") if st else None,
            "name": st.get("name") if st else None,
            "target_pct": (targets.get("weights_pct") or {}).get(t),
        })

    cash = float(book.get("cash") or 0)
    total_cost = invested_cost + cash
    total_mv = (invested_mv + cash) if price_map else None
    weights_current = []
    for r in rows:
        w = r["weight_pct"]
        if w is None and total_mv and r["market_value"] is not None:
            w = 100.0 * float(r["market_value"]) / total_mv
        weights_current.append({"ticker": r["ticker"], "weight_pct": w, "target_pct": r["target_pct"]})
    cash_pct = None
    if account and account.get("cash_pct") is not None:
        cash_pct = account["cash_pct"]
    elif total_mv:
        cash_pct = 100.0 * cash / total_mv

    return {
        "currency": book.get("currency", "USD"),
        "cash": cash,
        "cash_pct": cash_pct,
        "cash_target_pct": (targets.get("weights_pct") or {}).get("cash"),
        "positions": rows,
        "weights": weights_current,
        "targets": targets.get("weights_pct") or {},
        "account": account,
        "total_cost": total_cost,
        "total_market_value": account.get("total_value") if account else total_mv,
        "stats_date": stats.get("date") if stats else None,
        "prices_as_of": (stats.get("as_of_prices") if stats else None),
    }


# ---------------------------------------------------------------------------
# Watchlist
# ---------------------------------------------------------------------------

@app.get("/api/watchlist")
def get_watchlist():
    if not WATCHLIST.exists():
        return {"items": []}
    data = _read_json(WATCHLIST)
    if isinstance(data, dict):
        items = data.get("items") or data.get("tickers") or []
    else:
        items = data
    return {"items": items}


@app.post("/api/watchlist")
def add_watchlist(item: WatchlistAdd):
    ticker = _safe_ticker(item.ticker)
    current = get_watchlist()["items"]
    for it in current:
        if str(it.get("ticker", "")).upper() == ticker:
            raise HTTPException(409, f"{ticker} already on watchlist")
    # backup
    if WATCHLIST.exists():
        bak = WATCHLIST.with_suffix(WATCHLIST.suffix + f".bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        shutil.copy2(WATCHLIST, bak)
    entry = {"ticker": ticker, "sector": item.sector.strip() or "Other", "type": item.type}
    current.append(entry)
    _write_json(WATCHLIST, current)
    return {"ok": True, "items": current}


@app.delete("/api/watchlist/{ticker}")
def remove_watchlist(ticker: str):
    ticker = _safe_ticker(ticker)
    if not WATCHLIST.exists():
        raise HTTPException(404, "Watchlist empty")
    if WATCHLIST.exists():
        bak = WATCHLIST.with_suffix(WATCHLIST.suffix + f".bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        shutil.copy2(WATCHLIST, bak)
    current = get_watchlist()["items"]
    new = [it for it in current if str(it.get("ticker", "")).upper() != ticker]
    if len(new) == len(current):
        raise HTTPException(404, f"{ticker} not on watchlist")
    _write_json(WATCHLIST, new)
    return {"ok": True, "items": new}


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

@app.get("/api/fund-manager")
def fund_manager():
    latest = _latest_fund_report()
    history = []
    if FUND_DIR.exists():
        for p in sorted(
            [x for x in FUND_DIR.iterdir() if x.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", x.name)],
            reverse=True,
        ):
            history.append({
                "date": p.name,
                "has_report": (p / "portfolio_report.md").exists(),
                "has_json": (p / "portfolio_report.json").exists(),
                "has_stats": (p / "portfolio_stats.json").exists() or (p / "snapshot_portfolio_stats.json").exists(),
            })
    trades = []
    decision = None
    markdown = None
    date = None
    if latest:
        date = latest.get("date")
        markdown = latest.get("markdown")
        js = latest.get("json") or {}
        decision = js.get("decision")
        if decision and decision.get("trades"):
            trades = decision["trades"]
    return {
        "date": date,
        "markdown": markdown,
        "decision": decision,
        "trades": trades,
        "history": history,
    }


@app.get("/api/fund-manager/{date}")
def fund_manager_date(date: str):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise HTTPException(400, "Invalid date")
    d = FUND_DIR / date
    if not d.exists():
        raise HTTPException(404, "No fund manager run for that date")
    out: dict[str, Any] = {"date": date}
    md = d / "portfolio_report.md"
    js = d / "portfolio_report.json"
    if md.exists():
        out["markdown"] = md.read_text(encoding="utf-8", errors="replace")
    if js.exists():
        out["json"] = _read_json(js)
        out["decision"] = out["json"].get("decision")
        out["trades"] = (out["decision"] or {}).get("trades") or []
    return out


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

def _spawn_run(meta: dict, args: list[str]) -> None:
    """Background worker: run PowerShell script, stream stdout to log."""
    rid = meta["id"]
    log_path = _run_log_path(rid)
    meta["status"] = "running"
    meta["pid"] = None
    _save_run(meta)

    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    try:
        with open(log_path, "w", encoding="utf-8", errors="replace") as log:
            log.write(f"# Argus run {rid}\n# cmd: {' '.join(args)}\n# started {meta['started_at']}\n\n")
            log.flush()
            proc = subprocess.Popen(
                args,
                cwd=str(TA_ROOT),
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=creationflags,
            )
            meta["pid"] = proc.pid
            _save_run(meta)
            code = proc.wait()
            meta["exit_code"] = code
            meta["status"] = "succeeded" if code == 0 else "failed"
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
    done = meta.get("status") in ("succeeded", "failed")
    return {"offset": len(data), "chunk": chunk, "done": done, "status": meta.get("status")}


@app.post("/api/runs")
def runs_start(body: RunRequest):
    if not body.confirm:
        raise HTTPException(400, "Set confirm=true after acknowledging cost/time warning")
    if not RUN_SCRIPT.exists():
        raise HTTPException(500, f"Run script missing: {RUN_SCRIPT}")

    flags = _script_flags()
    tickers = [_safe_ticker(t) for t in body.tickers] if body.tickers else []

    # Cost/time estimate for UI echo
    n = len(tickers) if tickers else 0
    if body.run_agents and n == 0:
        try:
            n = len((_read_json(BOOK).get("positions") or []))
        except Exception:
            n = 0
    est_min = n * 7 if body.run_agents else (0 if body.no_llm else 5)

    args = [
        "powershell",
        "-ExecutionPolicy", "Bypass",
        "-File", str(RUN_SCRIPT),
    ]
    if body.run_agents:
        args.append("-RunAgents")
    if body.no_llm:
        args.append("-NoLLM")
    if body.include_risk:
        args.append("-IncludeRisk")
    if body.no_macro:
        args.append("-NoMacro")
    if body.include_watchlist:
        if not flags.get("IncludeWatchlist"):
            raise HTTPException(400, "-IncludeWatchlist is not available on the current run script yet")
        args.append("-IncludeWatchlist")
    if body.analysis_date:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", body.analysis_date):
            raise HTTPException(400, "analysis_date must be YYYY-MM-DD")
        args.extend(["-AnalysisDate", body.analysis_date])
    if body.since:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", body.since):
            raise HTTPException(400, "since must be YYYY-MM-DD")
        args.extend(["-Since", body.since])
    if tickers:
        args.extend(["-Tickers", ",".join(tickers)])

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
    uvicorn.run(app, host="127.0.0.1", port=port)
