# Lawrence IRR (Oakcliff / Bryan Lawrence)

**Workflow:** `_system/frameworks/decision_stack.md` — this file is **math appendix** only.

**Purpose:** Quantitative expected-return discipline for Marvin deep dives. Complements Munger (quality), Pabrai (dhando / stance), Stahl (archetype / cycle), and Horizon Kinetics (equity yield curve for dated payoffs).

**Reference:** [Bryan Lawrence, Oakcliff Capital](https://moiglobal.com/bryan-lawrence-oakcliff-capital/) — 10-year IRR model, five questions, three business buckets.

---

## When to use

| Situation | Method | Tag |
|-----------|--------|-----|
| Modelable operating FCF / owner earnings | Full 10-year Lawrence IRR | `full` |
| Dated contractual recovery (NPI deficit, callable preferred, bankruptcy plan) | HK equity yield curve instead | `yield_curve` |
| Pre-revenue optionality, binary turnarounds | Scenario IRR table (bear/base/bull) | `scenario` |
| No credible cash-flow forecast | Skip numeric IRR; document why | `pending` |

Do **not** force a fake precision IRR when cash flows are unmodelable. Tag `irr_method: pending` and use qualitative valuation + HK lenses where applicable.

---

## A. Five questions (qualitative gate)

Answer **before** trusting the spreadsheet:

1. **Understand?** Can I explain the business and unit economics in plain language?
2. **Durable cash flow?** Will this business still throw off cash in 10 years (moat, regulation, obsolescence)?
3. **Shareholder-aligned management?** Incentives, capital allocation, insider ownership — do they match owners?
4. **Cheap vs cash flow?** Is today's price low relative to normalized owner earnings / FCF?
5. **Why cheap / misconception?** What does the market miss, and is that gap closeable?

If any answer is a clear **no**, fix the thesis or downgrade stance before optimizing IRR math.

---

## B. Lawrence business buckets

| Bucket | Description | Examples |
|--------|-------------|----------|
| `pricing_power` | Can raise price without losing volume | CSU, CPRT |
| `multi_sided` | Network / platform connecting two sides | ICE, exchanges, marketplaces |
| `low_cost` | Scale cost advantage | Costco-style, some croupiers |
| `other` | Does not fit cleanly — explain in prose |

---

## C. Base case model (10-year)

**Metric:** Prefer **adj. FCF per share** or **owner earnings per share** (not GAAP EPS distorted by fair-value marks or amortization).

**Steps:**

1. Set **Year 0 price** (current quote; cite date).
2. Set **starting FCF/sh** — normalize for cycle if Stahl `Cycle` = peak or trough.
3. Project FCF/sh for years 1–10 (growth can step down after year 5).
4. Assume **100% of FCF** returns to shareholders (dividends + buybacks) unless reinvestment clearly compounds at high ROIC — then reduce payout assumption and document.
5. **Terminal value at year 10:** `FCF_10 × exit_multiple` (P/FCF or EV/FCF equivalent).
6. Solve **IRR** on cash-flow stream: `CF0 = −price`, `CF1…CF9 = FCF_t`, `CF10 = FCF_10 + terminal`.

**Tool:** `python _system/scripts/marvin_valuation.py --ticker {TICKER} --write`  
Machine-readable assumptions live in `{TICKER}/research/valuation.json`.

---

## D. Sensitivity (required)

Report **bear / base / bull** with different:

- FCF growth (years 1–5 and 6–10)
- Exit multiple at year 10
- Optional: starting FCF normalization (mid vs peak cycle)

Show implied IRR at **current price** for each scenario.

---

## E. Stance mapping (Marvin proposes — human approves)

| Implied 10yr IRR (base) | Suggested stance | Notes |
|-------------------------|------------------|-------|
| **>20%** | accumulate / core | Fat pitch; size up if dhando + moat confirm |
| **15–20%** | hold | Adequate return; monitor IRR vs price |
| **<15%** | watch / trim | Reluctantly reduce unless strategic lock-in |
| New ideas | Higher bar | Must beat portfolio median **and** weakest incumbent |

IRR **crosses a band** after a material price move → flag in cross-check / refresh dive.

---

## F. Report section (required in deep dives)

Every deep dive with modelable cash flow includes:

```markdown
## Lawrence IRR

### Five questions
| # | Question | Answer |
|---|----------|--------|
| 1 | Understand? | … |
| … | … | … |

**Lawrence bucket:** multi_sided

### Model assumptions
| Input | Value | Source |
|-------|-------|--------|
| Price (date) | $X | … |
| Starting FCF/sh | $X | FY20XX adj. FCF ÷ shares |
| Growth Y1–5 / Y6–10 | X% / Y% | … |
| Exit P/FCF (Y10) | Xx | vs history / peers |

### Implied 10-year IRR
| Scenario | IRR | Notes |
|----------|-----|-------|
| Bear | X% | … |
| Base | X% | … |
| Bull | X% | … |

**IRR method:** full

### Stance vs IRR
Base IRR X% → **hold** (15–20% band). …
```

---

## G. Classification footer extensions

Add to the standard Classification table:

| Field | Values |
|-------|--------|
| **Implied 10yr IRR** (Lawrence) | e.g. `17% (base)` or `pending` |
| **IRR method** | `full`, `yield_curve`, `scenario`, `pending` |
| **Lawrence bucket** | `pricing_power`, `multi_sided`, `low_cost`, `other` |

Source of truth: `_system/portfolio/classification.json` + `{TICKER}/research/thesis.md` + `{TICKER}/research/valuation.json`.

---

## H. Integration with other lenses

| Lens | Role in IRR |
|------|-------------|
| **Stahl cycle** | Normalize starting FCF when `Cycle` = peak or trough |
| **Stahl croupier** | Exit multiple anchored to historical P/FCF through cycles |
| **Munger moat** | Gates question 2 — eroding moat → lower terminal multiple |
| **Pabrai dhando** | Downside in bear case must be bounded before sizing up on high IRR |
| **HK equity yield curve** | Use instead of full model when payoff is dated and contractual |

---

## Maintenance

- Recompute IRR on every **refresh** deep dive at current price.
- Store assumptions in `{TICKER}/research/valuation.json` for diff across dates.
- Promote stable IRR methodology bullets to `_system/memory/MEMORY.md` after human review.
