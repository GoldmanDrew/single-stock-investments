# CNC — Cross-Check: Third-Party Sources

**Date:** 2026-09-02
**Agent:** Marvin
**Marvin dive:** `CNC/research/deep_dive_2026-09-02.md`
**Source inventory:** `CNC/third-party-analyses/source_inventory_2026-08-26.md`
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

No **approved** third-party sources exist for Centene in `_system/frameworks/third_party_sources.md` as of this date. The indexed inventory contains one **context-tier** activist filing (2021 DFAN14A) and multiple SC-13G ownership disclosures. Mechanical SSI packs (`CNC/research/ssi_report_2026-08-07.md`) are **[PENDING APPROVAL]** and are not folded into base IRR.

**Synthesis:** Marvin floor only for base return (**6.6% per year** at **$64.34**). Pending and context sources inform monitoring but do not adjust the stance gate.

## Sources in scope

| ID | Title | Path | Status | Reviewed? |
|----|-------|------|--------|-----------|
| activist_long | Centene Corporation — DFAN14A (proxy solicitation) | `CNC/third-party-analyses/activist_reports/long/DFAN14A_20210104_acc0001140361_21_000089.htm` | context | Skimmed; 2021 governance pressure, stale for current HBR thesis |
| sc13g_series | Institutional ownership SC-13G/A filings | `CNC/third-party-analyses/activist_reports/long/` | context | Not material to cash-flow model |
| ssi_pack | SSI mechanical report 2026-08-07 | `CNC/research/ssi_report_2026-08-07.md` | **[PENDING APPROVAL]** | Reviewed for KPI table; not in base IRR |
| approved_registry | — | `_system/frameworks/third_party_sources.md` | none for CNC | Confirmed absent |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| Revenue scale | FY2025 revenue **$194.8B** | SSI pack cites same XBRL tag | FY2025 10-K; `ssi_report_2026-08-07.md` |
| FY2025 loss driver | **$6.7B** goodwill impairment (Magellan Health) | SSI pack flags impairment magnitude | FY2025 10-K Note 7 |
| Cash generation | FY2025 OCF **$5.09B**; H1 2026 OCF **$7.96B** | SSI pack lists OCF series | 10-K / Q2 2026 10-Q |
| Medicaid redetermination | Membership decline and higher acuity on remaining book | Filings-only; no approved external deep dive | FY2025 10-K MD&A |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| Base annual return | **6.6% per year** (owner-earnings DCF) | SSI draft cited higher contract range before stock-specific review | Use filing-grounded `valuation_contract.json`; ignore stale SSI return labels |
| Moat | **unproven** (HBR and rate-cycle risk) | Activist 2021 emphasized governance, not medical-cost mechanics | No blend; context only |
| Stance | **watch / pass** below **~15%** hurdle | No approved external stance | Marvin floor governs |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | **$4.3B** normalized owner earnings; **$100.72/sh** base intrinsic | **6.6% per year** over 7 years | **watch / pass** |
| External (combined) | Not in base IRR | — | — |
| **Blended best estimate** | **Marvin floor only** | **6.6% per year** | **watch / pass** |

**Weights:** 100% Marvin primary filings; 0% approved third party.

**Returns statement (blended):** Base case **6.6% per year** at **$64.34** rests on SEC filings only; no approved external view adjusts the base case.

## [HUMAN REVIEW]

- [ ] No approved CNC entry in `third_party_sources.md`; do not promote SSI or activist material into base IRR without human approval
- [ ] Re-run `scan_third_party_sources.py CNC --with-hk` when Substacks or fund letters are added
- [ ] Blended estimate does not update `valuation.json` → `estimates.external[]` (no approved sources)

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] CNC: third-party cross-check 2026-09-02 confirms Marvin floor only; DFAN14A 2021 is context tier

## Primary sources cited

1. `CNC/research/deep_dive_2026-09-02.md`
2. `CNC/third-party-analyses/source_inventory_2026-08-26.md`
3. `CNC/investor-documents/sec-edgar/10-K_20260217_rpt20251231_acc0001071739_26_000049.htm`
4. `CNC/investor-documents/sec-edgar/10-Q_20260728_rpt20260630_acc0001071739_26_000153.htm`
5. `CNC/research/valuation_contract.json`
