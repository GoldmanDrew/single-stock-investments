# Mental Models Catalog

**Purpose:** Reference appendix for Marvin research. **Workflow:** read `_system/frameworks/decision_stack.md` first — not this entire file on every dive.

**Sources:** `_system/reference/investment-wisdom/` (Munger, Pabrai, Stahl, Horizon Kinetics)  
**Approved beliefs:** `_system/memory/MEMORY.md` (human-promoted only)  
**Classification axes:** `_system/frameworks/classification.md`  
**Tier 2 by archetype:** `_system/frameworks/archetype_models.json`

Each model has: **Trigger** (when to apply), **Question** (what to ask), **Tier** (priority).

---

## How to use

1. **Every deep dive:** run Tier 1 + archetype Tier 2 models.
2. **If trigger matches:** run relevant Tier 3 models; tag report with **Predictive attribute** (see below).
3. **Cite sources** by path — not training memory alone.
4. **Propose new models** as `[PROPOSED]` in daily log; human promotes to `MEMORY.md`.

### Predictive attribute tag (optional report field)

| Value | Meaning |
|-------|---------|
| `equity_yield_curve` | Known/predictable future value + timeline; institutional time horizon creates discount |
| `dormant_asset` | Hidden value not in earnings multiple |
| `market_structure_discount` | Index/yield/K-1/small-cap exclusion misprices security |
| `transitory_problem` | Temporary, bounded operational or cash-flow interruption |
| `none` | No Tier 3 HK predictive attribute identified |

---

## Tier 1 — Universal (every deep dive)

| Model | Genius | Trigger | Question |
|-------|--------|---------|----------|
| **Latticework** | Munger | Always | Am I using models from multiple disciplines, or collecting isolated facts? |
| **Inversion** | Munger | Always | What would make this fail? Can we survive being wrong? |
| **Incentive-caused bias** | Munger | Management / operator assessment | Who gets paid for what? Does their incentive match unit-holder economics? |
| **Circle of competence** | Munger | Always | Can I explain this business in five plain sentences? If not, pass or defer. |
| **Psychology checklist** | Munger | Thesis challenge, cross-checks | Which of ~25 misjudgment tendencies are active? Any lollapalooza combination? |
| **Dhando asymmetry** | Pabrai | Always | Is this heads I win, tails I don't lose much — or am I paying for heroic assumptions? |
| **Simplicity** | Pabrai | Always | Is the business simple enough that I need not rely on a single fragile variable? |
| **Fat pitch discipline** | Pabrai | Sizing / stance | Am I forcing a trade, or waiting for margin of safety? |
| **Lawrence 5 questions** | Lawrence | Always | Understand, durable cash flow, aligned mgmt, cheap vs cash flow, why cheap? |
| **10-year IRR** | Lawrence | Modelable FCF / owner earnings | What IRR does today's price imply on a 10-year base case? |
| **IRR vs price** | Lawrence | After material price move | Did implied IRR cross 15% or 20%? Update stance? |
| **New idea bar** | Lawrence | Watchlist → onboard | Is IRR clearly above portfolio median *and* above weakest incumbent? |

**Sources:** `munger/Munger-1994-Elementary-Worldly-Wisdom.pdf`, `munger/Psychology-of-Human-Misjudgment.pdf`, `pabrai/` partner letters; `_system/frameworks/lawrence_irr.md` (Oakcliff / Bryan Lawrence).

---

## Tier 2 — Archetype-specific

### Stahl — Croupier / exchange / index infrastructure

| Model | Trigger | Question |
|-------|---------|----------|
| **Croupier toll** | Archetype = croupier | Does this facilitate pecuniary transactions without principal balance-sheet risk? |
| **Volume vs share** | Exchanges | Is handled volume growing even if market share slips? |
| **Fee model resilience** | Exchanges | Ad valorem (cyclical with markets) or per-trade/volume (more resilient)? |
| **Cycle normalization** | Croupiers with Cycle tag | Are current earnings peak / mid / trough vs normalized activity? |
| **Real diversification** | Portfolio scans | Are we mistaking cap-weight breadth for economic diversification? |

**Sources:** `stahl/Stahl-Croupier-Business-Model-2008.pdf`, `stahl/Stahl-Exchanges-Less-Talk-More-Figures-2009.pdf`, `stahl/Stahl-Achievement-of-Diversification-2020.pdf`

### Stahl — Corporate structure

| Model | Trigger | Question |
|-------|---------|----------|
| **Spinoff / simplification** | Conglomerate, forced separation | Does complexity hide segment economics that separation would reveal? |

**Source:** `stahl/Stahl-Spinoffs-Going-Separate-Ways-2015.pdf`

### Munger — Compounders

| Model | Trigger | Question |
|-------|---------|----------|
| **Moat durability** | Archetype = compounder / serial_acquirer | Can rational managers defend pricing power over long periods? |
| **Moat trajectory** | Same | Is the moat widening, stable, or eroding — not just this year's EPS? |

### Pabrai — Compounders & special situations

| Model | Trigger | Question |
|-------|---------|----------|
| **Cloning + verify** | Idea from another investor | Did I independently verify from primary sources before capital? |
| **Concentration vs capacity** | Portfolio sizing | Is this high-conviction enough for concentration given fund/portfolio constraints? |

---

## Tier 3 — Horizon Kinetics / Stahl (situation-specific)

