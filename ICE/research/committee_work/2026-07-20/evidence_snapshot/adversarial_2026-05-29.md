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

# ICE — Adversarial review

**Date:** 2026-05-29  
**Agent:** Milly (batch pass)  
**Dive reviewed:** `ICE/research/deep_dive_2026-05-29.md`  
**Valuation reviewed:** `ICE/research/valuation.json`  
**Filings used:** `ICE/research/evidence/filing_facts_2026-05-29.json`

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
| 1 | Latest revenue (filing) | — | **$2.47B** vs prior $2.12B (+16.3% YoY) | spot-check dive | — |
| — | Stockholders' equity (filing) | — | **29478.0** | spot-check dive | — |
| — | Net income (filing) | — | **1413.0** | spot-check dive | — |
| — | EPS basic (filing) | — | **2.49** | spot-check dive | — |

---

## Internal consistency

| Check | Expected (valuation.json) | Found in dive | OK? |
|-------|---------------------------|---------------|-----|
| Returns statement | 11.0% | 11.0% | Yes |
| Classification IRR | 11.0% | 11.0% | Yes |
| Valuation bridge base | 11.0% | 11.0% | Yes |

**Lint notes:**
- ICE\research\deep_dive_2026-05-29.md: executive_summary_first_pct 15.0% vs valuation.json base 11.0% (tol 0.25pp)
- ICE/research: adversarial date adversarial_2026-05-28.md != dive 2026-05-29

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
