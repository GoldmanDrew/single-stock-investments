# IBKR Portfolio Hub implementation status

Date: 2026-08-17

## Implemented in this repository

- Portfolio / All / Drew / Michael navigation, full positions grid, Risk, Margin & Liquidity, Performance, Orders, and Reconciliation views.
- Separate SPX 0DTE and Leveraged ETF Overview/B1–B5 product pages.
- Versioned contracts for broker snapshots, canonical positions, strategy snapshots, Flex EOD, allocation projections, and order intents.
- SQLite/WAL private ledger with transactional outbox, snapshot watermarks, `account + conId + model_code` identity, allocation lots, multi-currency cash events, immutable broker/order/execution events, and online backups.
- Quantity and cash reconciliation; incomplete broker snapshots are never interpreted as flat.
- Maintained `ib_async` collector for account summary, P&L series, positions/marks/P&L, and all-client open-order observation.
- Flex parser covering positions, trades, commissions, cash transactions, and NAV rows.
- Explicit SPX, LS-risk, live-B5, and research-B5 adapters with role/basis/denominator/provenance boundaries.
- Cloudflare v2 private read model using D1 plus immutable R2 evidence, body-bound signed ingest, replay and business-idempotency controls, and origin-side Access JWT verification.
- Deploy-time exclusion and scanning of private static artifacts and broker identifiers; post-deploy unauthenticated denial tests.
- Paper-first exact-contract Python limit-order API with quote freshness, NBBO price band, market tick, notional, reduce-only, what-if, ticket-bound approval, positive orderRef, partial fills, cancel/fill races, and uncertain-send reconciliation.
- NY4 systemd definitions for collector, publisher, health monitor, and backups; client-ID/ownership ADR and incident/restore runbook.
- Legacy bootstrap review tooling that refuses ambiguous ticker-to-conId or conflicting-owner mappings.

## External activation gates

These cannot be completed safely from a source checkout and intentionally fail closed:

1. Configure Cloudflare Access application/audience, `CF_ACCESS_TEAM_DOMAIN`, `CF_ACCESS_AUD`, `PORTFOLIO_INGEST_TOKEN`, `IBKR_ACCOUNT_IDS_FOR_SCAN`, and the private R2 bucket through the deployment environment.
2. Install the NY4 services, inject the account alias/ID and Gateway settings, register unique client IDs, and prove account/order visibility.
3. Provision the required Flex queries and credentials, then reconcile one completed statement through trades, commissions, cash, NAV, and positions.
4. Deploy positive SPX and LS `orderRef` namespaces in their producer repositories, dual-publish the versioned artifacts, and classify 100% of working orders before central paper submission.
5. Export both local SleeveStore and hosted D1 v1 data, review the generated bootstrap artifact, approve exact conId allocations and opening cash, then dual-run v1/v2.
6. Pass paper scenarios against the real Gateway: duplicate intent, reject, partial fill, cancel/fill race, Gateway restart, disconnect-after-send, stale quote, kill switch, and foreign/manual order coexistence.
7. Enable a tightly capped live canary only after explicit human approval. Source defaults remain dry-run/paper and `live_enabled=false`.

No live order, Cloudflare deployment, credential change, sibling-repository change, or allocation guess was performed by this implementation.