These models extend Stahl beyond croupiers. Full extracts: `horizon-kinetics/`; vault: `C:\Users\werdn\Documents\Investing\Horizon Kinetics\hk_pdfs\`.

| Model | Trigger | Question | Predictive tag |
|-------|---------|----------|----------------|
| **Equity yield curve** | Contractual or high-confidence future value + date (bankruptcy plan, callable preferred, NPI deficit paydown, utility settlement) | What annualized return does the market require for each month/year until realization? Is the discount >25–35% at 2–3 years? | `equity_yield_curve` |
| **Time arbitrage** | Same as equity yield curve | Am I willing to hold through interim uncertainty that institutional 12-month horizons avoid? | `equity_yield_curve` |
| **Predictive vs descriptive** | Screening / index inclusion | Am I relying on backward-looking stats (P/E, yield, GICS) or forward predispositions (dormancy, recovery timeline)? | — |
| **Dormant asset** | Land, unused rights, off-balance-sheet value | Is there value priced at zero in the earnings multiple until a catalyst reveals it? | `dormant_asset` |
| **Transitory problem** | Dividend suspension, temporary deficit, litigation overhang with bounded resolution | Is the impairment temporary and contractually/mechanically bounded? What is the Mesabi/PG&E precedent? | `transitory_problem` |
| **Market structure discount** | Royalty trust, LP/K-1, sub-index, yield-screen exclusion | Is disdain from institutions/yield databases creating persistent mispricing unrelated to fundamental risk? | `market_structure_discount` |
| **Inverted equity yield curve** | Growth priced for perfection | Does implied long-run scale require negative slope (eBay case)? Where is the sell point? | — |
| **Curve flattening** | Approaching known catalyst | As the event nears, does return compress toward T-bill (efficiency at the end)? Should I avoid chasing late? | `equity_yield_curve` |

**Primary sources:**

| File | Topic |
|------|-------|
| `horizon-kinetics/Stahl-Equity-Yield-Curve-extract.txt` | Core theory; Johns Manville, PG&E, utility case studies |
| `horizon-kinetics/HK-Q1-2025-Commentary-extract.txt` | Predictive attributes; SJT, Mesabi, HE; PG&E preferred curve |
| `horizon-kinetics/HK-Q3-2025-Commentary-extract.txt` | SJT NPI deficit mechanics; royalty trusts |
| `horizon-kinetics/HK-Q1-2026-Commentary-extract.txt` | Royalty trust structural discounts |
| `horizon-kinetics/Stahl-Worth-The-Time-Predictive-Attributes-extract.txt` | Predictive attributes interview (Feb 2024) |
| `stahl/Compilation-of-Murray-Stahls-Writings.pdf` | Full shelf copy (search "Equity Yield Curve") |

### Equity yield curve — quick reference

1. Plot **expected annualized return** vs **years/months until value realization** (like a bond curve, steeper).
2. **Rarely plottable** — future stock price is subjective (NVIDIA growth debate).
3. **Plottable when:** dated recovery (bankruptcy emergence), callable preferred, NPI deficit erasure, regulatory settlement schedule.
4. **Observed steepness:** ~35% annualized at ~3 years in HK case studies; compresses near the event.
5. **Mechanism:** Institutional managers judged on 12-month relative returns — long-dated certain gains have low utility → lower price / higher yield for patient capital.

### Holdings map — Tier 3 triggers

| Holding | Likely Tier 3 models |
|---------|---------------------|
| **SJT** | Equity yield curve, transitory problem, market structure discount |
| **FRMO, royalty trusts, LPs** | Market structure discount |
| **Turnarounds with dated recovery** | Equity yield curve, transitory problem |
| **Land / resource optionality** | Dormant asset, equity yield curve |

---

## Tier 1 extensions — Munger worldly wisdom (cherry-picked)

Promote to MEMORY after review. Apply when trigger matches.

| Model | Trigger | Question |
|-------|---------|----------|
| **Compound interest** | Long holding periods | Does small edge + time dominate, or is this a terminal asset? |
| **Redundancy / margin of safety** | Engineering-heavy businesses | Are there backup systems — or single points of failure? |
| **Critical mass** | Network businesses | Has the business crossed tipping point, or is it sub-scale? |
| **Permutations & combinations** | Complex outcomes | Have I enumerated key paths, not just the base case? |
| **Opportunity cost** | Capital allocation | Is this the best use of capital vs next best holding? |

**Source:** `munger/Munger-1994-Elementary-Worldly-Wisdom.pdf`

---

## Tier 1 extensions — Pabrai (cherry-picked from letters)

| Model | Trigger | Question |
|-------|---------|----------|
| **Abhimanyu dilemma** | Complex compounders | Do I know how to *exit* as well as enter? (Chakravyuha) |
| **Low risk, high uncertainty** | Special situations | Is uncertainty masking low fundamental risk? |
| **Deny compounding to others** | Pricing | Am I paying a price that gives away my compounding to the seller? |
| **Redemption as feature** | Portfolio management | When cash is scarce, does that signal prioritize quality over dilution? |

**Sources:** `pabrai/Pabrai-Letter-l_010112.pdf`, `pabrai/Pabrai-Letter-l_010124.pdf`, `pabrai/Pabrai-Letter-l_010125.pdf`

---

## Report integration

Deep dives and cross-checks should include:

```markdown
## Mental models applied

| Model | Finding (1 line) |
|-------|------------------|
| … | … |

**Predictive attribute:** equity_yield_curve | … | none
```

Then standard **Classification** table (include Lawrence IRR fields when computed), **[HUMAN REVIEW]**, **[PROPOSED MEMORY]**.

---

## Maintenance

- New HK quarterly commentaries: add extract to `horizon-kinetics/`, update this file + `INDEX.md`.
- After human promotion, mirror key bullets in `MEMORY.md` — do not duplicate entire catalog there.
- Run `python _system/scripts/build_wisdom_manifest.py` after adding PDFs to wisdom folders.
