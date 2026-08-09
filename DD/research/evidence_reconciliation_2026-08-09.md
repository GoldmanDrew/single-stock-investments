# DD valuation evidence reconciliation — 2026-08-09

**Scope:** Contract backfill. Close `valuation_contract.json` blocker: stale debt source fact (2024-09-30 `LongTermDebt` tag). Evidence packet per `research_agent_manifest.json`.

## What changed since 2026-07-29

| Artifact | Prior | Current |
|----------|-------|---------|
| `DOWNLOAD_MANIFEST.json` | Indexed SEC docs | Stable; manifest is the authorized changed artifact |
| `valuation_fact_ledger.json` | `debt_m` **$7,170M** from 2024 Q3 `LongTermDebt` | **$3,194M** = FY2025 `LongTermDebtAndCapitalLeaseObligations` **$3,134M** + `DebtCurrent` **$60M** |
| `valuation.json` / contract | Base equity value **negative** (−$5.61/sh base component) | **Target:** positive base equity after debt refresh |
| Narrative | No deep dive on disk | First filing-grounded dive `deep_dive_2026-08-09.md` |

## Blocker closure: stale debt fact

### Acceptance test — met

| Field | Content |
|---|---|
| status | met |
| evidence | `us-gaap:LongTermDebtAndCapitalLeaseObligations` **$3,134 million** and `us-gaap:DebtCurrent` **$60 million** at **2025-12-31**; accession **0001666700-26-000013** (FY2025 10-K). Q1 2026 10-Q confirms **$3,132M** long-term debt and **$40M** current debt at **2026-03-31**. |
| source path | `DD/research/evidence/sec_companyfacts.json` |
| calculation | Prior proof used standalone `LongTermDebt` **$7,170M** (2024-09-30), overstating leverage by **~$3.98 billion** versus post-separation filings. Updated total debt flows through the equity bridge: base equity value per share rises from **−$5.61** to **~$4.09** at unchanged owner-earnings and reinvestment judgments. |
| remaining uncertainty | Single-component proof uses consolidated owner earnings after major 2025 Electronics separation; segment-level reinvestment not yet split. **[HUMAN REVIEW]** if stance should reflect Healthcare & Water vs Diversified Industrials separately. |
| falsifier | FY2026 10-K or Q2 2026 10-Q shows total debt above **$4.5B** without a disclosed acquisition, or a restatement changes the FY2025 debt note. |

### Component proof completeness — unchanged structure, met

Single additive component `operating_business_and_net_assets` retains valid `owner_earnings_reinvestment_dcf@1.0` calculation_proof. Overlap key `entire_security` non-overlapping; `double_counting_flags` empty.

## Facts vs judgments

**Facts (locked):** FY2025 revenue **$6.849B**; FY2025 operating cash flow **$560M**; FY2025 capital spending **$333M**; normalized owner earnings **$227M** (OCF minus capex); cash **$752M** (Q1 2026); total debt **$3.194B** (FY2025 LT + current); shares **409.9M** (Q1 2026); price **$135.75** (Yahoo close 2026-07-20).

**Judgments (bounded):** Reinvestment rate 20–50%; incremental after-tax return on capital 12–25%; discount rate 9–12%; terminal owner-earnings multiple 12–24×.

## Valuation consequence

Proof-complete base value **~$4.09 per share** (post-debt fix) vs **$135.75** price. Contract annualized return at price remains **deeply negative** on base case. Security remains **watch**; no human capital decision recorded. Zero-value policy not required once base equity value is positive under refreshed debt.
