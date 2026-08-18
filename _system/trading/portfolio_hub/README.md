# Portfolio hub private runtime

This package is the private read/command core for the IBKR portfolio hub. It is intentionally separate from the hosted dashboard.

- SQLite in WAL mode is the local system of record.
- Every broker snapshot is versioned and business-idempotent.
- Positions reconcile at `account_alias + conId + model_code` and a complete snapshot watermark.
- Owner/strategy allocations are independent virtual lots; gaps are visible reconciliation breaks.
- State changes and their publish events commit in one transaction through the outbox.
- Orders default to dry-run/paper, require an exact qualified contract fingerprint, and never blindly retry an uncertain transmission.

Runtime account identity comes from `IBKR_ACCOUNT_ID` and `IBKR_ACCOUNT_ALIAS`; it is not stored in source. The live collector uses the maintained `ib_async` package. The order broker adapter remains disabled until the client-ID/master-client ADR, SPX/LS positive `orderRef` migration, and paper scenario gates are complete.

The order interface is deliberately exact-contract and multi-step:

```python
from _system.trading.portfolio_hub import PortfolioClient, PortfolioLedger
from _system.trading.portfolio_hub.paper import PaperOrderBroker

ledger = PortfolioLedger("_private/portfolio-hub/portfolio.db")
ledger.migrate()
private_bridge = PaperOrderBroker(lambda conid: {
    "conid": conid, "bid": "25.39", "ask": "25.41", "current_position": "0",
})
client = PortfolioClient.for_broker(ledger, private_bridge, approval_secret="replace-with-runtime-secret", live_enabled=False)
draft = client.draft_limit(
    account_alias="paper-primary",
    conid=123456789,
    contract_fingerprint="123456789|STK|USD|SMART",
    action="BUY",
    quantity="10",
    limit_price="25.40",
    owner="drew",
    strategy="single_stock",
    mode="paper",
)
preview = client.preview(draft["intent_uuid"])
approval = client.issue_approval(draft["intent_uuid"])
client.approve(draft["intent_uuid"], token=approval["token"], contract_fingerprint=approval["contract_fingerprint"])
submitted = client.submit(draft["intent_uuid"])
```

The `private_bridge` implements the `OrderBroker` protocol. It must be the one long-lived bridge described in `CLIENT_ID_REGISTRY.md`; direct browser submission is not supported.

Run tests from the repository root:

```powershell
python -m pytest -q _system/trading/portfolio_hub/tests
```
