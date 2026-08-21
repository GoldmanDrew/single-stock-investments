# ASML epistemic review receipt — 2026-08-21

**Work ID:** `3c1f58c10ad99d2de0093b41`  
**Task:** `review_forecast` for `operating_business_and_net_assets`  
**Draft:** `ASML/research/falsifier_drafts/757a61e81f740aade46766d0.json`  
**Evidence hash:** `82a1330a5789cba61993a44053c396e78f243b808d898aa83db01ddb5c4ba356` <!-- pragma: allowlist secret -->  
**Input SHA:** `274796fa857cf07d8ddcc3db3b701a22af4c4cfd`

## Epistemic loop status

**BOOTSTRAP_BLOCKED** — 0 eligible scored outcomes; calibration **insufficient_outcomes** with `release_hash: null`. Learning cannot change stance, valuation, or sizing.

## Calibration receipt

| Field | Value |
|-------|-------|
| calibration_release_hash | null |
| route | quality_reinvestment\|owner_earnings_reinvestment_dcf |
| named_challenge | null |
| calibration_response | not_applicable |

## Review challenges

| Challenge | Result | Notes |
|-----------|--------|-------|
| Reviewer differs from author | passed | Author `marvin-cloud-agent`; reviewer `marvin-cloud-agent-review` |
| Materiality | passed | Component is `entire_security`; 41% equity impact if fires |
| Period semantics | passed_with_note | FY2026 via fact_ledger adapter; metric id retains TTM naming for registry compatibility |
| Look-ahead | passed | Information cutoff 2026-08-18; FY2026 20-F not yet filed |
| Source replay | passed | OCF 14,873.8M minus capex 1,849.0M = 13,024.8M matches threshold and contract low trace |

## Disposition

**Approved** — spec `asml-opbiz-oe-2026fy` (v3, revision 1). Fires if FY2026 normalized owner earnings resolve below 13,024.8 USD millions (FY2025 low-case anchor). Promoter may append after scheduled review gate.

## Facts

- FY2025 normalized owner earnings: **$13,024.8M** (OCF €12.7B minus capex €1.6B, converted at 2025-12-31 rate) — `ASML/research/valuation_fact_ledger.json`
- Low-case DCF growth assumes modest year-1 uplift from this anchor (~2.4%); any YoY decline falsifies the bridge

## [HUMAN REVIEW]

- Stance and sizing remain in `human_decision.json` only
- Scheduled promoter appends approved draft to `falsifier_specs.json`; agents do not edit authoritative list in place
