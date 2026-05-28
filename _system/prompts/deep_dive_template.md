# Deep Dive Template

Copy structure for `{TICKER}/research/deep_dive_{date}.md`.

**Read order:** `deep_dive_structure.md` → `irr_assumption_ledger.md` → `decision_stack.md` → `report_prose.md`

---

```markdown
# {TICKER} — Company Deep Dive

**Date:** {date}
**Agent:** Marvin
**Prior dive:** `{TICKER}/research/deep_dive_{prior}.md`
**Valuation:** `{TICKER}/research/valuation.json`
**Filing evidence:** `{TICKER}/research/evidence/filing_digest_{date}.md`
**Third party:** `{TICKER}/third-party-analyses/references.md`  
**Adversarial:** pass | blocked · `{TICKER}/research/adversarial_{date}.md` (Milly — required before dive is final)

---

## What this business is

{≤5 sentences. Company overview for a high-school reader.}

---

## Why the market might be wrong

{2–3 sentences. Predictive attribute in plain English.}

---

## Executive summary

{120–180 words. Business + stance + **one** base IRR %. No step-by-step math.}

---

## Primary sources reviewed

{All 10-K / 10-Q / annual / interim from `document_inventory.json`. List pending third-party PDFs separately.}

| Tier | Period / type | Path | Role in this report |
|------|---------------|------|---------------------|

---

## Business & moat

### What (Stahl + Lawrence bucket)

| Field | Value | Evidence |
|-------|-------|----------|

### Mental models

| Model | Finding | Source |
|-------|---------|--------|

### Business mechanics (Hohn)

#### Operating snapshot

| Metric | Latest | Prior Q / YoY | Source |
|--------|--------|---------------|--------|

**Run-rate vs one-off:** …

#### Thesis pillars

| # | Pillar | Mechanism | Numbers / timeline | Evidence |
|---|--------|-----------|-------------------|----------|

**Fieldwork / management:** …

**Disruption / competitive watch:** …

#### Look-through snapshot (holding_co / optionality only)

| Stake | GAAP / carrying | Economic value | Driver |
|-------|-------------------|----------------|--------|

#### Catalyst path (if event-driven)

- …
- Failure mode: …

### Moat (Munger)

{One paragraph.}

---

## Approved Substack context

{If `approved_substacks.md` applies. Else omit.}

---

## Blended estimate (best judgment)

{If approved third party or Substacks change weights. `external_view_blend.md`.}

---

## Payoff & return

### Five-question gate

| # | Gate | Answer |
|---|------|--------|

**Predictive attribute:** …

### Dhando (Pabrai)

| Criterion | Assessment |
|-----------|------------|

### Stance proposal

**Method:** {irr_method}. **Scenarios and every IRR assumption:** see **## Valuation & IRR (assumption ledger)** and `valuation.json`. Base **X%** → **{stance}**.

---

## Risks & inversion

**Primary risk:** …

{≤3 bullets. Inversion.}

---

## Valuation & IRR (assumption ledger)

**Price today:** ${price} ({source}, {date})  
**Method:** {method} · **Base IRR:** {base_pct}% · `{TICKER}/research/valuation.json`

### Valuation bridge

| Case | Method | Key inputs | Implied return | vs ~15% bar |
|------|--------|------------|----------------|-------------|
| Bear | … | … | …% | … |
| Base | … | … | …% | … |
| Bull | … | … | …% | … |

### Assumption ledger (base case)

| # | Assumption | Value | Source or judgment |
|---|------------|-------|-------------------|
| 1 | Price today (P₀) | … | … |
| … | … | … | … |

{Every input. **[Assumption]** or filing path. SOTP: running sum to payoff.}

### IRR arithmetic (show your work)

{Numbered steps per `lawrence_irr.md` § F and `irr_assumption_ledger.md`.}

**Upside / downside from price:** …

**Returns statement:** …

---

## Classification

| Field | Value |
|-------|-------|

## Terms (optional)

## [HUMAN REVIEW]

## [PROPOSED MEMORY]
```
