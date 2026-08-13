"""IB connection, qualify, snapshot, limit order. Fail closed without ib_insync."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping
import time

from .classify_positions import norm_sym
from .config_loader import load_config, operator_config


class IbUnavailable(RuntimeError):
    pass


def _import_ib():
    try:
        from ib_insync import IB, LimitOrder, Stock  # type: ignore
    except ImportError as exc:
        raise IbUnavailable("ib_insync is not installed") from exc
    return IB, Stock, LimitOrder


def connect_ib(owner: str, cfg: Mapping[str, Any] | None = None, *, paper: bool = False, readonly: bool = False):
    cfg = cfg or load_config()
    IB, _, _ = _import_ib()
    ibkr = cfg["ibkr"]
    port = int(ibkr["paper_port"] if paper else ibkr["live_port"])
    ids = ibkr.get("client_ids") or {}
    client_id = int(ids.get(owner) or ids.get("sync") or 73)
    ib = IB()
    ib.connect(str(ibkr.get("host") or "127.0.0.1"), port, clientId=client_id, readonly=readonly, timeout=15)
    if readonly:
        try:
            ib.reqMarketDataType(3)
        except Exception:
            pass
    account = str(ibkr.get("account_id") or "").strip()
    if not account:
        ib.disconnect()
        raise PermissionError("ibkr.account_id is required (same pin as ls-algo / SPX 0DTE)")
    managed = [str(a).strip() for a in (ib.managedAccounts() or []) if str(a).strip()]
    if account not in managed:
        ib.disconnect()
        raise PermissionError(f"TWS is not on {account}; managed={managed}")
    return ib


def qualify_and_quote(ib: Any, ticker: str) -> dict[str, Any]:
    _, Stock, _ = _import_ib()
    ticker_n = norm_sym(ticker)
    contract = Stock(ticker_n, "SMART", "USD")
    qualified = ib.qualifyContracts(contract)
    if not qualified:
        raise ValueError(f"IB could not qualify {ticker_n}")
    contract = qualified[0]
    ticker_data = ib.reqMktData(contract, "", False, False)
    ib.sleep(1.5)
    last = ticker_data.last if ticker_data.last == ticker_data.last else None
    if last is None or last <= 0:
        last = ticker_data.close if ticker_data.close == ticker_data.close else None
    bid = ticker_data.bid if ticker_data.bid == ticker_data.bid else None
    ask = ticker_data.ask if ticker_data.ask == ticker_data.ask else None
    ib.cancelMktData(contract)
    if last is None or last <= 0:
        raise ValueError(f"no last price for {ticker_n}")
    return {
        "ticker": ticker_n,
        "qualified_name": getattr(contract, "localSymbol", None) or getattr(contract, "symbol", ticker_n),
        "conId": int(getattr(contract, "conId", 0) or 0),
        "exchange": str(getattr(contract, "exchange", "SMART") or "SMART"),
        "currency": str(getattr(contract, "currency", "USD") or "USD"),
        "secType": str(getattr(contract, "secType", "STK") or "STK"),
        "last": float(last),
        "bid": float(bid) if bid and bid == bid and bid > 0 else None,
        "ask": float(ask) if ask and ask == ask and ask > 0 else None,
        "as_of": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "contract": contract,
    }


def fetch_positions(ib: Any, account_id: str) -> list[dict[str, Any]]:
    """Account-pinned snapshot. Prefer reqPositionsMulti so sibling accounts stay quiet."""
    account = str(account_id or "").strip()
    if account:
        try:
            ib.reqAccountUpdates(True, account)
            deadline = time.time() + 8
            while time.time() < deadline:
                ib.sleep(0.4)
                try:
                    preview = list(ib.portfolio(account) or [])
                except TypeError:
                    preview = list(ib.portfolio() or [])
                if preview:
                    break
        except Exception:
            pass

    raw_positions = []
    if account and hasattr(ib, "reqPositionsMulti"):
        try:
            raw_positions = list(ib.reqPositionsMulti(account) or [])
        except Exception:
            raw_positions = []
    if not raw_positions:
        ib.reqPositions()
        ib.sleep(1.0)
        raw_positions = list(ib.positions(account) if account else ib.positions())

    fx = {"USD": 1.0}
    try:
        for av in ib.accountValues(account) if account else ib.accountValues():
            if str(getattr(av, "tag", "")) == "ExchangeRate" and getattr(av, "currency", None):
                try:
                    fx[str(av.currency)] = float(av.value)
                except (TypeError, ValueError):
                    continue
    except Exception:
        pass

    marks: dict[int, dict[str, Any]] = {}
    try:
        portfolio = list(ib.portfolio(account) if account else ib.portfolio())
    except TypeError:
        portfolio = list(ib.portfolio())
    for item in portfolio:
        if account and str(getattr(item, "account", "") or "") not in {"", account}:
            continue
        contract = item.contract
        con_id = int(getattr(contract, "conId", 0) or 0)
        marks[con_id] = {
            "mark": float(getattr(item, "marketPrice", 0) or 0),
            "marketValue": float(getattr(item, "marketValue", 0) or 0),
            "avgCost": float(getattr(item, "averageCost", 0) or 0),
            "base": True,
        }

    rows = []
    for pos in raw_positions:
        if account and str(pos.account) != account:
            continue
        qty = float(pos.position)
        if qty == 0:
            continue
        c = pos.contract
        con_id = int(getattr(c, "conId", 0) or 0)
        currency = str(getattr(c, "currency", "") or "USD")
        mark_row = marks.get(con_id) or {}
        avg = float(mark_row.get("avgCost") or getattr(pos, "avgCost", 0) or 0)
        mark = float(mark_row.get("mark") or avg or 0)
        if mark_row.get("base") and mark_row.get("marketValue") is not None:
            mv = float(mark_row.get("marketValue") or 0)
        else:
            mv = qty * mark * float(fx.get(currency) or 1.0)
        local = str(getattr(c, "localSymbol", "") or "")
        symbol = local or str(getattr(c, "symbol", "") or "")
        rows.append({
            "account": pos.account,
            "symbol": symbol,
            "localSymbol": local,
            "secType": getattr(c, "secType", ""),
            "tradingClass": getattr(c, "tradingClass", ""),
            "underlyingSymbol": getattr(c, "symbol", "") if str(getattr(c, "secType", "")).upper() in {"OPT", "FOP"} else "",
            "currency": currency,
            "conId": con_id,
            "qty": qty,
            "avgCost": avg,
            "mark": mark,
            "marketValue": mv,
            "costUsd": abs(qty * avg) * float(fx.get(currency) or 1.0),
            "name": local or str(getattr(c, "symbol", "") or ""),
            "orderRef": "",
        })
    if account:
        try:
            ib.reqAccountUpdates(False, account)
        except Exception:
            pass
    return rows


def submit_limit(ib: Any, proposal: Mapping[str, Any], quote: Mapping[str, Any], cfg: Mapping[str, Any] | None = None) -> int:
    cfg = cfg or load_config()
    if bool((cfg.get("execution") or {}).get("dry_run", True)):
        raise PermissionError("submit_limit refused because dry_run is true")
    if not bool((cfg.get("execution") or {}).get("allow_live", False)):
        raise PermissionError("submit_limit refused because allow_live is false")
    _, Stock, LimitOrder = _import_ib()
    owner = str(proposal["owner"])
    op = operator_config(cfg, owner)
    account = str((cfg.get("ibkr") or {}).get("account_id") or "")
    contract = quote.get("contract")
    if contract is None:
        contract = Stock(proposal["ticker"], quote.get("exchange") or "SMART", "USD")
        ib.qualifyContracts(contract)
    order = LimitOrder(
        proposal["side"],
        float(proposal["qty"]),
        float(proposal["limit_price"]),
        account=account,
        tif="DAY",
        orderRef=str(op["order_ref"]),
        transmit=True,
    )
    trade = ib.placeOrder(contract, order)
    ib.sleep(1.0)
    oid = getattr(trade.order, "orderId", None)
    if oid is None:
        raise RuntimeError("IB did not return an order id")
    return int(oid)
