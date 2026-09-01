# GYRO valuation evidence reconciliation — 2026-07-21

**Scope:** Close `authorized_evidence.json` contract backfill blockers by attaching valid `calculation_proof` graphs to every additive component. Authorized evidence packet per `research_agent_manifest.json`.

## Blockers closed

| Component | Prior status | Method | Proof status | Base per share |
|-----------|--------------|--------|--------------|----------------|
| `real_estate_nrv` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | $24.55 |
| `cash_and_other_assets` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | $1.87 |
| `loans_payable` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | −$4.91 |
| `estimated_liquidation_costs` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | −$7.60 |
| `other_liabilities` | legacy_sensitivity | net_asset_value@1.0 | bounded_estimate | −$2.12 |

Embedded component `b2k_entitlement_option` remains embedded in `real_estate_nrv`; not additive.

## Acceptance tests

### Component ownership map — met

| Field | Content |
|---|---|
| status | met |
| evidence | Five additive components with unique overlap keys; B2K option embedded in real-estate NRV. |
| source path | `GYRO/research/valuation.json` → `component_valuation.components[]` |
| calculation | Sum base **$11.79/sh** = $24.55 + $1.87 − $4.91 − $7.60 − $2.12, matching disclosed net assets in liquidation. |
| remaining uncertainty | Article 78 appeal and Smithtown site-plan timing can force NRV re-estimation. |
| affected components | All five additive blockers |
| valuation consequence | Ownership map complete; proofs attached. |
| falsifier | New filing reveals an unmodeled material claim or duplicate overlap key. |

### Primary owner-cash / NAV bridge — met

| Field | Content |
|---|---|
| status | met |
| evidence | 10-Q Q1 2026 liquidation-basis statement: real estate **$53,990,000**; total assets **$58,107,127**; loans **$10,790,194**; estimated liquidation costs net **$16,709,887**; net assets **$25,924,002** (**$11.79/sh**). |
| source path | `GYRO/investor-documents/sec-edgar/10-Q_20260513_rpt20260331_acc0001437749_26_016537.htm` |
| calculation | Each additive proof divides a filing-locked or bounded dollar claim by **2,199,308** shares; component sum reproduces management NAV. |
| remaining uncertainty | Low/high bands on NRV and cost accrual are bounded judgments, not new filing marks. |
| affected components | All additive blockers |
| valuation consequence | Filing-locked facts anchor proofs; legacy sensitivities excluded from decision-grade sum. |
| falsifier | Next quarter net assets in liquidation per share falls below **$10.50** without a matching proof update. |

### Downside and capital claims — met

| Field | Content |
|---|---|
| status | met |
| evidence | Loans **$10.79M** with 2021 mortgage initial maturity **2026-10-10** and extension option; MD&A states additional capital may be needed through 2028. |
| source path | 10-Q Q1 2026 Notes 4–5 and MD&A |
| calculation | Senior claims modeled as additive negative components; bear scenario in dated payoff uses lower B2K price and extended timeline (~$9.00/sh). |
| remaining uncertainty | Refinancing failure or further cost re-estimation (FY2025 drop $13.91→$11.76) remains widest bands. |
| affected components | `loans_payable`, `estimated_liquidation_costs`, `real_estate_nrv` |
| valuation consequence | Downside claims reconciled to filings; no double-count with embedded B2K option. |
| falsifier | Drawn loans exceed **$12M** without offsetting asset sale proceeds. |

### Overlap control — met

| Field | Content |
|---|---|
| status | met |
| evidence | Unique overlap keys unchanged; `b2k_entitlement_option` treatment=embedded in `real_estate_nrv`. |
| source path | `GYRO/research/valuation.json` |
| calculation | No additive overlap key duplicates; `double_counting_flags` empty in authorized evidence. |
| remaining uncertainty | None on overlap map. |
| affected components | All |
| valuation consequence | Component sum is additive once. |
| falsifier | New component added without unique overlap_key. |

## Facts vs judgments

**Facts (locked):** Real estate held for sale **$53,990,000**; total assets **$58,107,127**; loans **$10,790,194**; estimated liquidation costs **$16,709,887**; net assets **$25,924,002**; shares **2,199,308**; net assets per share **$11.79**.

**Judgments (bounded):** NRV re-mark band **$22–27/sh**; non-RE asset band **$1.50–2.20/sh**; loan stress **−$5.20 to −$4.50/sh**; cost accrual **−$9.50 to −$6.00/sh**; other liabilities **−$2.50 to −$1.80/sh**.

## Valuation consequence

Proof-complete additive schedule base case **$11.79 per share** vs price **~$5.80** implies a large market discount to management liquidation NAV if the 2028 timeline holds. Lawrence equity-yield-curve base **33.4%** annualized remains the stance gate input; security stays **hold** pending human review of Article 78 and B2K site-plan status. No human capital decision recorded.
