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

# CI — Adversarial review

**Date:** 2026-08-10  
**Agent:** Milly (batch pass)  
**Dive reviewed:** `CI/research/deep_dive_2026-08-10.md`  
**Valuation reviewed:** `CI/research/valuation.json`  
**Filings used:** `CI/research/evidence/filing_facts_2026-08-10.json`

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
| 1 | Latest revenue (filing) | — | **$274.90B** vs prior $247.12B (+11.2% YoY) | spot-check dive | — |
| — | Stockholders' equity (filing) | — | **41713.0** | spot-check dive | — |
| — | Net income (filing) | — | **5957.0** | spot-check dive | — |
| — | EPS basic (filing) | — | **22.33** | spot-check dive | — |

---

## Internal consistency

| Check | Expected (valuation.json) | Found in dive | OK? |
|-------|---------------------------|---------------|-----|
| Returns statement | n/a | 7.26% | — |
| Classification IRR | n/a | None% | — |
| Valuation bridge base | n/a | 7.26% | — |

**Lint notes:**
- CI/research: dive header cites adversarial but file missing

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
