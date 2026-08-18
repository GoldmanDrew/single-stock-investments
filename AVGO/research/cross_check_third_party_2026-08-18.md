# AVGO — Cross-Check: Third-Party Sources

**Date:** 2026-08-18
**Agent:** Marvin
**Marvin dive:** `AVGO/research/deep_dive_2026-08-18.md`
**Source inventory:** `AVGO/third-party-analyses/source_inventory_2026-08-02.md`
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

No third-party sources are indexed for AVGO as of **2026-08-18**. The latest scan (`source_inventory_2026-08-02.md`) lists **0** approved, **0** pending, and **0** context research notes. SC-13G beneficial-ownership filings exist under `third-party-analyses/activist_reports/long/` but are ownership disclosures, not investment research, and are excluded from return blending per `third_party_sources.md`.

**Synthesis:** Marvin floor only; no external blend. Base annual return **-18.08%** per year at **$378.16** rests entirely on primary filings and the decision-grade valuation contract (`AVGO/research/valuation_contract.json`). Re-run `scan_third_party_sources.py AVGO --with-hk` when Substacks, fund letters, or HK commentaries are added.

## Sources in scope

| ID | Title | Path | Status | Use |
|----|-------|------|--------|-----|
| (none) | Primary filings only | `AVGO/investor-documents/sec-edgar/` | n/a | 10-K, 10-Q, proxy, 424B5 debt filings |
| context | SC-13G ownership filings | `AVGO/third-party-analyses/activist_reports/long/` | context | Institutional ownership; not research |

Every inventory row reviewed: there are no approved or pending research sources to triangulate.

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| FY2025 revenue scale | **$63.9B** consolidated; semiconductor **$36.9B**, software **$27.0B** | No external view | FY2025 10-K |
| Cash generation | Operating cash flow **$27.5B** FY2025; free cash flow **~$26.9B** per proxy | No external view | FY2025 10-K; DEF 14A 2026 |
| Leverage | Long-term debt **~$62B** | No external view | FY2025 10-K; Q2 FY2026 10-Q |
| AI backlog | RPO **~$164.6B** including custom AI accelerator contract | No external view | Q2 FY2026 10-Q |

With no external research indexed, agreements table documents filing facts only.

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| Normalized owner earnings | **$26.9B** operating cash flow anchor | — | No external normalization to compare |
| Terminal / reinvestment | Bounded contract assumptions (35% reinvestment, 18% incremental return) | — | No sell-side or fund letter to challenge |
| Stance | **watch** at **-18.08%** base return | — | No external stance to reconcile |

No divergences until an approved or pending source is indexed and reviewed.

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor (filings + contract) | Base **~$93.60/sh** | **-18.08%** per year / 7 years | watch |
| External (combined) | — | — | — |
| **Blended best estimate** | **~$93.60/sh** (base) | **-18.08%** per year | **watch** |

**Weights:** 100% Marvin filing floor; 0% external (no indexed sources).

**Returns statement (blended):** With no approved third party, the best estimate equals the Marvin contract base: **-18.08%** per year at **$378.16** over seven years. Pending sources, if added later, require **[PENDING APPROVAL]** citation and must not enter `valuation.json` base without human OK.

## [HUMAN REVIEW]

- [ ] Every **approved** source reviewed against filings (none indexed)
- [ ] Every **pending** source cited with **[PENDING APPROVAL]** only (none indexed)
- [ ] Blended estimate in `valuation.json` → `estimates.external[]` if material third party is promoted
- [ ] Re-run scan after adding Substacks or research-note PDFs to `third-party-analyses/`

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] AVGO: third-party cross-check 2026-08-18 — Marvin floor only; no approved external; base return **-18.08%** unblended

## Primary sources cited

1. `AVGO/research/deep_dive_2026-08-18.md`
2. `AVGO/third-party-analyses/source_inventory_2026-08-02.md`
3. `AVGO/investor-documents/sec-edgar/10-K_20251218_rpt20251102_acc0001730168_25_000121.htm`
4. `AVGO/investor-documents/sec-edgar/10-Q_20260609_rpt20260503_acc0001730168_26_000054.htm`
5. `AVGO/research/valuation_contract.json`
6. `AVGO/research/pricing_analysis.json`
