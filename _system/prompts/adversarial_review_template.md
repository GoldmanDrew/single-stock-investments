# Adversarial review template (Milly)

Copy to `{TICKER}/research/adversarial_{date}.md`.

**Read:** `_system/agents/MILLY.md`, `_system/frameworks/short_activist_registry.md`

---

```markdown
---
filing: pass
consistency: pass
disclosure: pass
short: no_hit
third_party: n/a
valuation_staleness: pass
ai_coverage: n/a
block_final: false
blocking_issues: []
re_pass: false
---

# {TICKER} — Adversarial review

**Date:** {date}
**Agent:** Milly
**Dive reviewed:** `{TICKER}/research/deep_dive_{dive_date}.md`
**Valuation reviewed:** `{TICKER}/research/valuation.json`
**Filings used:** {list paths from filing_digest + filing_facts_{date}.json}

**Goal:** Truth-seeking QA. Not bearish for its own sake.

---

## Summary verdict

| Area | Status | One line |
|------|--------|----------|
| Filing reconciliation | pass / partial / fail | |
| Internal consistency | pass / fail | |
| Disclosure scan | pass / hit / needs_human | |
| Short activist scan | no_hit / hit / stale_hit / litigation | |
| Third-party (approved) | n/a / pass / partial | |

**Overall:** {one sentence}

---

## Filing reconciliation

| # | Claim in dive | Dive cites | Filing / filing_facts | Match? | Severity |
|---|---------------|------------|------------------------|--------|----------|

{Mandatory checklist: price, shares/book, revenue+YoY, NI+one-off, equity/debt, owner cash, IRR triple-check, stance.}

---

## Internal consistency

| Check | Expected (valuation.json) | Found in dive | OK? |
|-------|---------------------------|---------------|-----|
| Base IRR exec summary | | | |
| Base IRR returns statement | | | |
| valuation.json base_pct | | | |
| Classification Implied 10yr IRR | | | |
| Valuation bridge base row | | | |
| SOTP sum (if holdco) | | | |

---

## AI & valuation staleness

{If `ai_overlay` or hyperscaler — `ai_infrastructure_valuation.md`}

| Check | Status | Note |
|-------|--------|------|
| `#### AI infrastructure` in dive | | |
| FCF₀ period vs latest filing | | |
| Capex guide vs FCF₀-year capex | | |
| `not_in_model_requires_refresh` addressed | | |
| Press-only AI claims labeled | | |

**valuation_staleness:** pass / warn / fail  
**ai_coverage:** n/a / partial / complete

---

## Disclosure scan

| Event | Date | Source path | In dive? | Action |
|-------|------|-------------|----------|--------|

{8-K, late filing, non-reliance, auditor change since prior dive.}

---

## Short activist scan

**Registry:** `_system/frameworks/short_activist_registry.md`  
**Portfolio index:** `_system/research/short_scan_{date}.md`

| Firm | Report? | Date | Path/URL | Verdict |
|------|---------|------|----------|---------|

### Material claims (if any)

| Claim | Short source | Filing check | Dive addressed? | Verdict |

---

## Third-party reconciliation (approved only)

| Source ID | Claim | In dive? | Filing supports? | Blend weight OK? |
|-----------|-------|----------|------------------|------------------|

---

## Recommended actions

1. {Marvin fix / human only}

---

## Resolved in dive

{After re-pass: list sections fixed; leave empty on first pass.}

---

## [HUMAN REVIEW]

- …
```
