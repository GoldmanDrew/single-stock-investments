from __future__ import annotations

import os
import asyncio
import math
import uuid
from dataclasses import dataclass
from decimal import Decimal
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
            # IBKR publishes the rate it is itself using, per currency, as an
            # ExchangeRate row in the account-update stream. Reading it is a cache
            # lookup -- connectAsync(account=...) already subscribed -- so this
            # costs no request and no market-data line.
            #
            # It replaces deriving the rate from marketValue / (position x price).
            # That ratio only carries FX information if marketValue really is in
            # base; on this account it comes back in the *contract* currency, so
            # the ratio was always ~1 and every foreign position was published at
            # its native magnitude. See _fx_translation.
            exchange_rates = self._exchange_rates(ib)
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
                "positions": [self._portfolio_position(row, model_by_conid.get(row.contract.conId, ""), now, base_currency, exchange_rates) for row in portfolio_rows]
                if portfolio_rows else [self._position(row, now, base_currency) for row in positions if row.account == self.profile.account_id],
                "open_orders": [self._open_order(trade, now) for trade in trades if getattr(trade.order, "account", "") == self.profile.account_id],
            }
        finally:
            ib.disconnect()

    def _position(self, row: Any, as_of: str, base_currency: str | None = None) -> dict[str, Any]:
        c = row.contract
        if not getattr(c, "conId", 0):
            raise RuntimeError("IBKR returned an unqualified position")
        quantity_unit = "contracts" if str(c.secType).upper() in {"OPT", "FOP"} else "shares"
        return {
            "account_alias": self.profile.account_alias, "conid": c.conId, "model_code": getattr(row, "modelCode", None) or getattr(row, "model", "") or "",
            "symbol": c.symbol, "local_symbol": c.localSymbol or None, "description": None,
            "sec_type": c.secType, "currency": c.currency, "native_currency": c.currency,
            "base_currency": base_currency or c.currency, "quantity_unit": quantity_unit,
            "exchange": c.exchange or c.primaryExchange or None,
            "expiry": getattr(c, "lastTradeDateOrContractMonth", None) or None,
            "strike": str(c.strike) if getattr(c, "strike", 0) else None, "right": getattr(c, "right", None) or None,
            "multiplier": getattr(c, "multiplier", None) or None, "quantity": str(row.position),
            "average_cost": str(row.avgCost), "average_cost_native": str(row.avgCost),
            "mark": None, "mark_native": None, "market_value": None, "market_value_native": None,
            "market_value_base": None, "fx_rate_to_base": None, "fx_as_of": None, "fx_source": None,
            "unrealized_pnl": None, "unrealized_pnl_base": None,
            "realized_pnl": None, "daily_pnl": None, "source": "ibkr_live", "as_of": as_of, "quality": "unknown",
        }

    def _portfolio_position(self, row: Any, model_code: str, as_of: str, base_currency: str,
                            exchange_rates: dict[str, Decimal] | None = None) -> dict[str, Any]:
        result = self._position(type("PositionRow", (), {"contract": row.contract, "account": row.account, "modelCode": model_code, "position": row.position, "avgCost": row.averageCost})(), as_of, base_currency)
        multiplier = Decimal(str(getattr(row.contract, "multiplier", None) or 1))
        native_value = Decimal(str(row.position)) * Decimal(str(row.marketPrice)) * multiplier
        reported_value = Decimal(str(row.marketValue))
        fx_rate, fx_source = self._fx_translation(
            row.contract.currency, base_currency, native_value, reported_value, exchange_rates,
        )
        # Translate, rather than reusing the reported number as if it were base.
        #
        # `market_value_base` used to be str(row.marketValue) unconditionally --
        # the same figure as native, in the contract currency, relabelled. That is
        # what put 3,000 shares of a Tokyo listing at the top of a book sorted by
        # market value in USD: JPY 4,956,299 rendered and sorted as $4,956,299
        # when it is about $34,000.
        translated = self._translate(native_value, fx_rate)
        unrealized = Decimal(str(row.unrealizedPNL))
        realized = Decimal(str(row.realizedPNL))
        result.update({
            "base_currency": base_currency,
            "mark": str(row.marketPrice), "mark_native": str(row.marketPrice),
            "market_value": str(row.marketValue), "market_value_native": str(native_value),
            # An untranslatable row still has to publish *some* decimal here to
            # satisfy the account_snapshot.v1 contract, so it publishes the native
            # figure with fx_source=fx_unavailable and quality=estimated beside it.
            # Every consumer is required to check the source before using this.
            "market_value_base": str(translated if translated is not None else reported_value),
            "fx_rate_to_base": str(fx_rate) if fx_rate is not None else None,
            "fx_as_of": as_of, "fx_source": fx_source,
            "unrealized_pnl": str(unrealized),
            "unrealized_pnl_base": str(self._translate(unrealized, fx_rate) or unrealized),
            "realized_pnl": str(realized),
            "realized_pnl_base": str(self._translate(realized, fx_rate) or realized),
            # An untranslatable non-base row is published and flagged, never dropped and never
            # silently mixed into base totals. Only a flat row stays "live" without a rate.
            "quality": "estimated" if fx_source == "fx_unavailable" and Decimal(str(row.position)) else "live",
        })
        return result

    @staticmethod
    def _exchange_rates(ib: Any) -> dict[str, Decimal]:
        """IBKR's own native->base rate per currency, from the account-update cache."""
        rates: dict[str, Decimal] = {}
        try:
            values = ib.accountValues(ib.managedAccounts()[0]) or []
        except Exception:  # pragma: no cover - defensive; a missing cache is not fatal
            return rates
        for value in values:
            if getattr(value, "tag", "") != "ExchangeRate":
                continue
            currency = str(getattr(value, "currency", "") or "").upper()
            try:
                rate = Decimal(str(value.value))
            except (ArithmeticError, TypeError, ValueError):
                continue
            if currency and rate > 0:
                rates[currency] = rate
        return rates

    @staticmethod
    def _translate(value: Decimal, rate: Decimal | None) -> Decimal | None:
        return None if rate is None else value * rate

    @staticmethod
    def _fx_translation(native_currency: str, base_currency: str, native_value: Decimal,
                        reported_value: Decimal,
                        exchange_rates: dict[str, Decimal] | None = None) -> tuple[Decimal | None, str]:
        """The native->base rate, preferring the one IBKR states over one we infer.

        Ask, then infer, then admit you cannot.
        """
        if native_currency == base_currency:
            return Decimal(1), "identity"

        # Asked. IBKR's ExchangeRate row is the rate IBKR itself applies, so it
        # needs no sanity test and stays correct for pairs that legitimately sit
        # near 1.0 -- EUR and CHF have both traded there.
        stated = (exchange_rates or {}).get(str(native_currency).upper())
        if stated and stated > 0:
            return stated, "ibkr_exchange_rate"

        # Inferred, and only when the inference can carry information.
        #
        # The ratio marketValue / (position x price) is an FX rate only if
        # marketValue is in base. When IBKR returns it in the contract currency
        # the ratio is 1 plus float noise -- marketValue is rounded to 2dp while
        # the product is full precision -- so it is never *exactly* 1 and an
        # `== 1` test never fires. Observed on this account: JPY at
        # 1.000000000645, CAD at 0.999999996454, both published as real
        # translations. A tolerance is what that guard always needed.
        #
        # Rejecting a genuine pair that happens to sit within 0.01% of parity
        # costs an `fx_unavailable` flag on that row, which the UI already
        # refuses to use. Accepting a false one silently misstates the position
        # by orders of magnitude. The asymmetry decides the direction.
        if native_value:
            rate = reported_value / native_value
            if abs(rate - Decimal(1)) < Decimal("0.0001"):
                return None, "fx_unavailable"
            return rate, "ibkr_portfolio_translation"
        return None, "fx_unavailable"

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
