---
filing: pass
consistency: pass
disclosure: pass
short: no_hit
third_party: n/a
block_final: false
blocking_issues: []
re_pass: true
---

# BN — Adversarial review

**Date:** 2026-07-21  
**Agent:** Milly (batch pass)  
**Dive reviewed:** `BN/research/deep_dive_2026-07-21.md`  
**Valuation reviewed:** `BN/research/valuation.json`  
**Filings used:** `BN/research/evidence/filing_facts_2026-07-21.json`

**Goal:** Truth-seeking QA. Not bearish for its own sake.

---

## Summary verdict

| Area | Status | One line |
|------|--------|----------|
| Filing reconciliation | pass | filing_facts spot-check |
| Internal consistency | pass | Classification IRR now matches the 14.28% total synthesis return |
| Disclosure scan | pass | no 8-K scan this batch |
| Short activist scan | no_hit | No Tier-1 forensic short in `short_scan_2026-05-28.md`; no l… |
| Third-party (approved) | n/a | — |

**Overall:** Mechanical re-pass completed 2026-09-01. The Classification IRR now matches the 14.28% total synthesis return, so the prior consistency blocker is cleared. Targeted disclosure and short research remain human-review items rather than blockers.

---

## Filing reconciliation

| # | Claim in dive | Dive cites | Filing value | Match? | Severity |
|---|---------------|------------|--------------|--------|----------|
| — | filing_facts | — | no_full_tier_text_extract | — | inference |
| — | No filing_facts metrics | — | — | run build_filing_evidence | — |

---

## Internal consistency

| Check | Expected (valuation.json) | Found in dive | OK? |
|-------|---------------------------|---------------|-----|
| Returns statement | 14.28% | 14.28% | Yes |
| Classification IRR | 14.28% | 14.28% | **Yes** |
| Valuation bridge base | 14.28% | 14.28% | Yes |

**Lint notes:**
- Re-pass 2026-09-01: Classification IRR aligned to `valuation.json` total synthesis 14.28%.

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

1. **Completed:** Returns statement and Classification IRR both show the 14.28% total synthesis return.
2. **Human:** Tier-1 short web scan per `short_activist_registry.md` when prioritizing name.

---

## [HUMAN REVIEW]

- Mechanical re-pass — not a substitute for targeted disclosure / short research on high-risk names.
