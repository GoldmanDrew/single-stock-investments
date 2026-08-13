# DOC — Cross-Check: Third-Party Sources

**Date:** 2026-08-13  
**Agent:** Marvin  
**Marvin dive:** `DOC/research/deep_dive_2026-08-13.md`  
**Source inventory:** `DOC/third-party-analyses/source_inventory_2026-08-02.md`  
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

No approved third-party analyses are indexed for Healthpeak Properties as of this scan. Activist SC 13G filings in `third-party-analyses/activist_reports/long/` are **context tier** only (passive holder disclosures, not investment theses). Marvin stance rests on **primary SEC filings** (FY2025 10-K, Q1 2026 10-Q, 2026 proxy).

**Synthesis:** Marvin floor only; no external blend into base case.

## Sources in scope

| ID | Title | Path | Status | Use |
|----|-------|------|--------|-----|
| — | Primary filings only | `DOC/investor-documents/sec-edgar/` | primary | Base IRR / contract proofs |
| ACT-ctx | SC 13G/A passive holder filings | `DOC/third-party-analyses/activist_reports/long/` | context | Ownership history only |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| Portfolio scale | 689 properties across outpatient medical, lab, senior housing | — | `10-K_20260203` segment note |
| FY2025 revenue | $2.82 billion | — | `filing_facts_2026-08-06.json` |
| Janus Living spin | Draft S-11 filed; senior housing contribution planned | — | `10-K_20260203` Item 1 |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| — | — | — | No approved external return path |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor (contract) | **$0/sh** base after limited-liability floor (−$3.89/sh raw) | Pending Lawrence synthesis refresh | watch |
| External (combined) | — | — | — |
| **Blended best estimate** | **$0/sh** (contract base) | **Pending** | **watch** |

**Weights:** 100% primary filings; no approved third party in base.

**Returns statement (blended):** Base case follows proof-first component math only; no external views in base IRR.

## [HUMAN REVIEW]

- [ ] Re-run `scan_third_party_sources.py DOC --with-hk` when Substacks or fund letters are added.
- [ ] Activist filings remain context; do not promote to `third_party_sources.md` without human approval.

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] DOC: third-party cross-check 2026-08-13 — primary filings only; contract base $0/sh with zero_value_policy liquidation_shortfall.

## Primary sources cited

1. `DOC/investor-documents/sec-edgar/10-K_20260203_rpt20251231_acc0001628280_26_005044.htm`
2. `DOC/investor-documents/sec-edgar/10-Q_20260506_rpt20260331_acc0001628280_26_031287.htm`
3. `DOC/research/evidence/filing_digest_2026-08-06.md`
