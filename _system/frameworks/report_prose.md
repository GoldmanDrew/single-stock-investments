# Report prose — Hohn / Horizon Kinetics voice

**Purpose:** Make Marvin deep dives read like security analyses (Chris Hohn / TCI, Horizon Kinetics), not classification dashboards. Complements `decision_stack.md` (what to analyze) with **how to write it**.

**Structure (sections, dedup):** `_system/frameworks/deep_dive_structure.md` — **single source** for what goes in the report.  
**Template:** `_system/prompts/deep_dive_template.md`  
**IRR:** `_system/frameworks/irr_assumption_ledger.md` + `lawrence_irr.md` § F — at **end** of report only.  
**Third party:** `_system/frameworks/third_party_sources.md`  
**Lint:** `refresh_deep_dive_v2.py` then `lint_deep_dive.py {TICKER}`

---

## Reader-first order

| # | Section | Content |
|---|---------|---------|
| 1 | `## What this business is` | Five sentences max: customers, revenue engine, segments, geography if relevant. **No** archetype/moat/dhando codes. |
| 2 | `## Why the market might be wrong` | 2–3 sentences. HK predictive attribute in plain English, or explicit "no dated payoff / no clear mispricing signal." |
| 3 | `## Executive summary` | 120–180 words: synthesize 1–2 + base return + stance. **Do not** open with `**Stahl**` / `**Archetype**` labels. |
| 4 | `## Business & moat` | Stahl + Hohn mechanics + **Mental models** — **no IRR math** |
| 5 | `## Payoff & return` | Gates, dhando, stance — points to Valuation & IRR |
| 6 | `## Risks & inversion` | Primary risk + inversion |
| 7 | `## Valuation & IRR (assumption ledger)` | Bridge + **every assumption** + IRR arithmetic |
| 8 | Footer | Classification → Terms → [HUMAN REVIEW] → [PROPOSED MEMORY] |

Classification enums belong in the footer table, not the opening paragraph.

---

## Plain English on first use

Spell out jargon once in the body; the footer may keep short codes.

| Term | First-use example |
|------|-------------------|
| **Croupier** (Stahl) | "…acts as a toll collector on transactions (Stahl croupier): fees on volume, not balance-sheet lending." |
| **Dhando** (Pabrai) | "…asymmetric payoff (Pabrai dhando): bear case ~6% return, base case open if volumes persist." |
| **Moat** (Munger) | "…durable competitive advantage (Munger moat): clearing network effects and regulation." |
| **Lawrence bucket** | "…multi-sided network (Lawrence bucket `multi_sided`): exchanges plus data plus mortgage workflow." |
| **Implied IRR** | "…expected annual return at today's price (Lawrence): ~11% over ten years on mid-cycle free cash flow." |
| **Predictive attribute** (HK) | "…equity yield curve (HK): known NAV in 2028, but index funds won't hold until then." |

---

## Mental models (one subsection)

See `deep_dive_structure.md`. Use **### Mental models** only (no separate Tier 2 + plain English duplicate). Table: Model | Finding | Source.

---

## Hohn essentials (simple — every deep dive)

From `_system/frameworks/hohn_business_analysis.md`. **Narrative uses plain English;** genius names stay in footer/tables only.

| Must have | Where |
|-----------|--------|
| IRR arithmetic | `#### IRR arithmetic (show your work)` after valuation bridge — **required** (`lawrence_irr.md` § F) |
| Upside / downside from price | One line **after** IRR arithmetic |
| Quantified pillars + structural/cyclical | Thesis pillars table + one prose paragraph |
| One primary risk | Returns statement + first line under `## Risks & inversion` |
| Fieldwork or gap | Under Business mechanics only (not Primary sources) |
| Show the math | Step-by-step in IRR arithmetic; valuation bridge table is summary only |

**Operating companies:** % changes on volume, price, margin; name one peer when relevant.

**Holding companies / optionality:** `#### Look-through snapshot` + `#### Sum-of-parts or NAV` + `#### Catalyst path` in the body (Altaba-style discount % and next dated step). Do not defer SOTP to [HUMAN REVIEW] alone.

**Risks section:** lead with `**Primary risk:**` then at most **three** secondary bullets. No five-risk laundry list.

Target **400–800 words** in Hohn mechanics; at least half full sentences.

---

## Horizon Kinetics norms

When any Tier 3 HK trigger applies (`mental_models.md` predictive attributes):

| Attribute | Plain-English prompt |
|-----------|---------------------|
| `equity_yield_curve` | What future value is knowable, by what date, and why won't the market wait? |
| `dormant_asset` | What is priced at zero in the multiple? |
| `market_structure_discount` | Index, yield, K-1, or size exclusion — who can't buy it? |
| `transitory_problem` | What cash-flow hit is temporary and bounded? |
| `none` | State explicitly: return is earnings-power / franchise at price, not a dated payoff. |

---

## Punctuation and tone

| Rule | Detail |
|------|--------|
| Em dashes | **Avoid** unicode em dash `—` in narrative. Max **1** per report. Prefer periods or parentheses. |
| Sentence length | Prefer one idea per sentence in executive summary and returns statement. |
| Banned filler | "it's worth noting," "notably," "landscape," "robust," "compelling," "underscores," "delve," "leverage" (verb), "tapestry" |
| AI cadence | Do not chain three clauses with dashes or semicolons; split into separate sentences. |

---

## Facts, inferences, opinions

| Tag | When |
|-----|------|
| **[Fact]** | Disclosed in filings, releases, or audited numbers |
| **[Inference]** | Logical step from facts (normalized earnings, cycle position) |
| **[Opinion]** | Stance, sizing, or judgment calls |

Use inline in prose where judgment is non-obvious. Tables may hold numbers; interpretation needs a tag nearby.

---

## Optional glossary (`## Terms (this report)`)

After **Classification**, list only terms used in **this** report:

```markdown
## Terms (this report)

| Term | Meaning here |
|------|----------------|
| Dhando | … |
| Croupier | … |
```

Skip if every term was spelled out on first use in the body.

---

## Cross-checks and refreshes

- **Quarterly refresh:** update What / Why mispriced / executive summary / Hohn snapshot / bridge / Payoff blocks.
- **Cross-check:** same prose rules; re-derive from primary PDFs; no em-dash pileups when quoting external docs.

---

## Lint reference

| Check | Default | `--strict` | `--legacy` |
|-------|---------|------------|------------|
| Required sections (incl. What / Why mispriced) | error | error | skipped for new sections |
| `#### Return math in plain English` | error | error | skip |
| `**Upside / downside from price:**` | error | error | skip |
| `**Primary risk:**` | error | error | skip |
| holding_co: look-through or SOTP subsection | error | error | skip |
| holding_co: `#### Catalyst path` | warn | error | skip |
| Mental models subsection if Tier 2 present | error | error | skip |
| Em dash count > 1 in body | warn | error | skip |
| Executive summary opens with archetype label | warn | error | skip |
| Executive summary > 220 words | warn | error | skip |

---

## Read order (agents)

1. `decision_stack.md`
2. `report_prose.md` (this file)
3. `hohn_business_analysis.md`
4. `deep_dive_template.md`
5. Primary docs in `{TICKER}/`
