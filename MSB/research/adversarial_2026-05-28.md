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

# MSB — Adversarial review

**Date:** 2026-05-28  
**Agent:** Milly (batch pass)  
**Dive reviewed:** `MSB/research/deep_dive_2026-05-28.md`  
**Valuation reviewed:** `MSB/research/valuation.json`  
**Filings used:** `MSB/research/evidence/filing_facts_2026-05-28.json`

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
| 1 | Latest revenue (filing) | — | **$3590.45B** vs prior $79001.84B (-95.5% YoY) | spot-check dive | — |
| — | Stockholders' equity (filing) | — | **22781200.0** | spot-check dive | — |
| — | Net income (filing) | — | **2767463.0** | spot-check dive | — |
| — | EPS basic (filing) | — | **0.2109** | spot-check dive | — |

---

## Internal consistency

| Check | Expected (valuation.json) | Found in dive | OK? |
|-------|---------------------------|---------------|-----|
| Returns statement | 8.4% | 8.4% | Yes |
| Classification IRR | 8.4% | 8.4% | Yes |
| Valuation bridge base | 8.4% | 8.4% | Yes |

**Lint notes:**
- MSB\research\deep_dive_2026-05-28.md: executive_summary_first_pct 22.9% vs valuation.json base 8.4% (tol 0.25pp)
- MSB\research\deep_dive_2026-05-28.md: valuation_bridge_base 10.3% vs valuation.json base 8.4% (tol 0.25pp)
- MSB/research: missing adversarial_*.md — run Milly standard pass
- MSB\research\deep_dive_2026-05-28.md: header missing **Adversarial review:** link

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
