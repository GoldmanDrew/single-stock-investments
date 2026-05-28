# Decision Stack

**Purpose:** Single pipeline for Marvin deep dives. Replaces reading four separate framework docs on every run.

**Report shape (dedup):** `deep_dive_structure.md` — sections and what not to repeat.  
**Appendix references (detail only):** `mental_models.md`, `lawrence_irr.md` § F (IRR arithmetic), `classification.md`, `quality_checklist.md`

---

## The stack (one direction of flow)

| Layer | Genius | Fields | Question |
|-------|--------|--------|----------|
| **1. What** | Stahl + Lawrence | `archetype`, `cycle`, `lawrence_bucket` | What business type; normalize earnings? |
| **1b. Mechanics** | Hohn | — (in report body) | How does it earn; thesis pillars; valuation bridge? |
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

## Step 2b — Business mechanics (Hohn)

Read `_system/frameworks/hohn_business_analysis.md` (or `tci/Hohn-Analysis-Framework-extract.txt` for quick reference).

Under **Business & moat → Business mechanics (Hohn)**, every deep dive must include (`hohn_business_analysis.md` § Hohn essentials):

1. **Operating snapshot** (or **look-through** for holding_co / optionality)  
2. **Thesis pillars** — 2–4 drivers, quantified; structural vs cyclical in prose  
3. **Business overview** (no IRR in body) → **Payoff & return** (gates only) → **`## Valuation & IRR (assumption ledger)`** at end (`irr_assumption_ledger.md`)  
4. **SOTP/NAV + catalyst path** when holding_co or optionality (no duplicate Optionality overlay table)  
5. **Primary risk** — one dominant failure mode (max 3 secondary in Risks)  

Reconcile base IRR in arithmetic with `valuation.json` and footer `implied_irr`.

## Step 2c — Optionality overlay (when triggered)

Read `_system/frameworks/optionality_valuation.md` when any trigger matches:

- Holdco / SOTP (FRMO)
- Mineral or land floor + free production option (KEWL)
- Passive royalty trust with HK transitory + yield curve (MSB, SJT)

Set `valuation_mode: optionality` in `valuation.json`. **Do not** downgrade to `watch` on Lawrence base IRR alone when `floor_pass` and primary metric clear the optionality gate.

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

Use `_system/prompts/deep_dive_template.md` and `_system/frameworks/report_prose.md`. Reader-first order:

1. **What this business is** — five plain sentences (no framework codes)
2. **Why the market might be wrong** — HK predictive attribute in prose
3. **Executive summary** — 120–180 words; synthesize 1–2 + return + stance
4. **Business & moat** — Stahl + Tier 2 + **Mental models in plain English** + **Hohn mechanics** + Munger
5. **Payoff & return** — five-question gate + dhando + expected return (Hohn bridge aligns with Lawrence/HK)
6. **Risks & inversion**
7. **Classification** + optional **Terms** + **[HUMAN REVIEW]** + **[PROPOSED MEMORY]**

Cross-checks / refreshes: update sections 1–5 when new filings arrive; full pillar rewrite only if thesis changed.

Lint: `python _system/scripts/lint_deep_dive.py {TICKER}` (`--legacy` for pre-refresh dives).

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
2. `_system/frameworks/report_prose.md` (voice and structure)
3. `_system/frameworks/hohn_business_analysis.md` (operating mechanics — every deep dive)
4. `_system/frameworks/optionality_valuation.md` (if FRMO / MSB / KEWL / SJT)
5. `_system/memory/MEMORY.md` (approved beliefs)
6. Primary docs in `{TICKER}/`
7. `_system/prompts/deep_dive_template.md` (output shape)
8. Appendix only if needed: `mental_models.md`, `lawrence_irr.md`
