# TPL evidence reconciliation — 2026-07-24

**Ticker:** TPL  
**Method profile:** scarce_asset_optionality  
**Purpose:** Close universal contract blockers from `authorized_evidence.json` with filing-backed calculation_proof graphs and non-overlapping economic claims.

**Authorized evidence hash:** `bf29a7cd7a8ec56cca5b5c3571e9e97601557b7adf4deb1fe836a5e7eaa16665` // pragma: allowlist secret

## Sources

| Source | Path | Period |
|--------|------|--------|
| Form 10-K | `TPL/investor-documents/sec-edgar/10-K_20260218_rpt20251231_acc0001811074_26_000018.htm` | FY2025 |
| Form 10-Q | `TPL/investor-documents/sec-edgar/10-Q_20260506_rpt20260331_acc0001811074_26_000035.htm` | Q1 2026 |
| 8-K desalination | `TPL/investor-documents/sec-edgar/8-K_20250814_rpt20250814_acc0001104659_25_078186.htm` | 2025-08-14 |
| 8-K Bolt / data center | `TPL/investor-documents/sec-edgar/8-K_20251217_rpt20251217_acc0001104659_25_121822.htm` | 2025-12-17 |
| Prior reconciliation | `TPL/research/evidence_reconciliation_2026-07-21.md` | 2026-07-21 |

Diluted shares (FACT): **69.027M** (FY2025 10-K EPS bridge).

---

## Gap 1 — `tract_level_royalty_inventory`

**Status:** `accepted`

### Proof linkage
- `producing_royalty_operations`: `owner_cash_or_dividend_discount@1.0` on **$411.7M** FY2025 oil and gas royalty revenue → base **$88.35/sh**
- `visible_royalty_inventory_option`: `risk_adjusted_milestone_value@1.0` on **224,000** total NRA at comparable marks after producing-DCF subtraction; **45%** residual allocation → base **$18.65/sh**
- `dormant_royalty_inventory_option`: same residual pool; **55%** allocation → base **$22.80/sh**

### Acceptance test (met)
| Requirement | Evidence |
|-------------|----------|
| Unique ownership claim | Producing cash flow, visible inventory, and dormant inventory use separate `overlap_key` values; producing DCF is subtracted before undeveloped residual allocation. |
| Activity class | Producing = current royalty revenue; visible = near-term drillable inventory (judgment); dormant = longer-dated inventory (judgment). |
| Probability and timing | Low/base/high comparable marks **$25k / $40k / $75k** per NRA encode timing and realization risk in the range width. |
| No overlap with producing cash | Cross-check on both inventory components states producing DCF is deducted from total comparable NAV before split. |

### Remaining limitations (documented, not blocking)
- TPL does not publish tract-level or county-level NRA roll-forward; the **45%/55%** visible/dormant split is a portfolio-level judgment anchored to operator activity proxies, not a filing table.
- The **~70,000 NRA** visible label in component notes remains provisional until a disclosed inventory roll-forward exists.

### Falsifier
A new filing shows total NRA materially below **200,000** or a duplicate royalty claim in both producing DCF and inventory options without overlap adjustment.

---

## Gap 2 — `water_economic_separation`

**Status:** `accepted`

### Proof linkage
| Component | Method | Revenue anchor | Treatment | Base $/sh |
|-----------|--------|----------------|-----------|-----------|
| `produced_water_royalties` | owner_cash_or_dividend_discount@1.0 | **$124M** produced-water royalty (capital-free) | additive | 43.25 |
| `operated_water_sales` | owner_earnings_reinvestment_dcf@1.0 | **$170M** operated water sales | additive; growth capital in ROIC path | 16.41 |
| `water_infrastructure_cross_check` | net_asset_value@1.0 (embedded) | **$164.5M** net PP&E FY2025 | embedded in operated water; not additive | 2.38 |
| `desalination_and_water_technology_option` | risk_adjusted_milestone_value@1.0 | Phase 2 facility complete; commercialization milestone | additive option | 1.16 |

FY2025 water segment total **~$307.5M** reconciles to royalty plus operated streams per 10-K segment disclosure.

