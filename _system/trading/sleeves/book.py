"""Build the dashboard book payload for one owner."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from . import PKG_DIR
from .classify_positions import norm_sym
from .config_loader import load_config, operator_config
from .performance import scorecard
from .store import SleeveStore


def build_book(owner: str, store: SleeveStore, cfg: Mapping[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    op = operator_config(cfg, owner)
    positions = []
    cash_usd = 0.0
    gross = 0.0
    for pos in store.positions():
        cls = pos.get("classification") or {}
        if cls.get("owner") != owner and cls.get("bucket") != owner:
            continue
        ticker = norm_sym(pos.get("ticker") or pos.get("symbol") or "")
        qty = float(pos.get("qty") or pos.get("position") or 0)
        mark = float(pos.get("mark") or pos.get("avgCost") or 0)
        mv = float(pos.get("marketValue") or pos.get("market_value") or qty * mark)
        cost = float(pos.get("costUsd") or pos.get("cost_usd") or 0) or abs(qty * float(pos.get("avgCost") or 0))
        reason = cls.get("reason") or "residual"
        if reason == "cash":
            cash_usd += abs(mv)
            continue
        idea = next((i for i in store.ideas(owner) if norm_sym(i.get("ticker") or "") == ticker), {})
        notes = [n for n in store.notes(owner) if norm_sym(n.get("ticker") or "") == ticker]
        years_held = idea.get("holding_period_years")
        entry = float(idea.get("entry_price") or pos.get("avgCost") or 0) or None
        cost = float(idea.get("cost_usd") or 0) or cost or abs(mv)
        positions.append({
            "ticker": ticker,
            "name": pos.get("name") or ticker,
            "currency": pos.get("currency") or "USD",
            "side": "BUY" if qty >= 0 else "SELL",
            "status": idea.get("status") or ("filled" if qty else "idea"),
            "qty": qty,
            "mark": mark,
            "market_value": mv,
            "entry_price": entry,
            "cost_usd": cost,
            "pnl_usd": mv - cost if cost else None,
            "cluster": idea.get("cluster") or "idiosyncratic",
            "conviction": idea.get("conviction"),
            "plc_score": idea.get("plc_score"),
            "plc_thesis": idea.get("plc_thesis"),
            "holding_period_years": years_held,
            "classifier_reason": reason,
            "notes": notes,
            "needs_thesis": not notes,
        })
        gross += abs(mv)
    positions.sort(key=lambda row: abs(float(row.get("market_value") or 0)), reverse=True)
    equity = op.get("equity_usd")
    if equity is None:
        equity = gross + cash_usd
    extra = float(op.get("extra_margin_usd") or 0)
    metrics = scorecard(
        owner=owner,
        positions=positions,
        notes=store.notes(owner),
        cashflows=store.cashflows(owner),
        capital_base=float(equity) if owner == "drew" else None,
    )
    ideas = store.ideas(owner)
    excluded = {"etf_ls": 0, "spx_0dte": 0, "ignored": 0}
    for pos in store.positions():
        bucket = (pos.get("classification") or {}).get("bucket")
        if bucket in excluded:
            excluded[bucket] += 1
    if owner == "michael":
        blurb = (
            "Live Magis account after taking out the ls-algo universe and SPX 0DTE. "
            "Blacklist names Michael trades by hand stay here even when they are in that universe."
        )
    else:
        blurb = (
            "Starts empty. New buys tagged DREW_SLEEVE on the local desk show up here. "
            "Does not inherit Michael's book. $100k equity plus $100k extra margin."
        )
    return {
        "owner": owner,
        "display_name": op.get("display_name") or owner,
        "as_of": date.today().isoformat(),
        "long_term": True,
        "header": {
            "equity_usd": equity,
            "extra_margin_usd": extra,
            "nav_usd": gross + cash_usd,
            "gross_usd": gross,
            "cash_usd": cash_usd,
            "buying_power_usd": float(equity) + extra - gross,
            "open_names": len(positions),
            "blurb": blurb,
            "excluded": excluded,
        },
        "positions": positions,
        "ideas": ideas,
        "notes": store.notes(owner),
        "fills": store.fills(owner),
        "metrics": metrics,
        "dry_run": bool((cfg.get("execution") or {}).get("dry_run", True)),
        "allow_live": bool((cfg.get("execution") or {}).get("allow_live", False)),
    }


def export_static_books(store: SleeveStore, cfg: Mapping[str, Any] | None = None, *, source: str = "desk_export") -> None:
    """Write dashboard fallback JSON so local Pages preview shows the latest book."""
    dash = PKG_DIR.parents[2] / "dashboard" / "data"
    if not dash.is_dir():
        return
    cfg = cfg or load_config()
    for owner in ("drew", "michael"):
        payload = build_book(owner, store, cfg)
        payload["source"] = source
        path = dash / f"sleeves_{owner}.json"
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
