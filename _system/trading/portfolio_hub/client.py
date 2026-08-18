from __future__ import annotations

from decimal import Decimal
from typing import Any

from .orders import GuardedOrderService, OrderBroker, OrderIntent


class PortfolioClient:
    """Small Python interface for exact-contract limit orders through a private bridge."""

    def __init__(self, service: GuardedOrderService):
        self.service = service

    @classmethod
    def for_broker(cls, ledger, broker: OrderBroker, approval_secret: str, **policy: Any) -> "PortfolioClient":
        return cls(GuardedOrderService(ledger, broker, approval_secret, **policy))

    def draft_limit(self, *, account_alias: str, conid: int, contract_fingerprint: str,
                    action: str, quantity: str | Decimal, limit_price: str | Decimal,
                    owner: str, strategy: str, mode: str = "dry_run",
                    reduce_only: bool | None = None) -> dict[str, Any]:
        return self.service.create(OrderIntent(
            account_alias=account_alias, conid=conid, contract_fingerprint=contract_fingerprint,
            action=action.upper(), quantity=Decimal(quantity), limit_price=Decimal(limit_price),
            owner=owner, strategy=strategy, mode=mode, reduce_only=reduce_only,
        ))

    def preview(self, intent_uuid: str) -> dict[str, Any]:
        return self.service.preview(intent_uuid)

    def issue_approval(self, intent_uuid: str) -> dict[str, str]:
        return self.service.issue_approval(intent_uuid)

    def approve(self, intent_uuid: str, *, token: str, contract_fingerprint: str) -> dict[str, Any]:
        return self.service.approve(intent_uuid, token, contract_fingerprint)

    def submit(self, intent_uuid: str) -> dict[str, Any]:
        return self.service.submit(intent_uuid)