### Acceptance test (met)
| Requirement | Evidence |
|-------------|----------|
| Royalty vs service separation | Distinct proofs on **$124M** royalty vs **$170M** operated revenue; different methods (capital-free vs reinvestment DCF). |
| Infrastructure cross-check only | `water_infrastructure_cross_check` treatment **embedded** in `operated_water_sales`; PP&E proof is a floor check, not added to component sum. |
| Growth capital deducted once | Operated-water DCF charges incremental after-tax ROIC explicitly; royalty stream has no reinvestment burden. |

### Remaining limitations
- Transfer pricing between TPWR operated entities and royalty volume is not disclosed at line-item level; volume bridges use segment totals only.
- Maintenance vs growth water capital is not split in filings; ROIC path uses judgment bands.

### Falsifier
Operated-water margin collapses below **25%** after-tax owner-cash conversion for two quarters while royalty stream is unchanged, suggesting mis-attributed economics.

---

## Gap 3 — `option_milestones_and_capital`

**Status:** `accepted`

### Milestone trees (driver_model excerpts)

| Component | Enforceable milestone (filing) | Success probability (base) | Remaining owner capital (base) | Base $/sh |
|-----------|-------------------------------|----------------------------|----------------------------------|-----------|
| `future_infrastructure_corridors` | Uncontracted easement/corridor pipeline; graduates to surface operations when contracted | 45% | **$30M** | 4.45 |
| `data_center_power_water_option` | Bolt **$50M** equity investment (8-K 2025-12-17); contracted receivable modeled separately | 6% | **$10M** | 2.03 |
| `desalination_and_water_technology_option` | Phase 2 desalination complete (8-K 2025-08-14); May 2026 commercial operation target | 10% | **$20M** | 1.16 |

Contracted data-center receivable (**$0.30/sh** base) and Bolt investment are **excluded** from incremental project success values to prevent double counting.

### Acceptance test (met)
| Requirement | Evidence |
|-------------|----------|
| Dated milestone tree | Desalination and Bolt/data-center milestones cite primary 8-K paths; corridor option uses stage-gated success value less remaining cost. |
| Success probability | Each `driver_model.scenarios.base.success_probability` is explicit in `valuation.json` proofs. |
| Remaining capital | Each base case includes `remaining_cost_m` deducted in `risk_adjusted_milestone_value@1.0` arithmetic. |
| Zero on falsifier | Monitoring falsifiers in contract require milestone failure or capital overrun before value goes to zero in narrative; low cases allow near-zero outputs. |

### Remaining limitations
- Data-center rent or power/water tariff economics are not yet in SEC contracts at granular low/base/high levels; success values remain judgment bands.
- Desalination commercial ramp and capital-light licensing structure are not yet proven in audited revenue.

### Falsifier
Disclosed remaining project capital exceeds **$50M** on any single option without corresponding success-value revision, or a filed impairment/write-down on Bolt without reserve adjustment.

---

## Component proof sum (base case)

| Layer | Components | Base $/sh |
|-------|------------|-----------|
| Operating | producing royalty, surface/easements, water royalty, operated water | 162.90 |
| Financial | cash, contracted receivable | 4.62 |
| Inventory / land options | visible + dormant royalty, residual surface, corridors | 78.50 |
| Project options | data center, desalination | 3.19 |
| Reserve | realization and corporate friction | −3.00 |
| **Total (additive)** | thirteen components | **≈246.21** |

Cross-check: Lawrence seven-year owner-cash base **−8.2%** per year at **~$414** price; component schedule and Lawrence path remain separate views per `valuation_methodology.decision_rule`.

---

## Acceptance summary

| Gap | Status | Closure basis |
|-----|--------|---------------|
| tract_level_royalty_inventory | accepted | Portfolio NRA fact + producing-DCF subtraction + visible/dormant split with non-overlapping proofs |
| water_economic_separation | accepted | Separate royalty and operated proofs; embedded PP&E cross-check; desalination as distinct option |
| option_milestones_and_capital | accepted | Milestone driver_models with probability, remaining capital, and filing-anchored 8-K milestones |

**Committee conclusion:** Contract blockers closed with proof-first component schedule. Tract-level granularity and uncontracted project economics remain in `economic_value_analysis.limitations` and **[HUMAN REVIEW]**; do not promote stance without `human_decision.json`.
