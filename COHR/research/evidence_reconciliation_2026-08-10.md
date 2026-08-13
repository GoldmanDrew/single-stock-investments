# COHR valuation evidence reconciliation — 2026-08-10

**Scope:** Contract backfill. Close `authorized_evidence.json` blocker: extreme annualized return requires independent validation with a second method and source-backed evidence. Evidence packet per `research_agent_manifest.json`.

## What changed since 2026-07-30

| Artifact | Prior | Current |
|----------|-------|---------|
| `DOWNLOAD_MANIFEST.json` | 85 SEC docs indexed | Stable; all entries `ok: true` |
| `authorized_evidence.json` | Missing | Created; targets extreme-return validation |
| `valuation.json` | Component proof complete; owner earnings cited to OCF tag only; no outlier block | Added `valuation_methodology.outlier_validation`; owner-earnings source reconciled to OCF minus capex |
| Narrative | No filing-grounded deep dive | First dive `deep_dive_2026-08-10.md` |

## Blocker closure: extreme return validation

### Acceptance test — met

| Field | Content |
|---|---|
| status | met |
| evidence | `valuation_methodology.outlier_validation.status` = `passed`; two independent methods with filing refs |
| source path | `COHR/research/valuation.json` |
| calculation | **Method 1 (component economic value):** owner-earnings reinvestment DCF proof base **$15.09/sh** at price **$285.40** → contract annualized return **−34.3%** over 7 years. **Method 2 (Lawrence owner-cash IRR):** normalized starting owner cash **$0.99/sh** (FY2025 operating cash flow **$633.6M** minus capital spending **$440.8M**, scaled to **195.6M** shares) at **$285.40** → synthesis **−31.1%** per year (8% growth years 1–5, 5% years 6–7, 18× exit on year-7 owner cash, 10% discount rate). Depreciation-proxy maintenance capex (**$250.8M**) raises normalized owner cash to **~$383M** (**~$1.96/sh**) and Lawrence IRR to **~−24.0%**; still extreme. |
| remaining uncertainty | Methods diverge in magnitude (−34.3% vs −31.1%) because the component DCF applies reinvestment-at-return mechanics while Lawrence uses growth-to-exit; both independently confirm price far above filing-grounded economics. Market may be capitalizing AI/datacenter transceiver and networking capacity not yet in normalized owner cash. |
| falsifier | Sustained normalized owner cash above **$3.00/sh** on FY2026–FY2027 filings without proportional debt or share issuance; or signed hyperscaler supply agreements with disclosed economics that raise normalized owner earnings above **$600M** annually. |

### Owner-cash reconciliation — met

| Field | Content |
|---|---|
| status | met |
| evidence | Prior proof labeled owner earnings from OCF tag alone; corrected to OCF **$633.6M** minus capex **$440.8M** = **$192.8M** |
| source path | `COHR/investor-documents/sec-edgar/10-K_20250815_rpt20250630_acc0000820318_25_000014.htm` |
| calculation | FY2025 cash flow statement: operating cash flow **$633.6M** less property-plant-and-equipment additions **$440.8M** = **$192.8M** conservative normalized owner earnings. PP&E depreciation **$250.8M** is an alternative maintenance proxy yielding **~$383M**; base proof uses total capex to stay conservative while Networking segment capex is growth-heavy. |
| remaining uncertainty | Filings do not split maintenance vs growth capex; **[HUMAN REVIEW]** if segment capital bridge should move base normalization toward depreciation proxy. |
| falsifier | FY2026 10-K discloses maintenance capex below **$300M** while total capex stays above **$500M**, supporting depreciation proxy over total-capex subtraction. |

### Component proof completeness — unchanged structure, met

Single additive component `operating_business_and_net_assets` retains valid `calculation_proof` graph (`owner_earnings_reinvestment_dcf@1.0`). Overlap key `entire_security` non-overlapping; `double_counting_flags` empty.

## Facts vs judgments

**Facts (locked):** FY2025 revenue **$5.81B**; operating cash flow **$633.6M**; capital spending **$440.8M**; normalized owner earnings **$192.8M** (OCF minus capex); cash **$2.23B** (Q1 2026); debt **$3.18B** (Q1 2026); shares **195.6M** (May 2026); price **$285.40** (Yahoo close 2026-07-20).

**Judgments (bounded):** Reinvestment rate 20–50%; incremental after-tax return on capital 12–25%; discount rate 9–12%; terminal owner-earnings multiple 12–24×.

## Valuation consequence

Proof-complete additive schedule base **$15.09 per share** vs **$285.40** price. Lawrence synthesis **−31.1%** per year on conservative normalization. Both methods validate extreme negative return at current quote. Security remains **watch**; no human capital decision recorded.
