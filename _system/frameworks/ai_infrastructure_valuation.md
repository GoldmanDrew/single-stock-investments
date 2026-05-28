# AI infrastructure valuation overlay

**Purpose:** For **AI hyperscaler / platform compounders**, document what is in the Lawrence IRR math versus what is only in narrative — and require explicit treatment of **capex cycles**, **Cloud backlog**, **custom silicon**, and **cost curves**.

**Companion:** `segment_cashflow_valuation.md` (segment sum) · `lawrence_irr.md` · `irr_assumption_ledger.md`

**Stance gate unchanged:** Lawrence consolidated `full` IRR from `marvin_valuation.py` unless human overrides to `optionality` or `scenario`.

---

## When to trigger

Set `ai_overlay` in `{TICKER}/research/valuation.json` when **any** of:

| Trigger | Examples |
|---------|----------|
| **Material AI capex guide** | GOOGL, AMZN, META, MSFT — mgmt guides **$100B+** annual capex or “significantly increase” next year |
| **Cloud + AI as growth engine** | Cloud rev growth **>40%** YoY or backlog disclosed |
| **Custom silicon / TPU story** | External chip sales, inference/training SKUs (press → verify filing) |
| **FCF₀ stale vs guide** | FCF₀ from prior FY while current-year capex guide **>2×** prior-year capex |

Tickers on watchlist (update as needed): **GOOGL, AMZN, META, MSFT**.

Often paired with `valuation_overlay: segment_cashflow`.

---

## Required JSON shape

```json
"ai_overlay": {
  "as_of": "YYYY-MM-DD",
  "status": "partial | complete",
  "in_model": { },
  "not_in_model_requires_refresh": [ ],
  "capex_stress_2026": { },
  "ai_inflection_bull": { }
}
```

| Block | Purpose |
|-------|---------|
| `in_model` | What the spreadsheet / `marvin_valuation.py` actually uses |
| `not_in_model_requires_refresh` | Gaps Milly must flag (TPU line, backlog schedule, margin path, JV economics) |
| `capex_stress_*` | Illustrative trough-year FCF if guide capex hits — **not** FCF₀ for Lawrence base |
| `ai_inflection_bull` | Sensitivity only — optional post-normalization FCF path |

---

## Marvin report requirements

In **Business & moat**, after segment map (if any):

### `#### AI infrastructure — model coverage`

Table: **Theme | Filing/news fact | In current math?**

Minimum rows:

1. Cloud AI demand / backlog  
2. Data-center capex (current-year guide vs FCF₀ year)  
3. Custom chips (TPU / accelerator) — revenue and/or capex offset  
4. Cost reduction / margin (Cloud op margin trend)  
5. Search / Services AI monetization  

In **Valuation & IRR**, add ledger rows for capex stress and bull sensitivity if `ai_overlay` present.

**Do not** move AI-only IRR math into Business & moat.

---

## Milly requirements

Add workstream checks (see `MILLY.md` § AI & valuation staleness):

| Check | Fail / warn |
|-------|-------------|
| FCF₀ year vs latest 10-K/10-Q period | **Warn** if FCF₀ FY ≠ latest filing period without note |
| Capex guide vs FCF₀ capex | **Warn** if guide **>1.5×** FCF₀-year capex and no `capex_stress` in JSON |
| `ai_overlay.not_in_model` non-empty | **Inference risk** in adversarial; not auto `block_final` |
| Press-only AI claims (TPU $, JV terms, “30% cost cut”) | **Warn** unless cited to filing path |
| Cloud backlog cited | **Filing reconcile** backlog $ if in exec summary |

YAML frontmatter extension:

```yaml
valuation_staleness: pass   # pass | warn | fail
ai_coverage: partial        # n/a | partial | complete
```

`valuation_staleness: fail` only when FCF₀ is wrong period vs filing (factual), not when model is conservative.

---

## Lint

```bash
python _system/scripts/marvin_valuation.py --ticker {TICKER} --write
python _system/scripts/lint_deep_dive.py {TICKER}
python _system/scripts/lint_adversarial.py {TICKER}
```

`marvin_valuation.py --write` populates `overlay_results` (AI inflection, capex stress, segment rows).

- `lint_deep_dive.py`: errors if `ai_overlay` in JSON but dive missing `#### AI infrastructure`
- `lint_adversarial.py`: warns on `not_in_model_requires_refresh` non-empty + missing [HUMAN REVIEW] in dive

---

## Anti-patterns

- Treating news TPU revenue as filing fact  
- Using **bull AI FCF** as Lawrence **FCF₀** without **[Assumption]** and human review  
- Skipping **capex trough** discussion when guide doubles YoY  
- Single blended growth rate as “AI is priced in” with no backlog/margin/chip rows  
