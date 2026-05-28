---
filing: pass
consistency: pass
disclosure: pass
short: no_hit
third_party: n/a
valuation_staleness: warn
ai_coverage: partial
block_final: false
blocking_issues: []
re_pass: false
---

# GOOGL — Adversarial review

**Date:** 2026-05-29  
**Agent:** Milly  
**Dive reviewed:** `GOOGL/research/deep_dive_2026-05-29.md`  
**Valuation reviewed:** `GOOGL/research/valuation.json`  
**Filings used:** `GOOGL/research/evidence/filing_facts_2026-05-28.json`, `filing_digest_2026-05-28.md`

**Goal:** Truth-seeking QA. Not bearish for its own sake.

---

## Summary verdict

| Area | Status | One line |
|------|--------|----------|
| Filing reconciliation | pass | Core metrics match filing_facts |
| Internal consistency | pass | Lawrence 2.1% aligned; overlay_results present |
| Disclosure scan | pass | Q1 2026 8-K on file |
| Short activist scan | no_hit | No new Tier-1 hit |
| Third-party (approved) | n/a | — |
| AI & valuation staleness | warn | FCF₀ FY2025 vs $180–190B capex guide; gaps documented |

**Overall:** No blocking factual errors. **valuation_staleness: warn** — Lawrence uses FY2025 FCF while capex guide implies trough-year cash; `ai_overlay.not_in_model` items require ongoing filing bridge.

---

## Filing reconciliation

| # | Claim in dive | Filing value | Match? | Severity |
|---|---------------|--------------|--------|----------|
| 1 | P₀ $386 | Market | ok | — |
| 2 | FY2025 revenue $402.8B | 402836 | ok | — |
| 3 | Q1 2026 revenue $109.9B | 109896 | ok | — |
| 4 | Services OI $139.4B FY2025 | Segment note | ok | — |
| 5 | FCF₀ $5.85/sh | OCF−capex FY2025 | ok | — |
| 6 | Base IRR 2.1% | valuation.json | ok | — |

---

## Internal consistency

| Check | Expected | Found | OK? |
|-------|----------|-------|-----|
| Base IRR exec / returns / classification | 2.1% | 2.1% | yes |
| overlay_results AI inflection | 11.2% | 11.2% | yes |
| Segment sum PV | $163.7/sh | $163.7/sh | yes |
| Stance watch | watch | watch | yes |

---

## AI & valuation staleness

| Check | Status | Note |
|-------|--------|------|
| `#### AI infrastructure` in dive | pass | Present |
| FCF₀ period vs latest filing | warn | FCF₀ = FY2025; capex guide is 2026 |
| Capex guide vs FCF₀-year capex | warn | $185B guide vs $52.5B FY2025 capex — `capex_stress` in JSON |
| `not_in_model_requires_refresh` addressed | partial | Listed in dive + [HUMAN REVIEW] |
| Press-only AI claims labeled | pass | TPU/JV as [Assumption] or news |

**valuation_staleness:** warn  
**ai_coverage:** partial (TPU revenue line, backlog schedule still open)

---

## Disclosure scan

| Event | In dive? | Action |
|-------|----------|--------|
| Q1 2026 earnings 8-K | yes | — |

---

## Short activist scan

**Verdict:** no_public_short_found (batch index 2026-05-28)

---

## Third-party (approved)

n/a

---

## Blocking issues

None.

## Inference risks → [HUMAN REVIEW]

- Segment FCF allocation by OI share, not segment cash from filing.
- AI inflection $8/sh FCF₀ is sensitivity only (11.2% IRR), not stance gate.
- TPU external revenue, backlog drawdown schedule, Cloud margin path not in Lawrence base math.
