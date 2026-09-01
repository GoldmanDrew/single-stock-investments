---
filing: pass
consistency: fail
disclosure: pass
short: no_hit
third_party: n/a
block_final: true
blocking_issues: ["classification_irr"]
re_pass: false
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
| Internal consistency | fail | lint_adversarial |
| Disclosure scan | pass | no 8-K scan this batch |
| Short activist scan | no_hit | No Tier-1 forensic short in `short_scan_2026-05-28.md`; no l… |
| Third-party (approved) | n/a | — |

**Overall:** Mechanical pass from filing_facts + lint. **Block fixes** in dive before final.

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
| Classification IRR | 14.28% | -1.79% | **No** |
| Valuation bridge base | 14.28% | 14.28% | Yes |

**Lint notes:**
- BN/research/deep_dive_2026-07-21.md: classification -1.79% vs valuation.json base 14.28% (tol 0.25pp)

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

1. **Marvin:** Align Returns statement / Classification IRR with `valuation.json` base.
2. **Human:** Tier-1 short web scan per `short_activist_registry.md` when prioritizing name.

---

## [HUMAN REVIEW]

- Batch pass — not a substitute for targeted disclosure / short research on high-risk names.
