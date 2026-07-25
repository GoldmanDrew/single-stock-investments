# ALAB — Cross-Check: Third-Party Sources

**Date:** 2026-07-25  
**Agent:** Marvin  
**Marvin dive:** `ALAB/research/deep_dive_2026-07-25.md`  
**Source inventory:** `ALAB/third-party-analyses/source_inventory_2026-07-25.md`  
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

No approved third-party research sources are indexed for ALAB as of 2026-07-25. The scan lists **0** approved, **0** pending, and **0** context-tier Substacks or fund letters. SC-13G filings from institutional holders (Fidelity, Vanguard-class filers) sit in `third-party-analyses/activist_reports/long/` but are **ownership disclosures**, not investment theses, and are excluded from IRR blending.

**Synthesis:** Marvin floor only. Normalized owner cash **$1.62 per share**, Lawrence base **-8.5%** per year at **$309.09**, component contract base **$84.20 per share** (**-17.0%** annualized at spot), total synthesis **-2.93%** per year. No external blend.

## Sources in scope

| ID | Title | Path | Status | Use |
|----|-------|------|--------|-----|
| (none) | Primary filings only | `ALAB/research/evidence/filing_digest_2026-07-25.md` | primary | Base IRR and contract |
| SC-13G (context) | Institutional ownership filings | `ALAB/third-party-analyses/activist_reports/long/` | context | Ownership only; not in base IRR |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| Revenue hyper-growth | FY2025 revenue **$852.5M** (+115% YoY); Q1 2026 **$308.4M** (+94% YoY) | No external thesis to compare | 10-K FY2025; 10-Q Q1 2026 |
| Balance sheet | **$167.6M** cash; no long-term debt tagged | n/a | filing_facts 2026-07-25 |
| Insider activity | Net insider selling; ICS negligible | n/a | insider_signal 2026-07-25 |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| Valuation vs growth | Spot **$309.09** embeds far above **$84.20/sh** contract base | n/a | No external counter-view |
| Owner-cash normalization | **$1.62/sh** after OCF capex haircut | n/a | Capex not XBRL-tagged; [Assumption] |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor (Lawrence) | **$1.62/sh** normalized | **-8.5%** / 7yr at **$309.09** | watch |
| Component contract | **$84.20/sh** base sum | **-17.0%** / 7yr at spot | watch |
| External (combined) | — | — | — |
| **Blended best estimate** | **$84.20/sh** contract base | **-2.93%** synthesis / 7yr | **watch** |

**Weights:** 100% Marvin primary (filings + component proofs). No approved external sources.

**Returns statement (blended):** At **$309.09**, Marvin synthesis implies about **-2.93%** per year over 7 years on filing-grounded owner cash and component reserve; no third-party views in base IRR.

## [HUMAN REVIEW]

- [ ] Confirm live price vs **$309.09** stub before sizing
- [ ] Promote any SC-13G holder commentary only after human approval in `third_party_sources.md`
- [ ] Re-run scan when Substacks or sell-side notes are added

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] ALAB: third-party cross-check 2026-07-25; Marvin floor only; synthesis **-2.93%** at **$309.09**; contract **$84.20/sh** base.

## Primary sources cited

1. `ALAB/research/deep_dive_2026-07-25.md`
2. `ALAB/third-party-analyses/source_inventory_2026-07-25.md`
3. `ALAB/research/evidence/filing_facts_2026-07-25.json`
4. `ALAB/investor-documents/sec-edgar/10-K_20260220_rpt20251231_acc0001736297_26_000010.htm`
5. `ALAB/investor-documents/sec-edgar/10-Q_20260506_rpt20260331_acc0001736297_26_000020.htm`
