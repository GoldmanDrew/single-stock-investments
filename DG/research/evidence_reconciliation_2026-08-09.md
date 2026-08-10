# DG valuation evidence reconciliation — 2026-08-09

**Scope:** Contract backfill. Close contract blocker: stale debt source fact (2022-10-28). Evidence packet per `research_agent_manifest.json`.

## What changed since 2026-07-29

| Artifact | Prior | Current |
|----------|-------|---------|
| `DOWNLOAD_MANIFEST.json` | 71 SEC docs indexed | Stable; manifest hash unchanged |
| `valuation_fact_ledger.json` | `debt_m` **$5,986M** from 2022 `LongTermDebtNoncurrent` tag | **$4,576M** from Q1 FY2026 total debt and lease obligations |
| `valuation.json` | Same stale debt in calculation_proof | Debt fact refreshed to Q1 2026 10-Q; proof graph unchanged otherwise |
| `valuation_contract.json` | `source_identity_and_freshness_valid: false` | **Target:** pass after rebuild |
| Narrative | No deep dive | First filing-grounded dive `deep_dive_2026-08-09.md` |

## Blocker closure: stale debt fact

### Acceptance test — met

| Field | Content |
|---|---|
| status | met |
| evidence | `LongTermDebtAndCapitalLeaseObligations` **$4,563M** plus `LongTermDebtAndCapitalLeaseObligationsCurrent` **$13M** = **$4,576M** at **2026-05-01**; accession **0001104659-26-069205** (Q1 FY2026 10-Q) |
| source path | `DG/research/evidence/sec_companyfacts.json` |
| calculation | Prior proof used `LongTermDebtNoncurrent` **$5,986M** (2022-10-28), overstating leverage by **~$1.4 billion** versus the latest filing. Updated debt input increases equity value per share by **~$6.40** at unchanged owner-earnings assumptions. |
| remaining uncertainty | Single debt line sums long-term and current capital-lease obligations; operating lease liabilities remain off the debt bridge. **[HUMAN REVIEW]** if lease-adjusted leverage matters for stance. |
| falsifier | Q2 FY2026 10-Q shows total debt above **$5.2B** without a disclosed issuance, or a restatement changes the Q1 FY2026 debt note. |

### Component proof completeness — unchanged structure, met

Single additive component `operating_business_and_net_assets` retains valid `owner_earnings_reinvestment_dcf@1.0` calculation_proof. Overlap key `entire_security` non-overlapping; `double_counting_flags` empty.

## Facts vs judgments

**Facts (locked):** FY2025 revenue **$42.7B**; FY2025 operating cash flow **$3.63B**; FY2025 capital spending **$1.24B**; normalized owner earnings **$2.39B** (operating cash flow minus capital spending); cash **$1.35B** (Q1 FY2026, includes restricted cash per XBRL tag); total debt **$4.58B** (Q1 FY2026); shares **220.6M** (Q1 FY2026); price **$124.75** (Yahoo close 2026-07-20).

**Judgments (bounded):** Reinvestment rate 20–50%; incremental after-tax return on capital 12–25%; discount rate 9–12%; terminal owner-earnings multiple 12–24×.

## Valuation consequence

Proof-complete base value rises to **~$182 per share** (post-debt fix) vs **$124.75** price. Contract annualized return at price improves modestly versus the stale-debt run but remains below a **15%** hurdle on base reinvestment assumptions. Security remains **watch**; no human capital decision recorded.
