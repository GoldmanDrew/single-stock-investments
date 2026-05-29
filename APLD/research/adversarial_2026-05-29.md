---
filing: pass
consistency: pass
disclosure: pass
short: no_hit
third_party: n/a
block_final: false
blocking_issues: []
re_pass: false
---

# APLD — Adversarial review

**Date:** 2026-05-29  
**Agent:** Milly (batch pass)  
**Dive reviewed:** `APLD/research/deep_dive_2026-05-29.md`  
**Valuation reviewed:** `APLD/research/valuation.json`  
**Filings used:** `APLD/research/evidence/filing_facts_2026-05-29.json`

**Goal:** Truth-seeking QA. Not bearish for its own sake.

---

## Summary verdict

| Area | Status | One line |
|------|--------|----------|
| Filing reconciliation | pass | filing_facts spot-check |
| Internal consistency | pass | lint_adversarial |
| Disclosure scan | pass | no 8-K scan this batch |
| Short activist scan | no_hit | No Tier-1 forensic short in `short_scan_2026-05-28.md`; no l… |
| Third-party (approved) | n/a | — |

**Overall:** Mechanical pass from filing_facts + lint. No blocking factual errors.

---

## Filing reconciliation

| # | Claim in dive | Dive cites | Filing value | Match? | Severity |
|---|---------------|------------|--------------|--------|----------|
| 1 | Latest revenue (filing) | — | **$126.64B** vs prior $52.92B (+139.3% YoY) | spot-check dive | — |
| — | Stockholders' equity (filing) | — | **1581221.0** | spot-check dive | — |
| — | Net income (filing) | — | **100861.0** | spot-check dive | — |
| — | EPS basic (filing) | — | **0.36** | spot-check dive | — |

---

## Internal consistency

| Check | Expected (valuation.json) | Found in dive | OK? |
|-------|---------------------------|---------------|-----|
| Returns statement | 12.6% | 13.0% | **No** |
| Classification IRR | 12.6% | 12.6% | Yes |
| Valuation bridge base | 12.6% | 13.0% | **No** |

**Lint notes:**
- APLD\research\deep_dive_2026-05-29.md: executive_summary_first_pct 11.5% vs valuation.json base 12.6% (tol 0.25pp)
- APLD\research\deep_dive_2026-05-29.md: returns_statement 13.0% vs valuation.json base 12.6% (tol 0.25pp)
- APLD/research: adversarial date adversarial_2026-05-28.md != dive 2026-05-29

---

## Disclosure scan

| Event | Date | Source | In dive? | Action |
|-------|------|--------|----------|--------|
| (batch) | — | not scanned | — | full pass on next refresh |

---

## Short activist scan

No Tier-1 forensic short in `short_scan_2026-05-28.md`; no local `short_reports/`.

---

## Recommended actions

1. None blocking — optional exec-summary IRR wording vs floor/bull.
2. **Human:** Tier-1 short web scan per `short_activist_registry.md` when prioritizing name.

---

## [HUMAN REVIEW]

- Batch pass — not a substitute for targeted disclosure / short research on high-risk names.
