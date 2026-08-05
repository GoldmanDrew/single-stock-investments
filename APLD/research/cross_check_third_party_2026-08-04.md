# APLD — Cross-Check: Third-Party Sources

**Date:** 2026-08-04  
**Agent:** Marvin (Cloud refresh — universal contract upgrade)  
**Marvin dive:** `APLD/research/deep_dive_2026-08-04.md`  
**Source inventory:** `APLD/third-party-analyses/source_inventory_2026-06-01.md` (no new third-party downloads this run)  
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

Lawrence base **13.12%** per year (scenario synthesis; stance **watch**) unchanged this run. Contract backfill closed the **zero_value_policy** blocker: base proof sum **−$1.27/sh** is explicitly floored at **$0/sh** under **liquidation_shortfall**; contract status **decision_grade**. Third-party sources remain **context** for catalyst timing only.

**Synthesis (best estimate):** Marvin **13.12%** base · stance **watch**; external sources adjust conviction on energization timing, not primary IRR.

## Sources in scope

| Source ID | Title | Path | Status | Cross-check |
|-----------|-------|------|--------|-------------|
| apld_pf3_summary | PF3 / portfolio lease summary | `APLD/investor-documents/research-notes/2026-05-20_Polaris_Forge_3_lease_summary.md` | approved | Used as **estimate** tier in contracted_expansion and uncontracted_option proofs |
| apld_reiterate_buy | Run-the-table bull case PDF | `APLD/investor-documents/research-notes/What Would A Run The Table Scenario Look Like_ Reiterate BUY.pdf` | approved | Bull framing only; not in base proof |
| wolfpack_2023-07 | Short report | `APLD/third-party-analyses/short_reports/wolfpack_2023-07.md` | context | Inversion context only |
| activist_index | Activist / short report index | `APLD/third-party-analyses/activist_reports_index.json` | context | Index only; no new Tier-1 report cited |

## Agreements

| Topic | Marvin (filings + proofs) | External | Source |
|-------|---------------------------|----------|--------|
| Lease backlog scale | ~$31B base contracted (estimate node in proof) | PF3 PR aligns | `2026-05-20_Polaris_Forge_3_lease_summary.md` |
| Catalyst stack | PF1–3 + Delta Forge energization | Bull note run-the-table | Approved PDF (context) |
| Capital structure risk | Senior-claim multiplier on GAAP net debt | Short reports flag related-party history | 10-K; wolfpack (context) |

## Divergences

| Topic | Marvin | External | Blend |
|-------|--------|----------|-------|
| Base IRR | **13.12%** Lawrence synthesis | Bull note higher if full ramp | Marvin numeric anchor; external **25%** weight on PF3 timing only (already in `valuation.json` blend) |
| Component proof vs legacy | Proof sum base **-$1.28/sh** vs legacy scaffold **+$30/sh** | External bull cases closer to legacy | Proofs are filing-conservative; legacy retained as sensitivity |

## Missing data

- No new Substack/HK extracts this run.
- Filed reconciliation of $31B contracted revenue to 10-K/10-Q segment note still **[HUMAN REVIEW]**.

## Synthesis (best estimate)

| Lens | Return / value | Stance |
|------|----------------|--------|
| Marvin Lawrence base | **13.12%** per year | **watch** |
| Component proofs (economic value) | Base **−$1.27/sh** sum → **$0/sh** floor | Evidence context; zero_value_policy **liquidation_shortfall** |
| External (approved) | Catalyst timing | **watch** |

**Weights:** Unchanged from `valuation.json` synthesis paths; third party not added to proof graphs.
