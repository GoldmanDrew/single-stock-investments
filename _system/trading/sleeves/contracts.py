"""Stock / option contract specs. No IB import — used by quote, propose, and send."""

from __future__ import annotations

import re
from typing import Any, Mapping

from .classify_positions import norm_sym

OCC_LOCAL = re.compile(
    r"^([A-Z][A-Z0-9.\-]{0,5})\s+(\d{6})([CP])(\d{8})$",
    re.I,
)


def normalize_expiry(raw: str) -> str:
    text = str(raw or "").strip()
    digits = re.sub(r"\D", "", text)
    if len(digits) == 8:
        return digits
    raise ValueError("expiry must be YYYY-MM-DD or YYYYMMDD")


def normalize_right(raw: str) -> str:
    text = str(raw or "").strip().upper()
    if text in {"C", "CALL"}:
        return "C"
    if text in {"P", "PUT"}:
        return "P"
    raise ValueError("right must be C/CALL or P/PUT")


def parse_occ_local(local_symbol: str) -> dict[str, Any] | None:
    match = OCC_LOCAL.match(str(local_symbol or "").strip().upper().replace(".", ""))
    if not match:
        compact = re.sub(r"\s+", "", str(local_symbol or "").upper())
        match = re.match(r"^([A-Z][A-Z0-9.\-]{0,5})(\d{6})([CP])(\d{8})$", compact)
    if not match:
        return None
    under, yymmdd, right, strike_raw = match.groups()
    year = int(yymmdd[:2])
    expiry = f"{2000 + year}{yymmdd[2:]}"
    strike = int(strike_raw) / 1000.0
    return {
        "underlying": norm_sym(under),
        "expiry": expiry,
        "right": right,
        "strike": strike,
        "local_symbol": str(local_symbol).strip().upper(),
    }


def contract_spec(
    ticker: str | None = None,
    *,
    sec_type: str = "STK",
    underlying: str | None = None,
    expiry: str | None = None,
    strike: float | None = None,
    right: str | None = None,
    local_symbol: str | None = None,
    currency: str | None = None,
    exchange: str | None = None,
    multiplier: float | None = None,
    con_id: int | None = None,
) -> dict[str, Any]:
    sec = str(sec_type or "STK").strip().upper()
    if sec in {"OPTION", "OPTIONS"}:
        sec = "OPT"
    if sec not in {"STK", "OPT"}:
        raise ValueError("sec_type must be STK or OPT")
    occ = parse_occ_local(local_symbol or ticker or "") if sec == "OPT" else None
    under = norm_sym(underlying or (occ or {}).get("underlying") or (ticker if sec == "STK" else "") or "")
    if sec == "STK":
        if not under:
            raise ValueError("ticker required")
        return {
            "sec_type": "STK",
            "ticker": under,
            "underlying": under,
            "expiry": None,
            "strike": None,
            "right": None,
            "local_symbol": None,
            "currency": (currency or "USD").upper(),
            "exchange": exchange or "SMART",
            "multiplier": 1.0,
            "con_id": int(con_id or 0) or None,
        }
    exp = normalize_expiry(expiry or (occ or {}).get("expiry") or "")
    put_call = normalize_right(right or (occ or {}).get("right") or "")
    strike_n = float(strike if strike is not None else (occ or {}).get("strike") or 0)
    if strike_n <= 0:
        raise ValueError("option strike must be positive")
    if not under:
        raise ValueError("option underlying required")
    local = str(local_symbol or (occ or {}).get("local_symbol") or "").strip().upper() or None
    display = local or f"{under} {exp}{put_call}{strike_n:g}"
    return {
        "sec_type": "OPT",
        "ticker": display,
        "underlying": under,
        "expiry": exp,
        "strike": strike_n,
        "right": put_call,
        "local_symbol": local,
        "currency": (currency or "USD").upper(),
        "exchange": exchange or "SMART",
        "multiplier": float(multiplier or 100),
        "con_id": int(con_id or 0) or None,
    }


def spec_from_mapping(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    row = dict(payload or {})
    return contract_spec(
        ticker=row.get("ticker") or row.get("symbol"),
        sec_type=str(row.get("sec_type") or row.get("secType") or "STK"),
        underlying=row.get("underlying") or row.get("underlyingSymbol"),
        expiry=row.get("expiry") or row.get("lastTradeDateOrContractMonth"),
        strike=row.get("strike"),
        right=row.get("right"),
        local_symbol=row.get("local_symbol") or row.get("localSymbol"),
        currency=row.get("currency"),
        exchange=row.get("exchange"),
        multiplier=row.get("multiplier"),
        con_id=row.get("con_id") or row.get("conId"),
    )


def quote_px(quote: Mapping[str, Any]) -> float | None:
    """Last, else bid/ask mid, else bid or ask. Options often have no last."""
    for key in ("last", "price"):
        try:
            value = float(quote.get(key))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            value = None
        if value and value == value and value > 0:
            return value
    bid = ask = 0.0
    try:
        bid = float(quote.get("bid"))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        bid = 0.0
    try:
        ask = float(quote.get("ask"))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        ask = 0.0
    if bid > 0 and ask > 0:
        return (bid + ask) / 2.0
    if ask > 0:
        return ask
    if bid > 0:
        return bid
    return None
