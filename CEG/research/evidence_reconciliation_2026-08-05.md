# CEG valuation evidence reconciliation — 2026-08-05

**Scope:** Contract backfill. Close `authorized_evidence.json` blocker: extreme annualized return requires independent validation with a second method and source-backed evidence. Evidence packet per `research_agent_manifest.json`.

## What changed since 2026-07-30

| Artifact | Prior | Current |
|----------|-------|---------|
| `DOWNLOAD_MANIFEST.json` | 55 SEC docs indexed | Stable; all entries `ok: true` |
| `authorized_evidence.json` | `extreme_return_validated: false` | **Target:** pass via `outlier_validation` |
| `valuation.json` | Component proof complete; no outlier block | Added `valuation_methodology.outlier_validation` with Lawrence IRR cross-check |
| Narrative | No filing-grounded deep dive | First dive `deep_dive_2026-08-05.md` |

## Blocker closure: extreme return validation

### Acceptance test — met

| Field | Content |
|---|---|
| status | met |
| evidence | `valuation_methodology.outlier_validation.status` = `passed`; two independent methods with filing refs |
| source path | `CEG/research/valuation.json` |
| calculation | **Method 1 (component economic value):** owner-earnings reinvestment DCF proof base **$28.53/sh** at price **$253.50** → contract annualized return **−26.81%** over 7 years. **Method 2 (Lawrence owner-cash IRR):** normalized starting owner cash **$3.57/sh** (FY2025 operating cash flow **$4.24B** minus capital spending **$2.95B**, scaled to **361.2M** shares) at **$253.50** → synthesis base **−12.5%** per year (6% growth years 1–5, 4% years 6–7, 15× exit on year-7 owner cash). |
| remaining uncertainty | Methods diverge in magnitude (−26.81% vs −12.5%) because the component DCF applies reinvestment-at-return mechanics and a 10% discount rate while Lawrence uses simpler growth-to-exit; both independently confirm price far above filing-grounded economics. Market may be capitalizing Microsoft/AI firm-power contracts and Calpine scale not yet in normalized owner cash. |
| falsifier | Sustained owner cash above **$8/sh** on FY2026–FY2027 filings without proportional debt or share issuance; or signed data-center PPAs with disclosed economics that raise normalized owner earnings above **$6B** annually. |

### Component proof completeness — unchanged, met

Single additive component `operating_business_and_net_assets` retains valid `calculation_proof` graph (`owner_earnings_reinvestment_dcf@1.0`). Overlap key `entire_security` non-overlapping; `double_counting_flags` empty.

## Facts vs judgments

**Facts (locked):** FY2025 revenue **$25.5B**; operating cash flow **$4.24B**; capital spending **$2.95B**; normalized owner earnings **$1.29B** (**$3.57/sh**); cash **$1.17B** (Q1 2026); long-term debt **$17.0B** (Q1 2026); shares **361.2M** (Apr 2026); price **$253.50** (Yahoo close 2026-07-20).

**Judgments (bounded):** Reinvestment rate 20–50%; incremental after-tax return on capital 12–25%; discount rate 9–12%; terminal owner-earnings multiple 12–24×.

## Valuation consequence

Proof-complete additive schedule base **$28.53 per share** vs **$253.50** price. Lawrence synthesis **−12.5%** per year remains stance reference. Both methods validate extreme negative return at current quote. Security remains **watch**; no human capital decision recorded.
