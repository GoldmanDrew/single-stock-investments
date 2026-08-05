# COHR valuation evidence reconciliation — 2026-08-05

**Scope:** Contract backfill. Close `authorized_evidence.json` blocker: extreme annualized return requires independent validation with a second method and source-backed evidence. Evidence packet per `research_agent_manifest.json`.

## What changed since 2026-07-30

| Artifact | Prior | Current |
|----------|-------|---------|
| `DOWNLOAD_MANIFEST.json` | 85 SEC docs indexed | Stable; all entries `ok: true` |
| `authorized_evidence.json` | Missing | Created with blocker list and evidence hash |
| `valuation.json` | Component proof complete; no outlier block | Added `valuation_methodology.outlier_validation` with Lawrence IRR cross-check |
| Narrative | No filing-grounded deep dive | First dive `deep_dive_2026-08-05.md` |

## Blocker closure: extreme return validation

### Acceptance test — met

| Field | Content |
|---|---|
| status | met |
| evidence | `valuation_methodology.outlier_validation.status` = `passed`; two independent methods with filing refs |
| source path | `COHR/research/valuation.json` |
| calculation | **Method 1 (component economic value):** owner-earnings reinvestment DCF proof base **$15.09/sh** at price **$285.40** → contract annualized return **−34.3%** over 7 years. **Method 2 (Lawrence owner-cash IRR):** normalized starting owner cash **$0.99/sh** (FY2025 operating cash flow **$634M** minus capital spending **$441M**, scaled to **195.6M** shares) at **$285.40** → synthesis base **−27.4%** per year (6.3% growth years 1–5, 4% years 6–7, 18× exit on year-7 owner cash). |
| remaining uncertainty | Methods diverge in magnitude (−34.3% vs −27.4%) because the component DCF applies reinvestment-at-return mechanics and a 10% discount rate while Lawrence uses simpler growth-to-exit; both independently confirm price far above filing-grounded economics. Market may be capitalizing AI/datacom photonics and post-merger scale not yet in normalized owner cash. |
| falsifier | Sustained owner cash above **$4.00 per share** on FY2026–FY2027 filings without proportional debt or share issuance; or segment disclosures showing incremental return on capital above **25%** on reinvested capital with capex held flat. |

### Component proof completeness — unchanged, met

Single additive component `operating_business_and_net_assets` retains valid `calculation_proof` graph (`owner_earnings_reinvestment_dcf@1.0`). Overlap key `entire_security` non-overlapping; `double_counting_flags` empty.

## Facts vs judgments

**Facts (locked):** FY2025 revenue **$5.81B** (+23% YoY); net income **$49M** (down from **$156M**); operating cash flow **$634M**; capital spending **$441M**; normalized owner earnings **$193M** (**$0.99/sh**); cash **$2.23B** (Q1 2026, incl. restricted); long-term debt **$3.18B** (Q1 2026); shares **195.6M** (May 2026); price **$285.40** (Yahoo close 2026-07-20).

**Judgments (bounded):** Reinvestment rate 20–50%; incremental after-tax return on capital 12–25%; discount rate 9–12%; terminal owner-earnings multiple 12–24×.

## Valuation consequence

Proof-complete additive schedule base **$15.09 per share** vs **$285.40** price. Lawrence synthesis **−27.4%** per year remains stance reference. Both methods validate extreme negative return at current quote. Security remains **watch**; no human capital decision recorded.
