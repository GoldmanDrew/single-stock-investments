# BN valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component and reconciling the economic unit denominator to primary filings.

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `core_engine` | legacy_sensitivity | owner_earnings_reinvestment_dcf@1.0 | bounded_estimate | $32.75 |
| `reinvestment_or_assets` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | $6.43 |
| `net_financial_claims` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | $2.30 |
| `downside_reserve` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | -$4.13 |

**Proof sum (base):** $32.75 + $6.43 + $2.30 − $4.13 = **$37.35/sh** vs legacy scaffold **$41.34/sh**. Proof-first schedule supersedes legacy sensitivities for the universal contract.

## Acceptance tests

### Component ownership map — met

| Field | Content |
|-------|---------|
| status | met |
| evidence | Four additive components with unique overlap keys: `core_engine`, `reinvestment_or_assets`, `net_financial_claims`, `downside_reserve`. DE split 60% direct+operating / 40% FRE+wealth prevents double-counting AM fees in the DCF slice. |
| source path | `BN/research/valuation.json` → `component_valuation.components[]` |
| calculation | Each material claim mapped once; `double_counting_flags` empty. |
| remaining uncertainty | Parent-only corporate net claims require 40-F segment carve-out [HUMAN REVIEW]. |
| affected components | All four |
| valuation consequence | Ownership map complete for committee review. |
| falsifier | New filing shows material claim (e.g. BNT merger, preferred stack) omitted from map. |

### Primary owner-cash / NAV bridge — met

| Field | Content |
|-------|---------|
| status | met |
| evidence | LTM DE $2.54/sh (`2026-Q1-BN-Supplemental-vF-2.pdf`); Q1 DE $0.66/sh; DE definition as deconsolidated earnings available for distribution. |
| source path | `BN/investor-documents/ir-bn/2026-Q1-BN-Supplemental-vF-2.pdf` |
| calculation | LTM DE total = $2.54 × 2,367.8M = **$6,014M**. Core proof uses 60% = **$3,609M** owner earnings base; FRE proof uses 40% = **$2,406M** capitalized at 6.33× → **$6.43/sh**. |
| remaining uncertainty | Exact DE segment split not in XBRL; 60/40 is judgment anchored to supplemental AM vs direct-investment language. |
| affected components | `core_engine`, `reinvestment_or_assets` |
| valuation consequence | Causal low/base/high from reinvestment, ROIC, discount, and capitalization assumptions. |
| falsifier | Two consecutive quarters of FRE decline >15% YoY with flat FBC. |

### Downside and capital claims — met

| Field | Content |
|-------|---------|
| status | met |
| evidence | Diluted shares 2,367.8M (40-F CY2025); consolidated cash $16.24B and borrowings $14.30B noted but excluded from net_financial_claims to avoid look-through double-count. |
| source path | `BN/research/evidence/sec_companyfacts.json` |
| calculation | Reserve base **-$9,789M** / 2,367.8M = **-$4.13/sh**; net corporate claims base **$5,455M** / 2,367.8M = **$2.30/sh**. |
| remaining uncertainty | Parent-only net financial claims [HUMAN REVIEW]; realization reserve magnitude judgment-heavy. |
| affected components | `net_financial_claims`, `downside_reserve` |
| valuation consequence | Senior claims and volatility reserved outside operating DE proofs. |
| falsifier | Material preferred or merger-related liability disclosed above low-case reserve. |

### economic_claim.unit_count — met

| Field | Content |
|-------|---------|
| status | met |
| evidence | `ifrs-full:AdjustedWeightedAverageShares` = 2,367,800,000 for CY2025. |
| source path | `BN/investor-documents/sec-edgar/40-F_20260318_rpt20251231_acc0001001085_26_000006.htm` via `sec_companyfacts.json` |
| calculation | `inputs.shares_outstanding` = 2,367,800,000; `economic_claim.unit_count` synced. |
| remaining uncertainty | None on denominator. |
| affected components | All per-share proofs |
| valuation consequence | Resolves validation error `economic_claim.unit_count required`. |
| falsifier | Share count revision >5% in next interim without matching proof refresh. |

## Facts vs judgments

**Facts (locked):** LTM DE $2.54/sh; Q1 2026 DE $0.66/sh; fee-bearing capital $614B; diluted shares 2,367.8M; consolidated cash $16.24B and borrowings $14.30B (context only).

**Judgments:** 60/40 DE split; reinvestment/ROIC/discount/terminal for core DCF; FRE capitalization multiple; parent net corporate claims; realization/holdco reserve.

**Opinion:** Lawrence base **11.9%** remains stance gate; component proof sum **$37.35/sh** vs price **~$45.93** implies modest negative base-case margin of safety before reserve release.
