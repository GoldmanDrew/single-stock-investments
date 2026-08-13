"""IB connection, qualify, snapshot, limit order. Fail closed without ib_insync."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping
import time

from .classify_positions import norm_sym
from .config_loader import load_config, operator_config
from .contracts import contract_spec, quote_px, spec_from_mapping


class IbUnavailable(RuntimeError):
    pass


def _import_ib():
    try:
        from ib_insync import IB, LimitOrder, Option, Stock  # type: ignore
    except ImportError as exc:
        raise IbUnavailable("ib_insync is not installed") from exc
    return IB, Stock, Option, LimitOrder


def connect_ib(owner: str, cfg: Mapping[str, Any] | None = None, *, paper: bool = False, readonly: bool = False):
    cfg = cfg or load_config()
    IB, _, _, _ = _import_ib()
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


def _finite_tick(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number <= 0:
        return None
    return number


def _make_ib_contract(spec: Mapping[str, Any]):
    _, Stock, Option, _ = _import_ib()
    if spec["sec_type"] == "OPT":
        if spec.get("local_symbol"):
            contract = Option()
            contract.localSymbol = spec["local_symbol"]
            contract.secType = "OPT"
            contract.exchange = spec.get("exchange") or "SMART"
            contract.currency = spec.get("currency") or "USD"
            contract.multiplier = str(int(spec.get("multiplier") or 100))
            return [contract]
        return [Option(
            spec["underlying"],
            spec["expiry"],
            float(spec["strike"]),
            spec["right"],
            spec.get("exchange") or "SMART",
            spec.get("currency") or "USD",
            str(int(spec.get("multiplier") or 100)),
        )]
    symbol = spec["ticker"]
    currency = str(spec.get("currency") or "").upper()
    exchange = spec.get("exchange") or "SMART"
    if currency and currency != "USD":
        return [Stock(symbol, exchange, currency), Stock(symbol, exchange, "USD")]
    return [Stock(symbol, exchange, "USD"), Stock(symbol, exchange, "CAD")]


def qualify_and_quote(ib: Any, ticker: str | Mapping[str, Any], **fields: Any) -> dict[str, Any]:
    """Live IB quote for a stock or option. `ticker` may be a symbol or a contract spec."""
    if isinstance(ticker, Mapping):
        spec = spec_from_mapping({**dict(ticker), **fields})
    else:
        spec = contract_spec(ticker, **fields)
    candidates = _make_ib_contract(spec)
    contract = None
    for candidate in candidates:
        qualified = ib.qualifyContracts(candidate)
        if qualified:
            contract = qualified[0]
            break
    if contract is None:
        raise ValueError(f"IB could not qualify {spec.get('ticker')}")
    try:
        ib.reqMarketDataType(1)
    except Exception:
        pass
    ticker_data = ib.reqMktData(contract, "", False, False)
    ib.sleep(1.2)
    last = _finite_tick(getattr(ticker_data, "last", None)) or _finite_tick(getattr(ticker_data, "close", None))
    bid = _finite_tick(getattr(ticker_data, "bid", None))
    ask = _finite_tick(getattr(ticker_data, "ask", None))
    if last is None and bid is None and ask is None:
        try:
            ib.reqMarketDataType(3)
            ib.sleep(1.2)
            last = _finite_tick(getattr(ticker_data, "last", None)) or _finite_tick(getattr(ticker_data, "close", None))
            bid = _finite_tick(getattr(ticker_data, "bid", None))
            ask = _finite_tick(getattr(ticker_data, "ask", None))
        except Exception:
            pass
    ib.cancelMktData(contract)
    px = quote_px({"last": last, "bid": bid, "ask": ask})
    if px is None:
        raise ValueError(f"no live price for {spec.get('ticker')}")
    local = str(getattr(contract, "localSymbol", "") or "") or spec.get("local_symbol")
    under = str(getattr(contract, "symbol", "") or "") or spec.get("underlying")
    sec = str(getattr(contract, "secType", "") or spec["sec_type"] or "STK").upper()
    display = local if sec == "OPT" and local else norm_sym(under or spec["ticker"])
    return {
        "ticker": display,
        "qualified_name": display,
        "underlying": norm_sym(under or spec.get("underlying") or display),
        "conId": int(getattr(contract, "conId", 0) or 0),
        "exchange": str(getattr(contract, "exchange", spec.get("exchange") or "SMART") or "SMART"),
        "currency": str(getattr(contract, "currency", spec.get("currency") or "USD") or "USD"),
        "secType": sec,
        "sec_type": sec,
        "expiry": str(getattr(contract, "lastTradeDateOrContractMonth", "") or spec.get("expiry") or "") or None,
        "strike": _finite_tick(getattr(contract, "strike", None)) or spec.get("strike"),
        "right": str(getattr(contract, "right", "") or spec.get("right") or "") or None,
        "local_symbol": local or None,
        "multiplier": float(getattr(contract, "multiplier", None) or spec.get("multiplier") or (100 if sec == "OPT" else 1)),
        "last": float(px),
        "bid": float(bid) if bid else None,
        "ask": float(ask) if ask else None,
        "as_of": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "account": str((load_config().get("ibkr") or {}).get("account_id") or ""),
        "mock": False,
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
    _, _, _, LimitOrder = _import_ib()
    owner = str(proposal["owner"])
    op = operator_config(cfg, owner)
    account = str((cfg.get("ibkr") or {}).get("account_id") or "")
    contract = quote.get("contract")
    if contract is None:
        spec = spec_from_mapping({**dict(proposal), **dict(quote)})
        qualified = None
        for candidate in _make_ib_contract(spec):
            found = ib.qualifyContracts(candidate)
            if found:
                qualified = found[0]
                break
        if qualified is None:
            raise ValueError(f"IB could not qualify {spec.get('ticker')}")
        contract = qualified
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


def refresh_quote(owner: str, spec: str | Mapping[str, Any], cfg: Mapping[str, Any] | None = None, *, readonly: bool = True) -> dict[str, Any]:
    """Pull a live bid/ask/last from Gateway. Uses the sync client when readonly."""
    cfg = cfg or load_config()
    ib = connect_ib("sync" if readonly else owner, cfg, readonly=readonly)
    try:
        return qualify_and_quote(ib, spec)
    finally:
        ib.disconnect()


def gateway_submit(proposal: Mapping[str, Any], quote: Mapping[str, Any], cfg: Mapping[str, Any] | None = None) -> int:
    cfg = cfg or load_config()
    ib = connect_ib(str(proposal["owner"]), cfg, readonly=False)
    try:
        live = dict(quote)
        if live.get("contract") is None:
            live = qualify_and_quote(ib, {**dict(proposal), **dict(quote)})
        return submit_limit(ib, proposal, live, cfg)
    finally:
        ib.disconnect()
