# Short Alpha filing furnace

**Status:** implementation contract for systematic filing analysis  
**Reference pattern:** Friday Furnace-style event discovery and tagging; this is an independent internal framework, not a copy of its content or product.

## Objective

Turn each new filing into a small number of falsifiable, source-addressable changes. The unit of work is not “summarize the 10-Q.” It is:

> **What changed, why can it impair the common equity, what evidence would confirm it, and what would prove the short wrong?**

## Partition

### 1. Identity and instrument

- Issuer, ticker, CIK, security type, exchange, and corporate-action history
- Operating company vs holding company vs SPAC vs fund vs daily-reset product
- Underlying/security dependency graph (for example `ECHX → ECHO`)
- Shares, warrants, converts, preferreds, earnouts, swaps, and other claims

### 2. Financial oxygen

- Unrestricted cash; revolver availability; minimum-liquidity covenants
- Quarterly operating cash burn and maintenance capital spending
- Debt maturity wall, floating-rate exposure, covenant headroom, and refinancing price
- ATM/shelf capacity, warrant exercise economics, and fully diluted share count
- Runway under base, adverse, and no-capital-market cases

### 3. Earnings quality

- Revenue recognition and concentration
- Receivables, contract assets/liabilities, inventory, and reserve movements
- Capitalized costs, useful-life changes, impairments, and gains presented as operations
- Acquisition accounting, pro forma claims, goodwill, and earnouts
- Recurring “one-time” adjustments and adjusted-EBITDA-to-cash conversion
- Auditor change, material weakness, restatement, late filing, and critical audit matters

### 4. Operating failure mode

- Unit price, volume, mix, utilization, capacity, backlog, churn, and cohort economics
- Supply additions, substitution, customer concentration, and purchasing commitments
- Segment margin bridge and incremental/decremental margin
- Regulatory/license/contract dependencies
- Management, board, control, compensation, and related-party changes

### 5. Market mechanics and timing

- Borrow availability, fee, utilization, recall history, and dividend/merger obligations
- Days-to-cover, crowding, options skew, float, lockups, index flows, and corporate actions
- Catalyst window, expected cash runway, and the cost of being early
- Maximum adverse move and position-size rule before an IC can approve the idea

## Event record

Every detected change should become one immutable event:

```json
{
  "ticker": "XYZ",
  "filed_at": "2026-08-04",
  "form": "10-Q",
  "accession": "...",
  "category": "financial_oxygen",
  "tags": ["serial_equity_issuance", "cash_runway"],
  "claim": "Runway falls below four quarters without new capital.",
  "prior_value": 6.2,
  "new_value": 3.7,
  "unit": "quarters",
  "evidence_ref": "TICKER/investor-documents/sec-edgar/...htm#locator",
  "short_impact": "strengthens",
  "confidence": "high",
  "falsifier": "Committed financing extends runway beyond eight quarters without >10% dilution.",
  "review_status": "analyst_reviewed"
}
```

## Taxonomy

Use one category and zero or more tags. Categories are stable; tags can expand.

| Category | Initial tags |
|---|---|
| Identity/instrument | ticker_change, reverse_split, merger, daily_reset, swap_exposure, tracking_risk |
| Financial oxygen | going_concern, cash_runway, covenant_pressure, refinancing, serial_equity_issuance, warrant_overhang |
| Accounting | revenue_recognition, capitalization, reserve_release, restatement, material_weakness, auditor_change, non_gaap, acquisition_accounting |
| Operations | margin_contraction, utilization, customer_concentration, supply_build, backlog_quality, impairment, restructuring |
| Governance/legal | related_party, executive_exit, controlling_holder, compensation, investigation, litigation, license, delisting |
| Transaction | deal_stress, financing_gap, strategic_review, asset_sale, wind_down, exchange_offer |

“Fraud” is a conclusion tag only after a regulator, court, admitted restatement/misconduct, or evidence-backed analyst determination. Until then use the specific observed tag.

## Processing sequence

1. Fetch filing and exhibits; preserve accession and content hash.
2. Diff against the comparable prior filing at section and structured-fact level.
3. Extract changed claims and numbers with exact locators.
4. Route each change to the partition and tags above.
5. Reconcile against the current Short Alpha hypothesis, catalyst, and falsifiers.
6. Update valuation/instrument scenarios only when a changed fact crosses a declared materiality threshold.
7. Queue human review for fraud/bad-actor, legal, related-party, and accounting-conclusion labels.
8. Append an outcome check-in; never overwrite the historical baseline.

## Dashboard contract

The Short Alpha tab consumes compact events, not filing prose. Each idea should show:

- latest strengthening and weakening events;
- unresolved contradictions;
- filing/source link;
- research and IC gate;
- next catalyst date;
- baseline-vs-actual price and thesis state.

## Guardrails

- Primary documents outrank articles and social posts.
- A third-party short report is a lead generator, not an adopted fact set.
- Separate reported facts, derived calculations, analyst assumptions, and allegations.
- Include borrow, dividends, merger terms, and path dependence in payoff math.
- A correct fundamental thesis can still be a bad short because of timing, crowding, or financing cost.
