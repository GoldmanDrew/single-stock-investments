# DVA — Cross-Check: Third-Party Sources

**Date:** 2026-08-13
**Agent:** Marvin
**Marvin dive:** `DVA/research/deep_dive_2026-08-13.md`
**Source inventory:** `DVA/third-party-analyses/source_inventory_2026-08-02.md`
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

Eleven Berkshire Hathaway SC-13D/A filings are indexed as **context tier** activist/long ownership records. None are approved in `_system/frameworks/third_party_sources.md`. Marvin stance rests on **primary filings** (10-K, 10-Q). Re-run `scan_third_party_sources.py` when Substacks, fund letters, or HK material is added.

**Synthesis:** Marvin floor only; no external blend in base IRR.

## Sources in scope

| ID | Title | Path | Status | Use |
|----|-------|------|--------|-----|
| activist_long | Berkshire Hathaway SC-13D/A (series) | `DVA/third-party-analyses/activist_reports/long/` | context | Ownership history; not in base IRR |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| Scale | Largest U.S. dialysis provider; FY2025 revenue **$13.64B** | Berkshire maintained large stake over multiple years | 10-K; SC-13D/A index |
| Leverage | Q1 2026 debt **~$10.5B** | Activist filings do not dispute leverage; focus on operations | 10-Q |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| Valuation / return | Base proof **$218/sh**; **2.84%** annual return at **$179.17** | Berkshire stake may imply longer horizon or private-market view of quality | **No blend** — context only until human approves a source |
| Moat | **Unproven** on reimbursement | Activist sponsorship suggests durable business | Flag **[HUMAN REVIEW]**; do not auto-upgrade moat |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | **$218/sh** base proof | **2.84%** per year (7yr) | watch |
| External (combined) | n/a | n/a | context only |
| **Blended best estimate** | **Marvin floor** | **2.84%** per year | **watch** |

**Weights:** 100% Marvin primary proof; 0% external (no approved sources).

**Returns statement (blended):** Same as Marvin base — **2.84% per year** at **$179.17**; pending sources not in base IRR.

## [HUMAN REVIEW]

- [ ] Every **approved** source reviewed against filings
- [ ] Every **pending** source cited with **[PENDING APPROVAL]** only
- [ ] Blended estimate in `valuation.json` → `estimates.external[]` if material

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] DVA: third-party cross-check 2026-08-13 — Berkshire SC-13D/A context only

## Primary sources cited

1. `DVA/research/deep_dive_2026-08-13.md`
2. `DVA/third-party-analyses/source_inventory_2026-08-02.md`
3. `DVA/investor-documents/sec-edgar/10-K_20260211_rpt20251231_acc0000927066_26_000012.htm`
4. `DVA/investor-documents/sec-edgar/10-Q_20260505_rpt20260331_acc0000927066_26_000062.htm`
