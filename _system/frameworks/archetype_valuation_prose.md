# Archetype valuation prose (plain English)

**Purpose:** Make the **Valuation & IRR** section readable without finance shorthand. Pick rules from the row that matches `classification.json` → `archetype` (Stahl).

**Companion:** `report_prose.md` (voice) · `irr_assumption_ledger.md` (structure) · `archetype_models.json` (Tier 2 prompts) · `decision_stack.md` (method choice)

**JSON codes stay in** `valuation.json` and the **Classification** footer. **Narrative and ledger tables use plain English.**

---

## Universal valuation rules (all archetypes)

### Words to prefer in `## Valuation & IRR`

| Instead of | Write in tables and arithmetic |
|------------|--------------------------------|
| P₀ | **Price today** |
| FCF₀ / FCF/sh | **Starting free cash flow per share** (or **owner cash per share**) |
| OCF | **Cash from operations** |
| g1 / g2 | **Growth years 1–5** / **Growth years 6–10** |
| exit × / exit multiple | **Selling multiple in year 10** (e.g. "25 times cash flow") |
| IRR (first use in section) | **Annual return at today's price** (then "IRR" in bridge column is OK) |
| PV | **Present value** |
| SOTP | **Sum of the parts** |
| NAV | **Net asset value** |
| YoY | **Versus last year** or **year-over-year** (spell out once) |
| bn / B | **billion** (spell out in prose; "$52.5 billion" in tables) |
| capex | **Capital spending** (spell out once per report) |
| TTM | **Trailing twelve months** |
| mgmt | **Management** |
| rev | **Revenue** |
| op. income / OI | **Operating profit** |
| vs ~15% bar | **Versus our ~15% annual return target** |

### Section titles (readable)

Use these headings in the markdown (not internal codes):

```markdown
## Valuation & IRR (assumption ledger)

### Valuation bridge (bear, base, bull)
### Assumption ledger (base case)
### How we calculated the annual return (show your work)
```

You may keep `#### IRR arithmetic (show your work)` for lint compatibility, but the line under it should say **"How we calculated the annual return"** in the first sentence.

### Valuation bridge table (column headers)

| Plain header | Meaning |
|--------------|---------|
| **Case** | Bear / Base / Bull (and overlay rows if any) |
| **Method** | Ten-year cash flow / dated payoff / scenarios |
| **Main assumptions** | One short phrase (not `g1=11% g2=8% exit=25×`) |
| **Annual return** | Percent per year |
| **Vs 15% target** | pass / marginal / fail / overlay / info |

**Main assumptions examples (not shorthand):**

- Bad: `g1=11% g2=8% exit=25×`
- Good: `Cash flow grows 11% then 8%; sell at 25× year-10 cash flow`

### Assumption ledger (row labels)

Use the **Assumption** column for full phrases. Examples:

| # | Assumption | Value | Source or judgment |
|---|------------|-------|-------------------|
| 1 | Price today | $386 | NASDAQ, May 26, 2026 |
| 2 | Starting free cash flow per share | $5.85 | FY2025: cash from operations minus capital spending, divided by shares |
| 3 | Growth in years 1 through 5 | 11% per year | Cloud mix; post-capex normalization [Assumption] |
| 4 | Growth in years 6 through 10 | 8% per year | Base scenario |
| 5 | Selling multiple in year 10 | 25× cash flow | Base scenario |
| 6 | Time horizon | 10 years | Standard Lawrence model |

### Returns statement (one sentence, no codes)

Template:

> **Returns statement:** At **$X** per share, we expect about **Y% per year** over **N years** on the base case (normalized free cash flow of **$Z** per share).

---

## Archetype → valuation playbook

Read `archetype_models.json` for operating prompts. Below is **how to write the valuation section** for each type.

### `compounder` (e.g. CPRT, CSU, GOOGL, DHR)

| Field | Guidance |
|-------|----------|
| **Plain name** | "Cash-generating franchise" |
| **Default method** | `full` — ten-year free cash flow per share |
| **Lead metric** | Normalized **free cash flow per share** after one-offs |
| **Bridge story** | "We start with cash the owner could take out today, project growth for ten years, then assume we sell the business at a multiple of year-10 cash flow." |
| **Extra overlay** | `segment_cashflow` for multi-segment names; `ai_overlay` for hyperscalers — separate subsection, do not merge into base cash flow silently |
| **Arithmetic steps** | (1) Price today (2) Starting cash per share + normalization note (3) Year-10 cash before multiple (4) Year-10 value = cash × multiple (5) Annual return from full stream |

**Avoid:** Leading with P/E or revenue multiples without tying to owner cash.

---

### `croupier` (e.g. ICE, SPGI, 8697.T, OTCM)

| Field | Guidance |
|-------|----------|
| **Plain name** | "Toll collector on market activity" |
| **Default method** | `full` on **mid-cycle** owner cash (not peak activity) |
| **Lead metric** | Fees on volume; state **cycle position** in prose (peak / mid / trough) |
| **Bridge story** | "Activity is normalized to mid-cycle before we apply a multiple; peak earnings are not the starting point." |
| **Ledger must include** | One row: **Cycle adjustment** (what you normalized and why) |
| **Arithmetic steps** | Same as compounder + explicit sentence: "Current activity vs normalized activity" |

