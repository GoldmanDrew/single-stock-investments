"""Propose once, approve once. Dry-run by default."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

from .config_loader import load_config, operator_config
from .contracts import quote_px, spec_from_mapping
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
    spec = spec_from_mapping({
        "ticker": ticker,
        "sec_type": quote.get("sec_type") or quote.get("secType") or "STK",
        "underlying": quote.get("underlying"),
        "expiry": quote.get("expiry"),
        "strike": quote.get("strike"),
        "right": quote.get("right"),
        "local_symbol": quote.get("local_symbol") or quote.get("localSymbol"),
        "currency": quote.get("currency"),
        "exchange": quote.get("exchange"),
        "multiplier": quote.get("multiplier"),
        "con_id": quote.get("conId") or quote.get("con_id"),
    })
    ticker_n = spec["ticker"]
    if not plc_thesis.strip():
        raise ValueError("PLC sentence is required before propose")
    if holding_period_years <= 0:
        raise ValueError("expected holding period (years) is required")
    if conviction not in {1, 2, 3, 4, 5}:
        raise ValueError("conviction must be 1-5")
    op = operator_config(cfg, owner)
    snapshot_last = quote_px(quote)
    if snapshot_last is None:
        snapshot_last = float(quote.get("last") or quote.get("price") or 0)
    proposal = {
        "proposal_id": str(uuid.uuid4()),
        "owner": owner,
        "ticker": ticker_n,
        "underlying": spec["underlying"],
        "sec_type": spec["sec_type"],
        "expiry": spec["expiry"],
        "strike": spec["strike"],
        "right": spec["right"],
        "local_symbol": spec["local_symbol"],
        "multiplier": spec["multiplier"],
        "con_id": spec["con_id"] or quote.get("conId"),
        "side": str(side).upper(),
        "qty": float(qty),
        "limit_price": float(limit_price),
        "snapshot_last": snapshot_last,
        "qualified_name": quote.get("qualified_name") or ticker_n,
        "exchange": quote.get("exchange") or spec["exchange"],
        "currency": quote.get("currency") or spec["currency"],
        "order_ref": op["order_ref"],
        "holding_period_years": float(holding_period_years),
        "plc_thesis": plc_thesis.strip(),
        "conviction": int(conviction),
        "cluster": cluster or "idiosyncratic",
        "created_at": _iso(_utcnow()),
        "status": "proposed",
        "dry_run": bool((cfg.get("execution") or {}).get("dry_run", True)),
    }
    gate_quote = dict(quote)
    gate_quote.setdefault("sec_type", spec["sec_type"])
    gate_quote.setdefault("secType", spec["sec_type"])
    gate_quote.setdefault("underlying", spec["underlying"])
    gate_quote.setdefault("multiplier", spec["multiplier"])
    result = check_safeties(
        owner=owner,
        ticker=ticker_n,
        side=side,
        qty=qty,
        limit_price=limit_price,
        quote=gate_quote,
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
    gate_quote = dict(quote)
    for key in ("sec_type", "underlying", "multiplier", "expiry", "strike", "right", "local_symbol", "con_id"):
        if gate_quote.get(key) in (None, "") and proposal.get(key) not in (None, ""):
            gate_quote[key] = proposal[key]
    gate_quote.setdefault("secType", gate_quote.get("sec_type") or "STK")
    result = check_safeties(
        owner=proposal["owner"],
        ticker=proposal["ticker"],
        side=proposal["side"],
        qty=proposal["qty"],
        limit_price=proposal["limit_price"],
        quote=gate_quote,
        proposal=proposal,
        typed_ticker=typed_ticker,
        current_positions=store.positions(),
        used_proposal_ids=store.used_proposal_ids(),
        recent_ticker_at=store.recent_ticker_at(),
        cfg=cfg,
    )
    result.raise_if_failed()
    dry = bool((cfg.get("execution") or {}).get("dry_run", True))
    if dry:
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
            "source": "dry_run",
            "ib_order_id": None,
            "dry_run": True,
        }
        store.record_fill(proposal, fill)
        return fill
    if ib_submit is None:
        raise RuntimeError("live submit function required when dry_run is false")
    ib_order_id = ib_submit(proposal, quote)
    submitted = {
        "proposal_id": proposal_id,
        "owner": proposal["owner"],
        "ticker": proposal["ticker"],
        "side": proposal["side"],
        "qty": proposal["qty"],
        "limit_price": proposal["limit_price"],
        "ib_order_id": ib_order_id,
        "source": "ib",
        "dry_run": False,
        "status": "submitted",
        "submitted_at": _iso(_utcnow()),
    }
    store.record_submit(proposal, submitted)
    return submitted
