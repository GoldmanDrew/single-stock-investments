from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _pick(attrs: dict[str, str], *keys: str) -> str | None:
    for key in keys:
        value = attrs.get(key)
        if value not in (None, ""):
            return value
    return None


def _rows(root: ET.Element, tag: str) -> list[dict[str, str]]:
    return [dict(element.attrib) for element in root.iter(tag)]


def parse_flex_xml(xml: bytes | str, *, account_alias: str, source_run_id: str | None = None) -> dict[str, Any]:
    raw = xml.encode() if isinstance(xml, str) else xml
    root = ET.fromstring(raw)
    statements = list(root.iter("FlexStatement"))
    if not statements:
        raise ValueError("Flex payload has no FlexStatement")
    statement = statements[0].attrib
    session_date = _pick(statement, "toDate", "periodEnd", "whenGenerated")
    if not session_date:
        raise ValueError("Flex payload has no completed-session date")
    session_date = session_date[:10].replace("-", "")
    if len(session_date) == 8:
        session_date = f"{session_date[:4]}-{session_date[4:6]}-{session_date[6:]}"
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    positions = []
    for row in _rows(root, "OpenPosition"):
        positions.append({
            "conid": int(_pick(row, "conid", "conId") or 0), "symbol": _pick(row, "symbol", "underlyingSymbol"),
            "asset_category": row.get("assetCategory"), "currency": row.get("currency"), "quantity": _pick(row, "position", "quantity"),
            "cost_basis": _pick(row, "costBasisMoney", "costBasis"), "mark": _pick(row, "markPrice", "closePrice"),
            "market_value": _pick(row, "positionValue", "marketValue"), "unrealized_pnl": _pick(row, "fifoPnlUnrealized", "unrealizedPnl"),
        })
    trades = []
    for row in _rows(root, "Trade"):
        trades.append({
            "trade_id": _pick(row, "tradeID", "tradeId"), "exec_id": _pick(row, "ibExecID", "execID"),
            "conid": int(_pick(row, "conid", "conId") or 0), "symbol": row.get("symbol"), "currency": row.get("currency"),
            "quantity": _pick(row, "quantity", "tradeQuantity"), "price": _pick(row, "tradePrice", "price"),
            "commission": _pick(row, "ibCommission", "commission"), "realized_pnl": _pick(row, "fifoPnlRealized", "realizedPnl"),
            "trade_time": _pick(row, "dateTime", "tradeDate"), "order_ref": _pick(row, "orderReference", "orderRef"),
        })
    cash = []
    for row in _rows(root, "CashTransaction"):
        cash.append({
            "transaction_id": _pick(row, "transactionID", "transactionId"), "type": _pick(row, "type", "levelOfDetail"),
            "currency": row.get("currency"), "amount": row.get("amount"), "date": _pick(row, "dateTime", "settleDate", "reportDate"),
            "symbol": row.get("symbol"), "conid": int(_pick(row, "conid", "conId") or 0) or None,
            "description": row.get("description"),
        })
    nav_rows = [{
        "currency": row.get("currency"), "net_liquidation": _pick(row, "total", "netLiquidation"),
        "cash": _pick(row, "cash", "cashBalance"), "stock": row.get("stock"), "options": row.get("options"),
    } for row in _rows(root, "ChangeInNAV")]
    return {
        "schema_version": "flex_eod.v1", "source_run_id": source_run_id or f"flex-{hashlib.sha256(raw).hexdigest()[:20]}",
        "account_alias": account_alias, "session_date": session_date, "as_of": now,
        "positions": positions, "trades": trades, "cash_transactions": cash, "nav_rows": nav_rows,
    }


def parse_flex_file(path: str | Path, *, account_alias: str) -> dict[str, Any]:
    return parse_flex_xml(Path(path).read_bytes(), account_alias=account_alias)
