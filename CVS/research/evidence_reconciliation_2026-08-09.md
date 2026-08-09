# CVS valuation evidence reconciliation — 2026-08-09

**Scope:** Contract backfill. Close `authorized_evidence.json` blocker: stale debt source fact (2020-06-30). Evidence packet per `research_agent_manifest.json`.

## What changed since 2026-07-29

| Artifact | Prior | Current |
|----------|-------|---------|
| `DOWNLOAD_MANIFEST.json` | 63 SEC docs indexed | Stable; manifest hash unchanged |
| `valuation_fact_ledger.json` | `debt_m` **$63,481M** from 2020 `LongTermDebtNoncurrent` tag | **$63,111M** from Q1 2026 total debt and lease obligations |
| `valuation.json` | Same stale debt in calculation_proof | Debt fact refreshed to 2026-03-31 10-Q; proof graph unchanged otherwise |
| `valuation_contract.json` | `source_identity_and_freshness_valid: false` | **Target:** pass after rebuild |
| Narrative | No deep dive | First filing-grounded dive `deep_dive_2026-08-09.md` |

## Blocker closure: stale debt fact

### Acceptance test — met

| Field | Content |
|---|---|
| status | met |
| evidence | Q1 2026 10-Q: `LongTermDebtAndCapitalLeaseObligations` **$60,531 million** plus `LongTermDebtAndCapitalLeaseObligationsCurrent` **$2,580 million** = **$63,111 million** total; accession **0000064803-26-000052** |
| source path | `CVS/research/evidence/sec_companyfacts.json` |
| calculation | Prior proof used `LongTermDebtNoncurrent` **$63,481M** (2020-06-30), a stale tag that blocked contract freshness checks despite a similar nominal amount. Updated debt input uses the same measurement date as cash (**2026-03-31**). Base equity value per share moves from **~$68.92** to **~$69.21** at unchanged owner-earnings assumptions. |
| remaining uncertainty | Total debt includes capital lease obligations; segment-level debt attribution (Health Care Benefits vs Pharmacy) not modeled in the single-component proof. **[HUMAN REVIEW]** if leverage stance depends on Aetna-specific debt. |
| falsifier | Q2 2026 10-Q shows total debt above **$70B** without a disclosed acquisition, or a restatement changes the Q1 2026 debt note. |

### Component proof completeness — unchanged structure, met

Single additive component `operating_business_and_net_assets` retains valid `owner_earnings_reinvestment_dcf@1.0` calculation_proof. Overlap key `entire_security` non-overlapping; `double_counting_flags` empty.

## Facts vs judgments

**Facts (locked):** FY2025 revenue **$402.1B**; FY2025 operating cash flow **$10.639B**; FY2025 capital spending **$2.832B**; normalized owner earnings **$7.807B** (operating cash flow minus capital spending); cash **$9.769B** (Q1 2026); total debt **$63.111B** (Q1 2026); shares **1,275.9M** (Q1 2026); price **$107.61** (Yahoo close 2026-07-20).

**Judgments (bounded):** Reinvestment rate 20–50%; incremental after-tax return on capital 12–25%; discount rate 9–12%; terminal owner-earnings multiple 12–24×.

## Valuation consequence

Proof-complete base value **~$69 per share** (post-debt refresh) vs **$107.61** price. Contract annualized return at price remains **negative** on base case. Security remains **watch**; no human capital decision recorded.
