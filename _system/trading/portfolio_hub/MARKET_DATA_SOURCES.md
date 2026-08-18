# Portfolio risk source and entitlement matrix

| Measure | Required source | Freshness | License / display rule | Missing-data behavior |
|---|---|---|---|---|
| Positions, marks, account P&L | IBKR live account/portfolio/PnL callbacks | Seconds | Private internal display | Unknown; never flat/zero |
| Margin and liquidity | IBKR account summary | Seconds | Private internal display | Suppress account strip and alert |
| Completed P&L/NAV/cash | IBKR Flex queries | Next completed statement | Private evidence | Retain prior session; label pending |
| Executions/commissions | IBKR live + Flex | Event/EOD | Private evidence | Reconciliation break |
| Greeks | IBKR model greeks or licensed option model | Seconds/minutes | Private, entitlement required | Null with coverage count |
| Beta/factors/scenarios | LS-risk atomic producer export | Producer cadence | Internal producer output | Do not pro-rate nonlinear totals |
| SPX stop/defined risk | SPX producer export | Session heartbeat | Internal producer output | Broker legs remain visible; model stale |
| Borrow rate/availability | LS borrow/Flex/approved vendor | Daily/intraday | Vendor terms govern | Null, never zero |
| FX translation | IBKR cash/FX plus approved EOD rates | Intraday/EOD | Private internal display | Show native currency only |
| Sector/country/theme | SSI research registry | Research cadence | Internal metadata | Unclassified bucket |
| Returns/drawdown | Canonical NAV plus external cash flows | Daily | Derived internally | TWR/MWR suppressed until complete |

Every normalized value carries source, source run, as-of time, currency, quality, model version where applicable, and denominator lineage for percentages. Vendor datasets may not be copied to public exports. Coverage—not silent imputation—is the Phase 8 acceptance measure.
