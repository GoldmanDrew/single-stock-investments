"""Draft, list, and send sleeve orders through IB Gateway.

Examples:
  python -m _system.trading.sleeves.send quote --ticker CSU
  python -m _system.trading.sleeves.send quote --underlying AAPL --expiry 2026-08-21 --strike 200 --right C
  python -m _system.trading.sleeves.send propose --owner drew --ticker CSU --side BUY --qty 10 --limit 50 --years 3 --conviction 4 --plc "..."
  python -m _system.trading.sleeves.send pending
  python -m _system.trading.sleeves.send approve PROPOSAL_ID --typed CSU
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from _system.trading.sleeves.book import export_static_books
from _system.trading.sleeves.config_loader import load_config
from _system.trading.sleeves.contracts import contract_spec
from _system.trading.sleeves.ib_client import gateway_submit, refresh_quote
from _system.trading.sleeves.orders import approve_trade, propose_trade
from _system.trading.sleeves.store import SleeveStore


def _print(payload: dict) -> None:
    print(json.dumps(payload, indent=2, default=str))


def _spec_from_args(args: argparse.Namespace):
    sec = str(getattr(args, "sec_type", None) or ("OPT" if getattr(args, "expiry", None) or getattr(args, "right", None) else "STK"))
    return contract_spec(
        getattr(args, "ticker", None),
        sec_type=sec,
        underlying=getattr(args, "underlying", None),
        expiry=getattr(args, "expiry", None),
        strike=getattr(args, "strike", None),
        right=getattr(args, "right", None),
        local_symbol=getattr(args, "local_symbol", None),
        currency=getattr(args, "currency", None),
    )


def cmd_quote(args: argparse.Namespace) -> int:
    spec = _spec_from_args(args)
    quote = refresh_quote(args.owner, spec, readonly=True)
    quote.pop("contract", None)
    _print(quote)
    return 0


def cmd_propose(args: argparse.Namespace) -> int:
    spec = _spec_from_args(args)
    quote = refresh_quote(args.owner, spec, readonly=True)
    quote.pop("contract", None)
    limit = args.limit if args.limit is not None else quote["last"]
    store = SleeveStore()
    proposal = propose_trade(
        owner=args.owner,
        ticker=spec["ticker"],
        side=args.side,
        qty=args.qty,
        limit_price=float(limit),
        quote=quote,
        holding_period_years=float(args.years),
        plc_thesis=args.plc,
        conviction=int(args.conviction),
        cluster=args.cluster,
        store=store,
    )
    _print(proposal)
    return 0


def cmd_pending(_args: argparse.Namespace) -> int:
    rows = SleeveStore().pending_proposals()
    _print({"count": len(rows), "proposals": rows})
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    cfg = load_config()
    store = SleeveStore()
    proposal = store.get_proposal(args.proposal_id)
    if not proposal:
        raise SystemExit(f"unknown proposal_id {args.proposal_id}")
    quote = refresh_quote(proposal["owner"], proposal, readonly=True)
    quote.pop("contract", None)
    dry = bool((cfg.get("execution") or {}).get("dry_run", True))
    result = approve_trade(
        proposal_id=args.proposal_id,
        typed_ticker=args.typed,
        quote=quote,
        store=store,
        cfg=cfg,
        ib_submit=None if dry else gateway_submit,
    )
    export_static_books(store, cfg)
    _print(result)
    return 0


def _add_contract_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--ticker", help="Stock ticker, or leave blank for structured options")
    parser.add_argument("--sec-type", dest="sec_type", choices=["STK", "OPT"])
    parser.add_argument("--underlying", help="Option underlying")
    parser.add_argument("--expiry", help="Option expiry YYYY-MM-DD")
    parser.add_argument("--strike", type=float)
    parser.add_argument("--right", help="C or P")
    parser.add_argument("--local-symbol", dest="local_symbol", help="OCC local symbol")
    parser.add_argument("--currency")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Draft and send Magis sleeve orders through IB Gateway")
    sub = parser.add_subparsers(dest="cmd", required=True)

    quote_p = sub.add_parser("quote", help="Live IB bid/ask/last")
    quote_p.add_argument("--owner", default="drew", choices=["drew", "michael"])
    _add_contract_args(quote_p)
    quote_p.set_defaults(func=cmd_quote)

    propose_p = sub.add_parser("propose", help="Quote live, then save a draft that still needs approve")
    propose_p.add_argument("--owner", required=True, choices=["drew", "michael"])
    propose_p.add_argument("--side", required=True, choices=["BUY", "SELL"])
    propose_p.add_argument("--qty", type=float, required=True)
    propose_p.add_argument("--limit", type=float)
    propose_p.add_argument("--years", type=float, required=True)
    propose_p.add_argument("--conviction", type=int, required=True)
    propose_p.add_argument("--plc", required=True, help="What would make this a permanent loss?")
    propose_p.add_argument("--cluster", default="idiosyncratic")
    _add_contract_args(propose_p)
    propose_p.set_defaults(func=cmd_propose)

    pending_p = sub.add_parser("pending", help="List drafts waiting for approve")
    pending_p.set_defaults(func=cmd_pending)

    approve_p = sub.add_parser("approve", help="Retype ticker, refresh live quote, send (or dry-run)")
    approve_p.add_argument("proposal_id")
    approve_p.add_argument("--typed", required=True, help="Retype the ticker or underlying")
    approve_p.set_defaults(func=cmd_approve)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
