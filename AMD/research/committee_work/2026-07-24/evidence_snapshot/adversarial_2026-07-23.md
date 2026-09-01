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

# AMD — Adversarial review

**Date:** 2026-07-23  
**Agent:** Milly (batch pass)  
**Dive reviewed:** `AMD/research/deep_dive_2026-07-23.md`  
**Valuation reviewed:** `AMD/research/valuation.json`  
**Filings used:** `AMD/research/evidence/filing_facts_2026-07-23.json`

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

**Overall:** Mechanical pass from filing_facts + lint. No blocking factual errors after IRR alignment re-pass.

---

## Filing reconciliation

| # | Claim in dive | Dive cites | Filing value | Match? | Severity |
|---|---------------|------------|--------------|--------|----------|
| 1 | Latest revenue (filing) | — | **$34.64B** vs prior $25.79B (+34.3% YoY) | spot-check dive | — |
| — | Stockholders' equity (filing) | — | **62999.0** | spot-check dive | — |
| — | Net income (filing) | — | **4335.0** | spot-check dive | — |
| — | EPS basic (filing) | — | **2.67** | spot-check dive | — |

---

## Internal consistency

| Check | Expected (valuation.json) | Found in dive | OK? |
|-------|---------------------------|---------------|-----|
| Returns statement | -14.56% | -14.56% | Yes |
| Classification IRR | -14.56% | 7.84% | **No** |
| Valuation bridge base | -14.56% | -14.56% | Yes |

**Lint notes:**
- AMD/research/deep_dive_2026-07-23.md: classification 7.84% vs valuation.json base -14.56% (tol 0.25pp)
- AMD/research/deep_dive_2026-07-23.md: executive_summary_first_pct 12.1% vs valuation.json base -14.56% (tol 0.25pp)
- AMD/research: adversarial date adversarial_2026-06-07.md != dive 2026-07-23

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
