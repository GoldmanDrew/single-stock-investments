"""Propose once, approve once. Dry-run by default."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

from .classify_positions import norm_sym
from .config_loader import load_config, operator_config
from .safeties import check_safeties
from .store import SleeveStore


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def propose_trade(
    *,
    owner: str,
    ticker: str,
    side: str,
    qty: float,
    limit_price: float,
    quote: Mapping[str, Any],
    holding_period_years: float,
    plc_thesis: str,
    conviction: int,
    cluster: str,
    store: SleeveStore,
    cfg: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_config()
    ticker_n = norm_sym(ticker)
    if not plc_thesis.strip():
        raise ValueError("PLC sentence is required before propose")
    if holding_period_years <= 0:
        raise ValueError("expected holding period (years) is required")
    if conviction not in {1, 2, 3, 4, 5}:
        raise ValueError("conviction must be 1-5")
    op = operator_config(cfg, owner)
    snapshot_last = float(quote.get("last") or quote.get("price") or 0)
    proposal = {
        "proposal_id": str(uuid.uuid4()),
        "owner": owner,
        "ticker": ticker_n,
        "side": str(side).upper(),
        "qty": float(qty),
        "limit_price": float(limit_price),
        "snapshot_last": snapshot_last,
        "qualified_name": quote.get("qualified_name") or ticker_n,
        "exchange": quote.get("exchange") or "SMART",
        "currency": quote.get("currency") or "USD",
        "order_ref": op["order_ref"],
        "holding_period_years": float(holding_period_years),
        "plc_thesis": plc_thesis.strip(),
        "conviction": int(conviction),
        "cluster": cluster or "idiosyncratic",
        "created_at": _iso(_utcnow()),
        "status": "proposed",
        "dry_run": bool((cfg.get("execution") or {}).get("dry_run", True)),
    }
    result = check_safeties(
        owner=owner,
        ticker=ticker_n,
        side=side,
        qty=qty,
        limit_price=limit_price,
        quote=quote,
        proposal=proposal,
        current_positions=store.positions(),
        used_proposal_ids=store.used_proposal_ids(),
        recent_ticker_at=store.recent_ticker_at(),
        cfg=cfg,
    )
    if not result.ok:
        proposal["status"] = "rejected"
        proposal["failures"] = result.failures
        store.save_proposal(proposal)
        raise PermissionError("; ".join(result.failures))
    store.save_proposal(proposal)
    return proposal


def approve_trade(
    *,
    proposal_id: str,
    typed_ticker: str,
    quote: Mapping[str, Any],
    store: SleeveStore,
    cfg: Mapping[str, Any] | None = None,
    ib_submit=None,
) -> dict[str, Any]:
    cfg = cfg or load_config()
    proposal = store.get_proposal(proposal_id)
    if not proposal:
        raise KeyError(f"unknown proposal_id {proposal_id}")
    if proposal.get("status") != "proposed":
        raise PermissionError(f"proposal is {proposal.get('status')}, not proposed")
    result = check_safeties(
        owner=proposal["owner"],
        ticker=proposal["ticker"],
        side=proposal["side"],
        qty=proposal["qty"],
        limit_price=proposal["limit_price"],
        quote=quote,
        proposal=proposal,
        typed_ticker=typed_ticker,
        current_positions=store.positions(),
        used_proposal_ids=store.used_proposal_ids(),
        recent_ticker_at=store.recent_ticker_at(),
        cfg=cfg,
    )
    result.raise_if_failed()
    dry = bool((cfg.get("execution") or {}).get("dry_run", True))
    ib_order_id = None
    if not dry:
        if ib_submit is None:
            raise RuntimeError("live submit function required when dry_run is false")
        ib_order_id = ib_submit(proposal, quote)
    fill = {
        "fill_id": str(uuid.uuid4()),
        "proposal_id": proposal_id,
        "owner": proposal["owner"],
        "ticker": proposal["ticker"],
        "side": proposal["side"],
        "qty": proposal["qty"],
        "price": proposal["limit_price"],
        "commission": 0.0,
        "filled_at": _iso(_utcnow()),
        "source": "dry_run" if dry else "ib",
        "ib_order_id": ib_order_id,
        "dry_run": dry,
    }
    store.record_fill(proposal, fill)
    return fill
