from __future__ import annotations

import os
import asyncio
import math
import uuid
from dataclasses import dataclass
from typing import Any, Protocol


REQUIRED_ACCOUNT_TAGS = (
    "NetLiquidation", "GrossPositionValue", "BuyingPower", "InitMarginReq",
    "MaintMarginReq", "AvailableFunds", "ExcessLiquidity", "SMA", "Cushion",
    "TotalCashValue", "SettledCash", "UnrealizedPnL", "RealizedPnL", "Leverage-S",
    "LookAheadInitMarginReq", "LookAheadMaintMarginReq", "LookAheadAvailableFunds", "LookAheadExcessLiquidity",
)


class SnapshotSink(Protocol):
    def ingest_account_snapshot(self, payload: dict[str, Any]) -> str: ...


@dataclass(frozen=True)
class BrokerProfile:
    host: str
    port: int
    client_id: int
    account_alias: str
    account_id: str
    readonly: bool = True

    @classmethod
    def from_env(cls) -> "BrokerProfile":
        account_id = os.environ.get("IBKR_ACCOUNT_ID", "")
        account_alias = os.environ.get("IBKR_ACCOUNT_ALIAS", "")
        if not account_id or not account_alias:
            raise RuntimeError("IBKR_ACCOUNT_ID and IBKR_ACCOUNT_ALIAS are required")
        return cls(
            host=os.environ.get("IBKR_HOST", "127.0.0.1"),
            port=int(os.environ.get("IBKR_PORT", "4002")),
            client_id=int(os.environ.get("IBKR_COLLECTOR_CLIENT_ID", "81")),
            account_alias=account_alias,
            account_id=account_id,
            readonly=True,
        )


class IBAsyncCollector:
    """Read-only collector adapter. Import is delayed so fixtures need no IB dependency."""

    def __init__(self, profile: BrokerProfile):
        self.profile = profile

    async def collect(self) -> dict[str, Any]:
        try:
            from ib_async import IB
        except ImportError as exc:
            raise RuntimeError("install ib_async to use the live collector") from exc
        ib = IB()
        await ib.connectAsync(self.profile.host, self.profile.port, clientId=self.profile.client_id, readonly=True, account=self.profile.account_id)
        try:
            accounts = set(ib.managedAccounts())
            if self.profile.account_id not in accounts:
                raise RuntimeError("configured IBKR account is not visible to this session")
            summaries = await ib.accountSummaryAsync(self.profile.account_id)
            positions = await ib.reqPositionsAsync()
            trades = await ib.reqAllOpenOrdersAsync()
            model_by_conid = {row.contract.conId: getattr(row, "modelCode", None) or getattr(row, "model", "") or "" for row in positions if row.account == self.profile.account_id}
            portfolio_rows = [row for row in ib.portfolio(self.profile.account_id) if row.account == self.profile.account_id]
            now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
            tags = [row for row in summaries if row.tag in REQUIRED_ACCOUNT_TAGS]
            base_currency = next((row.currency for row in tags if row.tag == "NetLiquidation" and row.currency), "USD")
            pnl_values = []
            pnl_complete = False
            try:
                pnl = ib.reqPnL(self.profile.account_id, "")
                await asyncio.sleep(0.5)
                for tag, value in (("DailyPnL", pnl.dailyPnL), ("UnrealizedPnL", pnl.unrealizedPnL), ("RealizedPnL", pnl.realizedPnL)):
                    if value is not None and math.isfinite(float(value)):
                        pnl_values.append({"tag": tag, "value": str(value), "currency": base_currency, "segment": None, "model_code": None, "source": "ibkr_pnl", "as_of": now})
                pnl_complete = any(row["tag"] == "DailyPnL" for row in pnl_values)
            except Exception:
                pnl_complete = False
            finally:
                try:
                    ib.cancelPnL(self.profile.account_id, "")
                except Exception:
                    pass
            return {
                "schema_version": "account_snapshot.v1", "source_run_id": str(uuid.uuid4()),
                "account_alias": self.profile.account_alias, "gateway_session_id": str(uuid.uuid4()),
                "as_of": now, "complete": True, "base_currency": base_currency,
                "completeness": {"positions": True, "account_summary": True, "open_orders": True, "pnl": pnl_complete},
                "account_values": [
                    {"tag": row.tag, "value": row.value, "currency": row.currency or "", "segment": None, "model_code": None, "source": "ibkr_account_summary", "as_of": now}
                    for row in tags
                ] + pnl_values,
                "positions": [self._portfolio_position(row, model_by_conid.get(row.contract.conId, ""), now) for row in portfolio_rows]
                if portfolio_rows else [self._position(row, now) for row in positions if row.account == self.profile.account_id],
                "open_orders": [self._open_order(trade, now) for trade in trades if getattr(trade.order, "account", "") == self.profile.account_id],
            }
        finally:
            ib.disconnect()

    def _position(self, row: Any, as_of: str) -> dict[str, Any]:
        c = row.contract
        if not getattr(c, "conId", 0):
            raise RuntimeError("IBKR returned an unqualified position")
        return {
            "account_alias": self.profile.account_alias, "conid": c.conId, "model_code": getattr(row, "modelCode", None) or getattr(row, "model", "") or "",
            "symbol": c.symbol, "local_symbol": c.localSymbol or None, "description": None,
            "sec_type": c.secType, "currency": c.currency, "exchange": c.exchange or c.primaryExchange or None,
            "expiry": getattr(c, "lastTradeDateOrContractMonth", None) or None,
            "strike": str(c.strike) if getattr(c, "strike", 0) else None, "right": getattr(c, "right", None) or None,
            "multiplier": getattr(c, "multiplier", None) or None, "quantity": str(row.position),
            "average_cost": str(row.avgCost), "mark": None, "market_value": None, "unrealized_pnl": None,
            "realized_pnl": None, "daily_pnl": None, "source": "ibkr_live", "as_of": as_of, "quality": "unknown",
        }

    def _portfolio_position(self, row: Any, model_code: str, as_of: str) -> dict[str, Any]:
        result = self._position(type("PositionRow", (), {"contract": row.contract, "account": row.account, "modelCode": model_code, "position": row.position, "avgCost": row.averageCost})(), as_of)
        result.update({
            "mark": str(row.marketPrice), "market_value": str(row.marketValue),
            "unrealized_pnl": str(row.unrealizedPNL), "realized_pnl": str(row.realizedPNL),
            "quality": "live",
        })
        return result

    @staticmethod
    def _open_order(trade: Any, as_of: str) -> dict[str, Any]:
        order, contract = trade.order, trade.contract
        order_ref = getattr(order, "orderRef", "") or ""
        return {
            "client_id": getattr(order, "clientId", None), "order_id": order.orderId,
            "perm_id": getattr(order, "permId", None), "conid": getattr(contract, "conId", None),
            "symbol": getattr(contract, "localSymbol", None) or getattr(contract, "symbol", None),
            "action": order.action, "order_type": order.orderType, "total_quantity": str(order.totalQuantity),
            "limit_price": str(order.lmtPrice) if order.orderType == "LMT" else None, "tif": order.tif,
            "status": getattr(trade.orderStatus, "status", None), "order_ref": order_ref,
            "ownership": "hub" if order_ref.startswith("MAGIS|") else "foreign",
            "parent_id": getattr(order, "parentId", None), "oca_group": getattr(order, "ocaGroup", None) or None,
            "as_of": as_of,
        }
