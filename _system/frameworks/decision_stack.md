# Decision Stack

**Purpose:** Single pipeline for Marvin deep dives. Replaces reading four separate framework docs on every run.

**Appendix references (detail only):** `mental_models.md`, `lawrence_irr.md`, `classification.md`, `quality_checklist.md`

---

## The stack (one direction of flow)

| Layer | Genius | Fields | Question |
|-------|--------|--------|----------|
| **1. What** | Stahl + Lawrence | `archetype`, `cycle`, `lawrence_bucket` | What business type; normalize earnings? |
| **2. Durable** | Munger | `moat` | Will it last 10 years? |
| **3. Payoff shape** | Pabrai | `dhando` | Is the bear case bounded? |
| **4. Return at price** | Lawrence / HK | `implied_irr`, `irr_method` | Expected return at today's price? |
| **5. Action** | Pabrai + Lawrence | `stance` | What do we do with capital? |

**Rule:** Layer 5 is **proposed** from layer 4, **gated** by layers 2–3, **approved** by human. Document overrides explicitly.

---

## Step 1 — Five-question gate (before quant)

One table — maps to all geniuses; do not duplicate elsewhere in the report.

| # | Gate | Maps to | Fail → |
|---|------|---------|--------|
| 1 | **Understand?** | Munger circle of competence | `stance: watch`; stop or defer |
| 2 | **Durable cash flow?** | Munger moat | Downgrade moat; cap terminal multiple |
| 3 | **Aligned management?** | Munger incentives | Flag in [HUMAN REVIEW] |
| 4 | **Cheap vs normalized cash flow?** | Lawrence input | Drives layer 4 model |
| 5 | **Why mispriced / bounded recovery?** | HK predictive attribute | Chooses `irr_method` |

---

## Step 2 — Archetype prompts (Tier 2)

Load `_system/frameworks/archetype_models.json`. When `archetype` is set, answer listed models inline under **Business & moat** — not as separate report sections.

---

## Step 3 — Expected return (one section, three methods)

| Trigger | `irr_method` | Tool |
|---------|--------------|------|
| Modelable FCF / owner earnings | `full` | Lawrence 10yr — `marvin_valuation.py` |
| Dated contractual payoff | `yield_curve` | HK equity yield curve — manual + `marvin_valuation.py` |
| Binary / pre-revenue | `scenario` | Bear/base/bull scenarios — `marvin_valuation.py` |
| Cannot model | `pending` | Skip numeric; explain why |

**Output file:** `{TICKER}/research/valuation.json` (source of truth for assumptions + computed returns)

```bash
python _system/scripts/marvin_valuation.py --ticker ICE
python _system/scripts/marvin_valuation.py --file ICE/research/valuation.json
```

`implied_irr` in classification = **base-case expected return** at current price (label: 10yr IRR, yield-curve annualized, or scenario IRR).

---

## Step 4 — Stance proposal (automated)

Script computes `stance_proposal` in `valuation.json`. Logic:

```
if moat in (eroding, unproven) or dhando == none:
    suggested = watch
elif base_return > 20% and dhando in (full, partial):
    suggested = accumulate
elif base_return >= 15%:
    suggested = hold
elif base_return < 15%:
    suggested = watch
else:
    suggested = pending  # irr_method pending or missing
```

**Override reasons** (human sets `override_reason` in valuation.json or documents in [HUMAN REVIEW]):

| Override | When allowed |
|----------|--------------|
| `hold` despite return < 15% | Incumbent core; tax; strategic sleeve (e.g. croupier basket) |
| `accumulate` despite return 15–18% | Dhando full + moat widening + cycle trough |
| `watch` despite return > 20% | Moat unproven, binary risk, going-concern |

Approved `stance` lives in `classification.json` + `thesis.md`. Run `sync_classification.py` to detect drift.

---

## Step 5 — Report template

Use `_system/prompts/deep_dive_template.md`. Five blocks only:

1. **Executive summary** + classification table
2. **Business & moat** — Stahl archetype + Munger + Tier 2 prompts
3. **Payoff & return** — dhando + five-question gate + expected return table
4. **Risks & inversion**
5. **[HUMAN REVIEW]** + **[PROPOSED MEMORY]**

Cross-checks / refreshes: update blocks 3–5 unless business changed.

---

## Lawrence bucket ↔ archetype (hints)

| Archetype | Typical bucket |
|-----------|----------------|
| `croupier`, `platform` | `multi_sided` |
| `compounder`, `serial_acquirer` | `pricing_power` |
| `infrastructure`, `holding_co` | `low_cost` or `other` |
| `optionality`, `turnaround` | `other` + `irr_method: scenario` |

Not mandatory match — document when they diverge.

---

## Sync & lint

```bash
python _system/scripts/marvin_valuation.py --ticker ICE    # compute + write valuation.json
python _system/scripts/sync_classification.py              # check thesis ↔ json ↔ valuation
python _system/scripts/lint_deep_dive.py ICE               # required sections
python _system/scripts/build_dashboard_data.py
```

---

## Read order for agents (deep dive)

1. `_system/frameworks/decision_stack.md` (this file)
2. `_system/memory/MEMORY.md` (approved beliefs)
3. Primary docs in `{TICKER}/`
4. `_system/prompts/deep_dive_template.md` (output shape)
5. Appendix only if needed: `mental_models.md`, `lawrence_irr.md`
