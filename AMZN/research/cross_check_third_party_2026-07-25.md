# AMZN — Cross-Check: Third-Party Sources

**Date:** 2026-07-25  
**Agent:** Marvin  
**Marvin dive:** `AMZN/research/deep_dive_2026-07-25.md`  
**Source inventory:** `AMZN/third-party-analyses/source_inventory_2026-07-25.md`  
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

Marvin filing anchor: **3.21%** per year total synthesis (Lawrence scenario gate **1.9%** per year on normalized **$5.35/sh** owner cash) at **$249.99**. The universal contract (decision_grade) prices the operating business at **$11.64/sh** base with **-35.5%** annualized return at spot, reflecting proof-first owner-earnings reinvestment math rather than mid-cycle capex normalization. One third-party source is indexed (VIC PDF, **pending**). No approved external source adjusts base IRR.

**Synthesis (best estimate):** Marvin **3.21%** per year · stance **hold**; pending VIC is context only until promoted in `third_party_sources.md`.

## Sources in scope

| Source ID | Title | Path | Status | Cross-check status |
|-----------|-------|------|--------|-------------------|
| vic | VIC PDF intake — AMZN VIC PDF | `third-party-analyses/vic/vic_pdf_2026-06-18_amzn-vic-pdf_04954f7a79.pdf` | **[PENDING APPROVAL]** | Not reviewed for numeric blend |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| Operating momentum | Q1 2026 net sales **$181.5B** (+17%); AWS **+28%** | n/a (pending) | `10-Q_20260430`; Q1 earnings release |
| Capital intensity | TTM OCF **$148.5B**; TTM capex **$147.3B**; FCF **$1.2B** | n/a | Q1 supplemental metrics |
| Normalization | Lawrence base uses **$5.35/sh** mid-cycle owner cash, not TTM FCF | n/a | `valuation.json` legacy scenarios |
| Download completeness | **56** SEC filings in manifest, all `ok: true` | n/a | `DOWNLOAD_MANIFEST.json` |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| Primary IRR | **3.21%** synthesis / **1.9%** Lawrence gate | No approved IRR | Marvin **100%** numeric until human promotes source |
| Contract vs Lawrence | Contract **-35.5%** at spot on reinvestment DCF | n/a | Contract is capital-route authority; Lawrence synthesis is stance context |
| Third party | Filing-first | VIC pending | **[PENDING APPROVAL]** — context tier only |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | **$5.35/sh** normalized | **3.21%** synthesis | **hold** |
| Contract (proof-first) | **$11.64/sh** base | **-35.5%** at **$249.99** | owner_review_required |
| External (combined) | Not in base | No change to base % | n/a until approved |
| **Blended best estimate** | **Filing anchor** | **3.21%** | **hold** |

**Weights:** Marvin **100%** on Lawrence synthesis numbers until an approved source is promoted. Contract return is reported separately per `decision_authority.py`; it does not replace synthesis display without **[HUMAN REVIEW]**.

**Returns statement (blended):** We expect **3.21%** per year at **$249.99** on the Marvin synthesis case; no third-party numeric adjustment without **[HUMAN REVIEW]**.

## [HUMAN REVIEW]

- [ ] Review VIC PDF against filings if promotion to approved registry is desired
- [ ] Reconcile Lawrence normalized owner cash ($5.35/sh) with contract owner-earnings bridge ($11.64/sh base value)
- [ ] Every **pending** source cited with **[PENDING APPROVAL]** only

## Primary sources cited

1. `AMZN/research/deep_dive_2026-07-25.md`
2. `AMZN/research/valuation.json`
3. `AMZN/research/valuation_contract.json`
4. `AMZN/third-party-analyses/source_inventory_2026-07-25.md`
5. `AMZN/investor-documents/DOWNLOAD_MANIFEST.json`
6. `AMZN/investor-documents/sec-edgar/10-Q_20260430_rpt20260331_acc0001018724_26_000014.htm`
