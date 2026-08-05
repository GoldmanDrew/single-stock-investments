# AAL — Cross-Check: Third-Party Sources

**Date:** 2026-08-04  
**Agent:** Marvin (contract backfill)  
**Marvin dive:** `AAL/research/deep_dive_2026-08-04.md`  
**Source inventory:** `AAL/third-party-analyses/source_inventory_2026-07-20.md`  
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

This refresh closes the universal contract blocker by documenting an explicit **zero value policy** for the filing-locked base component sum (**−$9.79** per share pre-floor, **$0** per share after limited-liability floor). Marvin base IRR and proof-first components remain anchored to FY2025 10-K and Q1 2026 10-Q. Historical Berkshire SC 13G filings (2018–2019, exited 2020) are **context only**; no approved third-party source is in base IRR.

**Synthesis (best estimate):** Marvin filing-first base · stance **watch**; external sources adjust historical ownership narrative only, not primary IRR without human OK.

## Sources in scope

| Source ID | Title | Path | Status | Cross-check status |
|-----------|-------|------|--------|-------------------|
| activist_long | Berkshire / institutional SC 13G series (2018–2024) | `AAL/third-party-analyses/activist_reports/long/` | context | ownership history only |

No approved Substack or HK commentary indexed for AAL.

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| Leveraged balance sheet | ~$29B debt vs $902M cash FY2025 | Institutional holders tracked in SC 13G | 10-K FY2025 |
| Post-pandemic recovery | Revenue ~$54.6B FY2025 | Industry recovery narrative aligns | 10-K FY2025 |
| Base return anchor | Lawrence / synthesis from `valuation.json` | No approved numeric IRR | `valuation.json` |
| Zero value policy | Base component sum negative; equity floored at $0 | Market ~$15 embeds high-case recovery | `valuation.json` zero_value_policy |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| Primary IRR | Filing-locked Lawrence path | No approved external IRR | Marvin **100%** numeric until human promotes |
| Component value | **−$9.79/sh** pre-floor; **$0/sh** base after floor | Market **~$15** embeds deleveraging option | Gap is cycle timing and equity stub, not filing error |
| Third party | Filing-first | Context tier only | No numeric upgrade without human OK |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | **$4.70/sh** OCF proxy; **$0/sh** base components (floored) | Mechanical refresh computes IRR | **watch** |
| External (combined) | Narrative / ownership history | No change to base % | **watch** (conviction) |
| **Blended best estimate** | **Filing anchor** | **Mechanical Lawrence / synthesis** | **watch** |

**Weights:** Marvin **100%** on numbers; indexed third party **0%** numeric (context on historical Berkshire stake and institutional ownership only).

**Returns statement (blended):** Base annual return is computed mechanically from filing-grounded assumptions in Phase 3; pending third-party sources do not replace filing math without **[HUMAN REVIEW]**.

## [HUMAN REVIEW]

- [ ] Confirm no approved third-party source should enter base IRR
- [ ] Review whether historical Berkshire exit (2020) remains relevant to current thesis
- [ ] Confirm zero_value_policy outcome `liquidation_shortfall` matches committee framing for levered stub

## Primary sources cited

1. `AAL/investor-documents/sec-edgar/10-K_20260218_rpt20251231_acc0000006201_26_000014.htm`
2. `AAL/investor-documents/sec-edgar/10-Q_20260423_rpt20260331_acc0000006201_26_000032.htm`
3. `AAL/research/valuation.json`
4. `AAL/research/evidence_reconciliation_2026-07-21.md`
