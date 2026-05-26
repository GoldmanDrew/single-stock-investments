# Deep Dive Template

Copy structure for `{TICKER}/research/deep_dive_{date}.md`. Follow `_system/frameworks/decision_stack.md` and `_system/frameworks/report_prose.md`.

---

```markdown
# {TICKER} — Company Deep Dive

**Date:** {date}
**Agent:** Marvin
**Prior dive:** `{TICKER}/research/deep_dive_{prior}.md` (if refresh)
**Valuation:** `{TICKER}/research/valuation.json`

---

## What this business is

{Up to 5 plain sentences: who pays whom, main segments, how cash is generated. No archetype/moat/dhando codes. No em dashes.}

---

## Why the market might be wrong

{2–3 sentences. Explain HK predictive attribute in plain English — equity yield curve, dormant asset, transitory problem, market-structure discount, or "no clear mispricing signal; return is franchise/earnings at price."}

---

## Executive summary

{120–180 words. Synthesize What + Why mispriced + base expected return + proposed stance. Do not open with Stahl/Munger/Pabrai/Lawrence labels. No tables. No em dashes.}

---

## Business & moat

### What (Stahl + Lawrence bucket)

{Archetype, cycle, lawrence_bucket — spell out bucket in words on first use; evidence table if helpful.}

### Tier 2 prompts

| Model | Finding |
|-------|---------|
| {from archetype_models.json} | … |

### Mental models in plain English

{One sentence per Tier 2 model used: Model (Genius): question? Answer — evidence cite. Required when Tier 2 table is present.}

### Business mechanics (Hohn)

See `_system/frameworks/hohn_business_analysis.md`.

#### Operating snapshot

| Metric | Latest | Prior Q / YoY | Source |
|--------|--------|---------------|--------|
| Revenue / net revenues | … | … | … |
| Volume / activity | … | … | … |
| Pricing / yield | … | … | … |
| Margin / mix | … | … | … |

**Run-rate vs one-off:** …

#### Thesis pillars

| # | Pillar | Mechanism | Numbers / timeline | Evidence |
|---|--------|-----------|-------------------|----------|
| 1 | … | reversionary pricing / volume / cost / capital / catalyst | … | `{TICKER}/…pdf` |
| 2 | … | … | … | … |

{1 short paragraph: label each pillar structural vs cyclical in words.}

**Fieldwork / management:** … (or "None this period — {what would upgrade conviction}")

**Disruption / competitive watch:** …

#### Valuation bridge

| Case | Method | Key inputs | Implied return | vs ~15% Hohn bar |
|------|--------|------------|----------------|------------------|
| Bear | … | … | …% | … |
| Base | EPS path × exit multiple / FCF yield + growth / … | … | …% | pass / fail |
| Bull | … | … | …% | … |

#### Return math in plain English

{One paragraph: audit base case. Example: "At $X, 8% FCF yield + 5% growth ≈ 13% total return" or "EPS $A → $B, × N× exit = $C in Y years → Z% p.a." Cite inputs.}

**Upside / downside from price:** Base …% upside to $…; bear …%; ~10% downside vs stand-alone/book: pass/fail.

**Returns statement:** We expect …% over … years based on …; primary risk: …

#### Look-through snapshot (holding_co / optionality only)

| Stake | GAAP / carrying | Economic value (if different) | Driver |
|-------|-------------------|-------------------------------|--------|
| … | … | … | … |

#### Sum-of-parts or NAV (holding_co / optionality only)

| Item | $ | Per FRMO sh (or per share) | Notes |
|------|---|---------------------------|--------|
| … | … | … | … |

**Price vs NAV:** $… market vs $… NAV = …% discount. (Skip subsections for pure operating companies.)

#### Catalyst path (if mispricing is event-driven)

- {Event 1 + timing}
- {Event 2 + timing}
- {What fails if catalysts slip}

### Optionality overlay (if triggered)

See `_system/frameworks/optionality_valuation.md`. Skip if standard Lawrence/Hohn gate is sufficient.

| Field | Value |
|-------|-------|
| Framework | holdco_sotp / mineral_floor_option / hk_royalty_curve |
| Floor | … |
| Free option / catalyst | … |
| Primary metric | … |
| Predictive attribute(s) | … |

### Moat (Munger)

{Widening / stable / eroding — spell out "competitive advantage" on first use; evidence from filings.}

---

## Blended estimate (best judgment)

{Required when an external manager letter, research note, or material press release is cited. Not binary Marvin vs external.}

| Lens | Key metric (owner cash Y0 or equivalent) | Return / horizon | Stance hint |
|------|------------------------------------------|------------------|-------------|
| Marvin floor | … | …% (10yr) | … |
| External ({source}) | … | … ({horizon}) | … |
| **Blended best estimate** | **…** | **…%** | **…** |

**Weights:** Marvin …% because …; external …% because ….

**Returns statement (blended):** …

{Skip section if no external view. Record in `valuation.json` → `estimates`.}

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

{One sentence explaining the attribute in plain English (required even when `none`).}

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

**Primary risk:** {one dominant failure mode — same as returns statement}

{At most 3 secondary bullets. Munger inversion: what proves us wrong? Cite primary sources.}

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

## Terms (this report)

{Optional. Only terms used in this report — skip if all spelled out in body.}

| Term | Meaning here |
|------|----------------|
| … | … |

## [HUMAN REVIEW]

- …

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] …
```
