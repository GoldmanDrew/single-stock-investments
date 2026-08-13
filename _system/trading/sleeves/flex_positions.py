"""Parse an IBKR Flex OpenPositions XML into the same rows as ib_client.fetch_positions."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

ASSET_TO_SEC = {
    "STK": "STK",
    "OPT": "OPT",
    "FOP": "FOP",
    "FUT": "FUT",
    "CASH": "CASH",
    "BILL": "BILL",
    "BOND": "STK",
    "FUND": "STK",
    "WAR": "STK",
}


def parse_flex_positions(path: Path | str, *, account_id: str = "U805366") -> list[dict[str, Any]]:
    root = ET.parse(path).getroot()
    rows: list[dict[str, Any]] = []
    for node in root.iter("OpenPosition"):
        account = (node.attrib.get("accountId") or "").strip()
        if account_id and account and account != account_id:
            continue
        qty = float(node.attrib.get("position") or 0)
        if qty == 0:
            continue
        asset = (node.attrib.get("assetCategory") or "STK").strip().upper()
        fx = float(node.attrib.get("fxRateToBase") or 1) or 1.0
        mark = float(node.attrib.get("markPrice") or 0)
        local_value = float(node.attrib.get("positionValue") or 0)
        cost_local = float(node.attrib.get("costBasisMoney") or 0)
        rows.append({
            "account": account or account_id,
            "symbol": node.attrib.get("symbol") or "",
            "localSymbol": node.attrib.get("symbol") or "",
            "secType": ASSET_TO_SEC.get(asset, asset or "STK"),
            "tradingClass": node.attrib.get("underlyingSymbol") or "",
            "underlyingSymbol": node.attrib.get("underlyingSymbol") or "",
            "currency": node.attrib.get("currency") or "",
            "conId": int(float(node.attrib.get("conid") or 0) or 0),
            "qty": qty,
            "avgCost": float(node.attrib.get("costBasisPrice") or 0),
            "mark": mark,
            "marketValue": local_value * fx,
            "costUsd": cost_local * fx,
            "name": node.attrib.get("description") or node.attrib.get("symbol") or "",
            "orderRef": "",
            "reportDate": node.attrib.get("reportDate") or "",
        })
    return rows
