# DVA valuation evidence reconciliation — 2026-08-13

**Scope:** Contract backfill. Close `valuation_contract.json` blocker: stale debt source fact (2014-12-31). Evidence packet per `research_agent_manifest.json`.

## What changed since 2026-07-29

| Artifact | Prior | Current |
|----------|-------|---------|
| `DOWNLOAD_MANIFEST.json` | 72+ SEC docs indexed | Stable; all entries `ok: true` |
| `valuation_fact_ledger.json` | `debt_m` **$8,503M** from 2014 `LongTermDebt` tag | **$10,694M** from Q1 2026 `DebtInstrumentCarryingAmount` |
| `valuation.json` | Same stale debt in calculation_proof | Debt fact refreshed; proof graph unchanged otherwise |
| `valuation_contract.json` | `source_identity_and_freshness_valid: false` | **Target:** pass after rebuild |
| Narrative | No deep dive on disk | First filing-grounded dive `deep_dive_2026-08-13.md` |

## Blocker closure: stale debt fact

### Acceptance test — met

| Field | Content |
|---|---|
| status | met |
| evidence | `us-gaap:DebtInstrumentCarryingAmount` **$10,694 million** at **2026-03-31**; accession **0000927066-26-000062** (Q1 2026 10-Q). Cross-check: `LongTermDebtAndCapitalLeaseObligations` **$10,514M** plus current portion **$113M** on same filing. |
| source path | `DVA/research/evidence/sec_companyfacts.json` |
| calculation | Prior proof used `LongTermDebt` **$8,503M** (2014-12-31), **understating** leverage by **~$2.2 billion** versus Q1 2026 filings. Updated debt input flows through equity bridge: base equity value per share falls from **~$249** to **~$215** at unchanged owner-earnings assumptions (exact figures from post-refresh contract). |
| remaining uncertainty | `DebtInstrumentCarryingAmount` is total debt carrying amount; operating lease liabilities are separate (~$2.6B ROU stack). Dialysis reimbursement and leverage covenants are not modeled as separate proof components. **[HUMAN REVIEW]** if stance depends on Medicare rate sensitivity. |
| falsifier | Q2 2026 10-Q shows debt below **$9.5B** without a disclosed repayment program, or a restatement changes the Q1 2026 debt note. |

### Component proof completeness — unchanged structure, met

Single additive component `operating_business_and_net_assets` retains valid `owner_earnings_reinvestment_dcf@1.0` calculation_proof. Overlap key `entire_security` non-overlapping; `double_counting_flags` empty.

## Facts vs judgments

**Facts (locked):** FY2025 revenue **$13.64B**; FY2025 operating cash flow **$1.887B**; FY2025 capital spending **$0.576B**; normalized owner earnings **$1.311B** (OCF minus capex); cash **$726M** (Q1 2026); debt **$10.694B** (Q1 2026 carrying amount); shares **64.2M** (Q1 2026); price **$234.10** (Yahoo close 2026-07-20, refreshed by pipeline).

**Judgments (bounded):** Reinvestment rate 20–50%; incremental after-tax return on capital 12–25%; discount rate 9–12%; terminal owner-earnings multiple 12–24×.

## Valuation consequence

Proof-complete base value **falls materially** after debt refresh versus the stale-2014 run, while price is unchanged in the short window. Contract annualized return at price on base case remains **near zero to modestly negative** (exact % from post-refresh `valuation_contract.json`). Security remains **watch**; no human capital decision recorded.
