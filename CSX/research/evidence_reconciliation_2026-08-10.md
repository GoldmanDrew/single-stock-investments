# CSX valuation evidence reconciliation — 2026-08-10

**Scope:** Contract backfill. Close stale-debt blocker on `operating_business_and_net_assets`. Evidence packet per `research_agent_manifest.json`.

## What changed since 2026-07-29

| Artifact | Prior | Current |
|----------|-------|---------|
| `DOWNLOAD_MANIFEST.json` | 67 SEC docs indexed | Stable; manifest hash authorized for this run |
| `valuation_fact_ledger.json` | `debt_m` **$9,832M** from 2012 `LongTermDebt` tag | **$18,864M** (current + non-current lease-adjusted debt at June 2026) |
| `valuation.json` | Same stale debt in calculation_proof | Debt fact refreshed; proof graph unchanged otherwise |
| `valuation_contract.json` | `source_identity_and_freshness_valid: false` | **Target:** pass after rebuild |
| Narrative | No deep dive on disk | First filing-grounded dive `deep_dive_2026-08-10.md` |

## Blocker closure: stale debt fact

### Acceptance test — met

| Field | Content |
|---|---|
| status | met |
| evidence | `LongTermDebtAndCapitalLeaseObligationsCurrent` **$1,702 million** plus `LongTermDebtAndCapitalLeaseObligations` **$17,162 million** at **2026-06-30**; accession **0000277948-26-000032** (Q2 2026 10-Q) |
| source path | `CSX/research/evidence/sec_companyfacts.json` |
| calculation | Prior proof used `LongTermDebt` **$9,832M** (2012-12-28), understating leverage by **~$9.0 billion**. Updated total debt flows through the equity bridge: base equity value per share falls from **~$12.0** to **~$7.1** at unchanged owner-earnings assumptions. |
| remaining uncertainty | Total debt sums current and non-current lease-adjusted obligations; operating-lease liability separate from debt bridge is not modeled. **[HUMAN REVIEW]** if lease capitalization treatment should net against enterprise value differently. |
| falsifier | Q3 2026 10-Q shows total debt below **$17.5B** without a disclosed repayment program, or a restatement changes the June 2026 debt note. |

### Component proof completeness — unchanged structure, met

Single additive component `operating_business_and_net_assets` retains valid `owner_earnings_reinvestment_dcf@1.0` calculation_proof. Overlap key `entire_security` non-overlapping; `double_counting_flags` empty.

## Facts vs judgments

**Facts (locked):** FY2025 revenue **$14.09B**; FY2025 operating cash flow **$4.61B**; FY2025 capital spending **$2.90B**; normalized owner earnings **$1.71B** (operating cash flow minus capital spending); cash **$1.01B** (Q2 2026); total debt **$18.86B** (Q2 2026); shares **1.85B** (Q2 2026); price **$50.11** (Yahoo close 2026-07-20).

**Judgments (bounded):** Reinvestment rate 20–50%; incremental after-tax return on capital 12–25%; discount rate 9–12%; terminal owner-earnings multiple 12–24×.

## Valuation consequence

Proof-complete base value falls to roughly **$7 per share** (post-debt fix) vs **$50.11** price. Contract annualized return at price remains **negative** on base case and becomes more negative versus the stale-debt run because leverage was materially understated. Security remains **watch**; no human capital decision recorded.
