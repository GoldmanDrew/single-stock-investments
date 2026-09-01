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

# QDEL — Adversarial review

**Date:** 2026-07-21  
**Agent:** Milly (batch pass)  
**Dive reviewed:** `QDEL/research/deep_dive_2026-07-21.md`  
**Valuation reviewed:** `QDEL/research/valuation.json`  
**Filings used:** `QDEL/research/evidence/filing_facts_2026-07-21.json`

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
| 1 | Latest revenue (filing) | — | **$2.78B** vs prior $3.00B (-7.2% YoY) | spot-check dive | — |
| — | Stockholders' equity (filing) | — | **1920.5** | spot-check dive | — |
| — | Net income (filing) | — | **1131.8** | spot-check dive | — |
| — | EPS basic (filing) | — | **16.69** | spot-check dive | — |

---

## Internal consistency

| Check | Expected (valuation.json) | Found in dive | OK? |
|-------|---------------------------|---------------|-----|
| Returns statement | 18.05% | 18.05% | Yes |
| Classification IRR | 18.05% | 18.05% | Yes |
| Valuation bridge base | 18.05% | 18.05% | Yes |

**Lint notes:**
- QDEL/research/deep_dive_2026-07-21.md: header missing **Adversarial review:** link

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
