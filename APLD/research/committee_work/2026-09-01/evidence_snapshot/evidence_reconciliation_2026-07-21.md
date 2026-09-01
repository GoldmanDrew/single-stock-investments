# APLD — Evidence reconciliation (contract backfill)

**As of:** 2026-07-21  
**Agent:** Marvin (contract_backfill)  
**Evidence hash:** `13df0257685cc36dd446f368d8dfba0f8eebb35c9236b713795be7c51f2b67f7`

## Summary

Universal valuation contract moved from **legacy_sensitivity** to **decision_grade** after attaching filing-grounded `calculation_proof` graphs to all four additive components. Proof outputs replace legacy per-share ranges in production; legacy ranges remain in `legacy_range_per_share` for comparison.

## Component ownership map

| Component | Overlap key | Economic claim | Proof method |
|-----------|-------------|----------------|--------------|
| existing_network | existing_network | Energized data-center operating capacity | `owner_cash_or_dividend_discount@1.0` |
| contracted_expansion | contracted_expansion | Contracted expansion cohorts (PF1–3, Delta Forge) | `owner_earnings_reinvestment_dcf@1.0` |
| uncontracted_option | uncontracted_option | Uncontracted marketed power lease-up | `risk_adjusted_milestone_value@1.0` |
| capital_and_execution_reserve | capital_and_execution_reserve | Net debt, preferred/SPV stack, execution reserve | `net_asset_value@1.0` |

No overlap keys collide. Options and contracted backlog are separate claims.

## Acceptance tests

### component_ownership_map — **met**

- **Evidence:** Four additive components with unique `overlap_key` values in `APLD/research/valuation.json` → `component_valuation_results.additive_components`.
- **Source:** `APLD/research/valuation_contract.json` (post-refresh).
- **Calculation:** Mechanical overlap audit in `universal_valuation_contract.py`.
- **Valuation consequence:** `unvalued_component_count` → 0.
- **Falsifier:** New filing reveals a material claim not mapped or double-counted.

### primary_cash_or_nav_bridge — **partially_met**

- **Evidence:** Existing network uses FQ3 nine-month revenue ($352.6M) annualized × bounded owner-cash margin × terminal multiple, less funding drag per share. Contracted expansion uses disclosed ~$31B backlog (press release) × ramp fraction × owner-cash yield, discounted.
- **Source:** `APLD/investor-documents/sec-edgar/10-Q_20260408_rpt20260228_acc0001144879_26_000030.htm`; `APLD/investor-documents/research-notes/2026-05-20_Polaris_Forge_3_lease_summary.md`.
- **Calculation:** See `calculation_proof` traces on `existing_network` and `contracted_expansion` in `valuation.json`.
- **Remaining uncertainty:** Filing-level adjusted EBITDA / segment owner-cash bridge not yet reproduced; proof base ($1.55/sh existing) is below legacy sensitivity ($21.08/sh) until energization cash is filed.
- **Falsifier:** Filed segment cash flow supports materially lower margin or longer funding drag than low case.

### downside_and_capital_claims — **met**

- **Evidence:** Capital reserve proof uses FY2025 long-term debt $869.5M, cash $41.6M, shares 285.8M, plus bounded senior-claim multiplier (preferred/SPV/execution).
- **Source:** `APLD/investor-documents/sec-edgar/10-K_20250730_rpt20250531_acc0001144879_25_000021.htm` (debt, cash); 10-Q cover (shares).
- **Calculation:** GAAP net debt × multiplier ÷ shares → proof outputs low **-$11.70**, base **-$5.61**, high **-$0.94** per share (matches legacy sensitivity within rounding).
- **Valuation consequence:** Downside capital claim is source-locked; contract status **decision_grade**.
- **Falsifier:** Filed debt/preferred stack exceeds low-case multiplier (4.04× GAAP net debt).

## Priced component totals (proof outputs)

| Case | Sum per share |
|------|----------------|
| Low | -$13.05 |
| Base | -$1.28 |
| High | +$11.73 |

Lawrence scenario IRR (`implied_return.base_pct` ~12%) remains the stance gate; component proof sum is a separate economic-value view.

## Monitoring

- Refresh proofs on next 10-Q with updated debt, cash, revenue, and shares.
- Promote press-release backlog estimates to filing tier when 10-K/8-K repeats $31B contracted revenue.
