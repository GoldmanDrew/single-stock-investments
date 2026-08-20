# ASML epistemic review forecast — 2026-08-20

**Work ID:** `3c1f58c10ad99d2de0093b41`  
**Draft:** `ASML/research/falsifier_drafts/757a61e81f740aade46766d0.json`  
**Spec:** `asml-opbiz-oe-2026fy` (revision 1)  
**Component:** `operating_business_and_net_assets`  
**Reviewer:** marvin-cloud-agent-review-2026-08-20 (distinct from author run)  
**Provenance:** `ASML/research/agent_run_state.json`  
**Input SHA:** `47728abdee39975936ab20163a2c87b8c45f2e1d`

## Epistemic loop status

**BOOTSTRAP_BLOCKED.** No active calibration release hash (`calibration_release_hash: null`). Calibration cannot change this analysis; `insufficient_outcomes` means no named error-pattern challenge applies. Calibration response: **not_applicable**.

## Verdict

**Approved.** Draft status set to `approved`; independent reviewer differs from author (`marvin-cloud-agent`).

## What the forecast tests

If FY2026 normalized owner earnings (operating cash flow minus capital spending, USD millions, EUR converted at year-end rate) resolve **below 13,024.8**, the owner-cash leg of the low-case DCF bridge has failed. Comparator: `lt`. Threshold matches the locked low-case proof trace at `ASML/research/valuation_contract.json#operating_business_and_net_assets.calculation_proof.traces.low.owner_earnings`.

## Challenge record

### Materiality

**Pass.** Component value impact is 41%, above the 10% policy floor. Low-case component value is **$382** per share versus **$644** base (`valuation_contract.json` outputs). A sub-anchor FY2026 owner-earnings print would compress the bounded range materially, not cosmetically.

### Period semantics

**Pass.** ASML is an annual 20-F filer with no interim 10-Q. The observation plan correctly uses `fact_ledger` adapter, `duration_basis: FY`, `fiscal_period: ANY`, and `accepted_forms: ["20-F", "20-F/A"]`. Measurement period end **2026-12-31**; observable after **2027-02-28** (prior FY2025 20-F filed **2026-02-25** per `ASML/investor-documents/DOWNLOAD_MANIFEST.json`); resolution deadline **2027-04-29** (60-day grace). The registry metric id `normalized_owner_earnings_ttm_m` is a naming artifact for annual filers; preflight accepts `fact_ledger` when `source_hint` is set.

### Look-ahead

**Pass.** `registered_at` (2026-08-18) precedes `observable_after` (2027-02-28). `outcome_unavailable_at_registration: true`. Threshold anchor uses only FY2025 facts (`as_of: 2025-12-31`), all before `information_cutoff_at`.

### Source replay

**Pass.** Independently recomputed from locked ledger facts:

| Field | Value (USD millions) | Source |
|-------|---------------------:|--------|
| Operating cash flow | 14,873.80 | `valuation_fact_ledger.json#operating_cash_flow_m` |
| Capital expenditures | 1,848.99 | `valuation_fact_ledger.json#capital_expenditures_m` |
| Normalized owner earnings | **13,024.82** | formula: OCF minus abs(capex) |

Matches `historical_replay.resolved_value` (13,024.816…) and contract low trace (13,024.81611167). EUR/USD conversion evidenced on ledger fact (`fx_conversion.from_currency: EUR`, rate_as_of 2025-12-31).

## Component fingerprint

Unchanged: `5adcad55017a09bc5091ed0c58de45dca3e605ac854a64408eb8cfa3f6776ce5` matches current `economic_ownership_map` entry.

## Receipt

| Field | Value |
|-------|-------|
| work_id | 3c1f58c10ad99d2de0093b41 |
| task_type | review_forecast |
| disposition | success |
| spec_id | asml-opbiz-oe-2026fy |
| calibration_response | not_applicable |

Promotion to `falsifier_specs.json` is owned by the scheduled promoter, not this review run.
