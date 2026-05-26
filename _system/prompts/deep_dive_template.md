# Deep Dive Template

Copy structure for `{TICKER}/research/deep_dive_{date}.md`. Follow `_system/frameworks/decision_stack.md`.

---

```markdown
# {TICKER} — Company Deep Dive

**Date:** {date}
**Agent:** Marvin
**Prior dive:** `{TICKER}/research/deep_dive_{prior}.md` (if refresh)
**Valuation:** `{TICKER}/research/valuation.json`

---

## Executive summary

{One paragraph: business, stack layers 1–3 in plain language, base expected return, proposed stance.}

---

## Business & moat

### What (Stahl + Lawrence bucket)

{Archetype, cycle, lawrence_bucket — 1 short paragraph + evidence table if helpful.}

### Tier 2 prompts

| Model | Finding |
|-------|---------|
| {from archetype_models.json} | … |

### Moat (Munger)

{Widening / stable / eroding — evidence from filings.}

---

## Payoff & return

### Five-question gate

| # | Gate | Answer |
|---|------|--------|
| 1 | Understand? | … |
| 2 | Durable cash flow? | … |
| 3 | Aligned management? | … |
| 4 | Cheap vs normalized cash flow? | … |
| 5 | Why mispriced / bounded recovery? | … |

**Predictive attribute:** none | equity_yield_curve | …

### Dhando (Pabrai)

| Criterion | Assessment |
|-----------|------------|
| Downside bounded (bear case) | … |
| Upside open | … |
| **Dhando** | full | partial | none |

### Expected return

**Method:** full | yield_curve | scenario | pending

| Scenario | Return | Notes |
|----------|--------|-------|
| Bear | …% | … |
| Base | …% | … |
| Bull | …% | … |

**Tool:** `python _system/scripts/marvin_valuation.py --ticker {TICKER}`

### Stance proposal

Base return …% → **{suggested stance}** ({band}). {Override note if any.}

---

## Risks & inversion

{Top 3–5 failure modes — Munger inversion. Cite primary sources.}

---

## Classification

| Field | Value |
|-------|-------|
| **Archetype** (Stahl) | … |
| **Moat** (Munger) | … |
| **Dhando** (Pabrai) | … |
| **Stance** | … |
| **Cycle** | … |
| **Implied 10yr IRR** (Lawrence) | … |
| **IRR method** | … |
| **Lawrence bucket** | … |

## [HUMAN REVIEW]

- …

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] …
```
