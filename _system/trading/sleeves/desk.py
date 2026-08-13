"""Local Magis sleeve order desk. Run: python -m _system.trading.sleeves.desk"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from _system.trading.sleeves.book import build_book, export_static_books
from _system.trading.sleeves.config_loader import load_config
from _system.trading.sleeves.ingest import post_ingest
from _system.trading.sleeves.orders import approve_trade, propose_trade
from _system.trading.sleeves.store import SleeveStore
from _system.trading.sleeves.sync_ib import sync_holdings

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import HTMLResponse
except ImportError:  # pragma: no cover
    FastAPI = None  # type: ignore
    HTMLResponse = None  # type: ignore
    HTTPException = Exception  # type: ignore


STATIC = Path(__file__).with_name("static") / "index.html"


def _store() -> SleeveStore:
    return SleeveStore()


def _maybe_ingest(payload: dict) -> dict | None:
    cfg = load_config()
    url = str((cfg.get("ingest") or {}).get("url") or os.environ.get("SLEEVE_INGEST_URL") or "").strip()
    token = os.environ.get(str((cfg.get("ingest") or {}).get("token_env") or "SLEEVE_INGEST_TOKEN") or "")
    if not url or not token:
        return None
    return post_ingest(url, token, payload)


def create_app() -> "FastAPI":
    if FastAPI is None:
        raise RuntimeError("Install fastapi and uvicorn to run the order desk")
    app = FastAPI(title="Magis sleeve desk", docs_url=None, redoc_url=None)
    cfg = load_config()

    @app.get("/", response_class=HTMLResponse)
    def home():
        return STATIC.read_text(encoding="utf-8")

    @app.get("/health")
    def health():
        return {
            "ok": True,
            "dry_run": bool((cfg.get("execution") or {}).get("dry_run", True)),
            "allow_live": bool((cfg.get("execution") or {}).get("allow_live", False)),
            "account": (cfg.get("ibkr") or {}).get("account_id"),
        }

    @app.get("/book")
    def book(owner: str = "drew"):
        if owner not in {"drew", "michael"}:
            raise HTTPException(400, "owner must be drew or michael")
        return build_book(owner, _store(), cfg)

    @app.post("/quote")
    def quote(payload: dict):
        owner = str(payload.get("owner") or "drew")
        ticker = str(payload.get("ticker") or "").strip()
        if not ticker:
            raise HTTPException(400, "ticker required")
        try:
            from _system.trading.sleeves.ib_client import connect_ib, qualify_and_quote
            ib = connect_ib(owner, cfg)
            try:
                q = qualify_and_quote(ib, ticker)
            finally:
                ib.disconnect()
            q.pop("contract", None)
            return q
        except Exception as exc:
            # Desk still works without TWS: operator types a last price.
            return {
                "ticker": ticker.upper(),
                "qualified_name": ticker.upper(),
                "exchange": "SMART",
                "currency": "USD",
                "secType": "STK",
                "last": payload.get("last"),
                "bid": None,
                "ask": None,
                "as_of": payload.get("as_of"),
                "ib_error": str(exc),
                "mock": True,
            }

    @app.post("/propose")
    def propose(payload: dict):
        store = _store()
        quote = payload.get("quote") or {}
        try:
            return propose_trade(
                owner=str(payload["owner"]),
                ticker=str(payload["ticker"]),
                side=str(payload["side"]),
                qty=float(payload["qty"]),
                limit_price=float(payload["limit_price"]),
                quote=quote,
                holding_period_years=float(payload.get("holding_period_years") or 0),
                plc_thesis=str(payload.get("plc_thesis") or ""),
                conviction=int(payload.get("conviction") or 0),
                cluster=str(payload.get("cluster") or "idiosyncratic"),
                store=store,
                cfg=cfg,
            )
        except (PermissionError, ValueError, KeyError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/approve")
    def approve(payload: dict):
        store = _store()
        try:
            fill = approve_trade(
                proposal_id=str(payload["proposal_id"]),
                typed_ticker=str(payload.get("typed_ticker") or ""),
                quote=payload.get("quote") or {},
                store=store,
                cfg=cfg,
            )
            export_static_books(store, cfg)
        except (PermissionError, KeyError, RuntimeError) as exc:
            raise HTTPException(400, str(exc)) from exc
        ingest = None
        try:
            ingest = _maybe_ingest({"kind": "fill", "fill": fill, "book": build_book(fill["owner"], store, cfg)})
        except Exception as exc:
            ingest = {"error": str(exc)}
        return {"fill": fill, "ingest": ingest}

    @app.post("/sync-ib")
    def sync_ib(payload: dict | None = None):
        payload = payload or {}
        flex = payload.get("flex_path")
        result = sync_holdings(
            _store(),
            cfg,
            positions=payload.get("positions"),
            flex_path=Path(flex) if flex else None,
        )
        return {
            "count": result["count"],
            "source": result["source"],
            "buckets": result["buckets"],
            "michael": result["michael"]["header"],
            "drew": result["drew"]["header"],
            "ingest": result["ingest"],
        }

    @app.post("/notes")
    def notes(payload: dict):
        store = _store()
        note = store.add_note(payload)
        return note

    return app


def main() -> None:
    cfg = load_config()
    desk = cfg.get("desk") or {}
    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit("pip install fastapi uvicorn") from exc
    app = create_app()
    uvicorn.run(app, host=str(desk.get("host") or "127.0.0.1"), port=int(desk.get("port") or 8788))


if __name__ == "__main__":
    main()