---

### `platform` (e.g. CSGP, BN)

| Field | Guidance |
|-------|----------|
| **Plain name** | "Network or marketplace with pricing power on volume" |
| **Default method** | `full` or `scenario` if monetization is still ramping |
| **Lead metric** | Revenue per user or per seat **and** owner cash when positive |
| **Bridge story** | "Volume on the network → revenue share → cash to owners; bear case stresses disintermediation or slower pricing." |
| **Ledger must include** | Row for **network growth** assumption separate from **price per unit** if both drive the model |

---

### `serial_acquirer` (e.g. TEQ.ST, CSU-style roll-ups)

| Field | Guidance |
|-------|----------|
| **Plain name** | "Roll-up of small acquisitions" |
| **Default method** | `full` on **pro forma** owner cash after synergies, or `scenario` if deal math is binary |
| **Bridge story** | "Base case uses fully synergized earnings power; bear delays integration or pays too much." |
| **Ledger must include** | **Acquisition pace** or **synergy timing** as its own row with [Assumption] |

---

### `holding_co` (e.g. FRMO)

| Field | Guidance |
|-------|----------|
| **Plain name** | "Company that owns stakes in other companies" |
| **Default method** | `yield_curve` — **dated payoff**, not ten-year DCF on parent GAAP earnings |
| **Section title** | `### Sum of the parts (how we get to payoff per share)` |
| **Lead metric** | Book or look-through value + **line-by-line uplifts** |
| **Bridge story** | "We add carrying value, listed stakes, and dated catalysts to a payoff price in year N, then annualize versus price today." |
| **Arithmetic steps** | Running sum table: book + line 1 + line 2 = payoff; then `(payoff ÷ price)^(1/years) − 1` in words |
| **Avoid** | Parent P/E or consolidated EPS as the only anchor |

---

### `optionality` (e.g. KEWL, MSB, SJT, APLD, CMSG)

| Field | Guidance |
|-------|----------|
| **Plain name** | "Asset with a floor plus an optional upside" |
| **Default method** | `yield_curve` (royalties, land) or `scenario` (pre-profit) |
| **Section title** | `### Payoff path and annual return` |
| **Lead metric** | **Floor** (royalty, land, book) + **option** (development, litigation, index inclusion) |
| **Bridge story** | "Base case values the floor at zero option value; bull assigns a dated payoff to the option." |
| **Ledger must include** | **Floor value**, **Option payoff**, **Date of payoff**, **Probability or scenario weight** (if scenario method) |
| **Stance rule** | Do not downgrade to watch on low Lawrence IRR alone when `optionality_valuation.md` gate passes — say so in plain English |

---

### `turnaround` (e.g. QDEL)

| Field | Guidance |
|-------|----------|
| **Plain name** | "Business fixing balance sheet or margins" |
| **Default method** | `scenario` — bear / base / bull owner cash paths |
| **Bridge story** | "Each case is a different path for margins, capital, and exit multiple; base is not 'steady state' until stated." |
| **Ledger must include** | **Cost program** or **capital ratio** row with filing or [Assumption] |
| **Arithmetic steps** | Label steps **Bear / Base / Bull** in short prose before the table |

---

### `infrastructure` (e.g. WBI)

| Field | Guidance |
|-------|----------|
| **Plain name** | "Physical asset with contracted or regulated cash flows" |
| **Default method** | `full` on **normalized levered free cash flow** or distribution yield + growth |
| **Bridge story** | "Traffic or tariff × contracted life → cash to equity; compare to bond-like alternatives." |
| **Ledger must include** | **Maintenance capital spending** vs growth capital; **Payout ratio** if relevant |

---

## Archetype × `irr_method` quick map

| Archetype | Usually | Valuation section emphasis |
|-----------|---------|----------------------------|
| compounder | `full` | Ten-year owner cash; one normalization paragraph |
| croupier | `full` | Mid-cycle normalization + cycle row |
| platform | `full` / `scenario` | Volume × price → cash |
| serial_acquirer | `full` / `scenario` | Synergy timing |
| holding_co | `yield_curve` | Sum of the parts table |
| optionality | `yield_curve` / `scenario` | Floor + option + date |
| turnaround | `scenario` | Three paths, capital repair |
| infrastructure | `full` | Yield + reinvestment |

---

## Executive summary tie-in

The executive summary may state **one** annual return percent. Use:

> "…about **2% per year** over ten years at today's price…"

Not:

> "…base IRR 2.1% on FCF₀…"

Footer **Classification** table may keep `Implied 10yr IRR` and `IRR method` labels for the dashboard.

---

## Lint and agents

- `report_prose.md` — abbreviation ban and tone
- `.cursor/rules/valuation-plain-english.mdc` — applies to `**/research/*.md`
- `lint_deep_dive.py` — structure unchanged; optional warn on dense shorthand in Valuation section (future)

When refreshing: set `valuation.json` first, then write prose using this file for the ticker's archetype.
