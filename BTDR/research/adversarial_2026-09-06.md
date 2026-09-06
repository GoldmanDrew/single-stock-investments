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

# BTDR — Adversarial review

**Date:** 2026-09-06  
**Agent:** Milly (batch pass)  
**Dive reviewed:** `BTDR/research/deep_dive_2026-09-06.md`  
**Valuation reviewed:** `BTDR/research/valuation.json`  
**Filings used:** `BTDR/research/evidence/filing_facts_2026-09-06.json`

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
| 1 | Latest revenue (filing) | — | **$225710.00B** | spot-check dive | — |
| — | Stockholders' equity (filing) | — | **706751000** | spot-check dive | — |
| — | Net income (filing) | — | **261740000** | spot-check dive | — |

---

## Internal consistency

| Check | Expected (valuation.json) | Found in dive | OK? |
|-------|---------------------------|---------------|-----|
| Returns statement | -35.77% | -35.77% | Yes |
| Classification IRR | -35.77% | None% | — |
| Valuation bridge base | -35.77% | -35.77% | Yes |

**Lint notes:**
- BTDR/research/deep_dive_2026-09-06.md: missing Implied 7yr IRR in Classification
- BTDR/research: adversarial date adversarial_2026-08-20.md != dive 2026-09-06

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
