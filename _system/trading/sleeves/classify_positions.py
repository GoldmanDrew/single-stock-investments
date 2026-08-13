"""Classify IB positions into Michael / Drew / systematic LETF / SPX 0DTE."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping

CASH_SEC_TYPES = {"CASH", "BILL"}
CASH_SYMBOLS = {"USD", "EUR", "GBP", "CAD", "JPY", "BIL", "SGOV", "SHV", "TBIL", "TFLO", "VMFXX"}
SPX_NAMES = {"SPX", "SPXW", "XSP"}
ETF_LS_REFS = ("ETF_LS", "B5P")
DREW_REF = "DREW_SLEEVE"
MICHAEL_REF = "MICHAEL_SLEEVE"


def norm_sym(symbol: str) -> str:
    s = str(symbol or "").strip().upper()
    if s == "BRK.B":
        return "BRK-B"
    if s == "BRK B":
        return "BRK-B"
    return s.replace(" ", "-")


def expand_blacklist_symbols(
    blacklist: Iterable[str],
    etf_to_under: Mapping[str, str],
) -> set[str]:
    """Underlying on the list pulls every mapped ETF; ETF on the list pulls siblings."""
    bl = {norm_sym(s) for s in blacklist if str(s).strip()}
    blocked: set[str] = set(bl)
    for etf, under in (etf_to_under or {}).items():
        e, u = norm_sym(etf), norm_sym(under)
        if e and u and e in bl:
            blocked.add(u)
    blocked_unders = set(blocked)
    for etf, under in (etf_to_under or {}).items():
        e, u = norm_sym(etf), norm_sym(under)
        if not e or not u:
            continue
        if e in bl or u in bl or u in blocked_unders:
            blocked.add(e)
            blocked.add(u)
    return blocked


@dataclass(frozen=True)
class Classification:
    ticker: str
    bucket: str  # michael | drew | etf_ls | spx_0dte | ignored
    reason: str
    owner: str | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _order_ref(pos: Mapping[str, Any]) -> str:
    return str(pos.get("orderRef") or pos.get("order_ref") or "").strip().upper()


def _sec_type(pos: Mapping[str, Any]) -> str:
    return str(pos.get("secType") or pos.get("sec_type") or "STK").strip().upper()


def _trading_class(pos: Mapping[str, Any]) -> str:
    return str(pos.get("tradingClass") or pos.get("trading_class") or "").strip().upper()


def classify_position(
    pos: Mapping[str, Any],
    *,
    blacklist_family: Iterable[str],
    etf_ls_symbols: Iterable[str],
    drew_symbols: Iterable[str] | None = None,
) -> Classification:
    under = norm_sym(pos.get("underlyingSymbol") or pos.get("underlying") or "")
    ticker = norm_sym(pos.get("symbol") or pos.get("ticker") or pos.get("localSymbol") or "")
    sec = _sec_type(pos)
    tclass = _trading_class(pos)
    ref = _order_ref(pos)
    family = {norm_sym(s) for s in blacklist_family}
    letf = {norm_sym(s) for s in etf_ls_symbols}
    drew = {norm_sym(s) for s in (drew_symbols or [])}
    index_name = under or ticker or tclass

    if sec in {"OPT", "FOP"}:
        local = str(pos.get("localSymbol") or pos.get("symbol") or "").upper()
        if index_name in SPX_NAMES or "SPXW" in local or local.startswith("XSP"):
            return Classification(index_name or "SPX", "spx_0dte", "spxw_option", None)

    if DREW_REF in ref or ticker in drew:
        return Classification(ticker, "drew", "drew_new", "drew")

    if ticker in family:
        return Classification(ticker, "michael", "blacklist_family", "michael")

    if sec in {"OPT", "FOP"}:
        name = under or ticker
        if name in family:
            return Classification(name, "michael", "blacklist_family", "michael")
        if name in letf:
            return Classification(name, "etf_ls", "etf_ls_universe", None)
        if MICHAEL_REF in ref:
            return Classification(name or ticker, "michael", "michael_new", "michael")
        if name:
            return Classification(name, "michael", "residual", "michael")
        return Classification(ticker, "ignored", "option_not_stock", None)

    if any(tag in ref for tag in ETF_LS_REFS):
        return Classification(ticker, "etf_ls", "order_ref", None)

    if ticker in letf:
        return Classification(ticker, "etf_ls", "etf_ls_universe", None)

    if MICHAEL_REF in ref:
        return Classification(ticker, "michael", "michael_new", "michael")

    if sec in CASH_SEC_TYPES or ticker in CASH_SYMBOLS:
        return Classification(ticker, "michael", "cash", "michael")

    if not ticker:
        return Classification("", "ignored", "missing_symbol", None)

    return Classification(ticker, "michael", "residual", "michael")


def classify_positions(
    positions: Iterable[Mapping[str, Any]],
    *,
    blacklist_family: Iterable[str],
    etf_ls_symbols: Iterable[str],
    drew_symbols: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    out = []
    for pos in positions:
        row = dict(pos)
        cls = classify_position(
            pos,
            blacklist_family=blacklist_family,
            etf_ls_symbols=etf_ls_symbols,
            drew_symbols=drew_symbols,
        )
        row["classification"] = cls.as_dict()
        out.append(row)
    return out
