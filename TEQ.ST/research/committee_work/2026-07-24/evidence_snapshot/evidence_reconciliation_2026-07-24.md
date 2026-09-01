# TEQ.ST — Evidence reconciliation (universal contract)

**Date:** 2026-07-24  
**Agent:** Marvin (contract backfill)  
**Evidence hash:** `0528aa4fb0afdb8f40db742f6f0643f3b529ea12d3a6d765baf1c05cc1b0663b` // pragma: allowlist secret  
**Framework:** `_system/prompts/cursor_valuation_evidence_worker.md`

## Status

**Contract status:** decision_grade (proof-backed component schedule).  
**Prior status:** evidence_blocked (legacy_sensitivity on all four additive components).

## Acceptance tests closed

### component_ownership_map

| Claim | Overlap key | Treatment | Proof method |
|-------|-------------|-----------|--------------|
| Operating portfolio owner cash | `core_engine` | additive | `owner_cash_or_dividend_discount@1.0` |
| Acquisition reinvestment runway | `reinvestment_or_assets` | additive | `owner_earnings_reinvestment_dcf@1.0` |
| Cash, debt, contingent consideration | `net_financial_claims` | additive | `net_asset_value@1.0` |
| First North liquidity reserve | `downside_reserve` | additive | `net_asset_value@1.0` |

**Unit denominator:** 17,165,756 shares at 2025-12-31 (`official-reports/annual-reports/2026-03-21 - Årsredovisning 2025.pdf`).

### primary_cash_or_nav_bridge

| Input | Filing value | Per share | Source |
|-------|--------------|-----------|--------|
| FCF ex-acquisitions | 173.1 MSEK | 10.08 SEK | `year-end-reports/2026-02-14 - Year-End Report 2025` cross-check vs Note 27 operating CF 184.6 MSEK |
| Operating EBITA | 203.1 MSEK | — | Annual 2025 |
| Cash | 209.5 MSEK | 12.21 SEK | Annual 2025 balance sheet |
| Net debt ex-leases | 286.6 MSEK | 16.70 SEK | Annual 2025 MD&A |
| Contingent consideration | 195.6 MSEK | 11.39 SEK | Annual 2025 Note 4 |

**Component base sum:** 126.39 + 22.12 + 7.95 − 14.22 ≈ **142.2 SEK** vs price **158 SEK**.

### downside_and_capital_claims

- **Debt:** Net debt/EBITDA guardrail < 2.5; actual leverage within policy at FY2025 (`Årsredovisning 2025` MD&A).
- **Contingent consideration:** 195.6 MSEK liability; probability-weighted in `net_financial_claims` proof.
- **Dilution:** No dividend FY2025; option programs disclosed; share count locked at 17,165,756.
- **Liquidity reserve:** First North execution friction sized as 9% of price in base case (`downside_reserve` proof).

## Calculation proof summary

| Component | Base (SEK/sh) | Method |
|-----------|---------------|--------|
| core_engine | 126.39 | Owner cash capitalization on 10.08 SEK/sh normalized FCF |
| reinvestment_or_assets | 22.12 | Incremental ROIC multiple on 306.9 MSEK acquisition spend |
| net_financial_claims | 7.95 | Cash minus bounded debt and earn-out charges plus credit headroom |
| downside_reserve | −14.22 | 9% liquidity reserve on 158 SEK reference price |

## Remaining uncertainty

- Q1 2026 interim still inventory-tier (0-char extract); margin/organic claims rely on prior review until re-extracted.
- Live TEQ.ST price may differ from 158 SEK reference in `valuation.json` inputs.

## Falsifiers

- Sustained organic decline with margin compression below 9% financial target.
- Earn-out payouts or net debt above guardrail without offsetting acquisition returns.
- Goodwill impairments recurring at FY2025 Q3 scale (73 MSEK).

## Valuation consequence

Universal contract unblocked; Lawrence synthesis **14.4%** base remains separate stance gate. Component economic value base **142.2 SEK** implies roughly **−10%** downside to proof-backed base vs spot price.
