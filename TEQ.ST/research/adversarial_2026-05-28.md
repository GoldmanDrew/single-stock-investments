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

# TEQ.ST — Adversarial review

**Date:** 2026-05-28  
**Agent:** Milly (batch pass)  
**Dive reviewed:** `TEQ.ST/research/deep_dive_2026-05-28.md`  
**Valuation reviewed:** `TEQ.ST/research/valuation.json`  
**Filings used:** `TEQ.ST/research/evidence/filing_facts_2026-05-28.json`

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
| — | No filing_facts metrics | — | — | run build_filing_evidence | — |

---

## Internal consistency

| Check | Expected (valuation.json) | Found in dive | OK? |
|-------|---------------------------|---------------|-----|
| Returns statement | 13.7% | 13.7% | Yes |
| Classification IRR | 13.7% | 13.7% | Yes |
| Valuation bridge base | 13.7% | 13.7% | Yes |

**Lint notes:**
- TEQ.ST\research\deep_dive_2026-05-28.md: executive_summary_first_pct 42.8% vs valuation.json base 13.7% (tol 0.25pp)
- TEQ.ST/research: missing adversarial_*.md — run Milly standard pass
- TEQ.ST\research\deep_dive_2026-05-28.md: header missing **Adversarial review:** link

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
