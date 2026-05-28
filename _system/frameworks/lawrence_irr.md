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

## F. IRR arithmetic (show your work) — required

**Placement:** **`## Valuation & IRR (assumption ledger)`** at the **end** of the report (after Risks, before Classification). **Not** in Business & moat. Spec: `irr_assumption_ledger.md` · `deep_dive_structure.md`.

**Rule:** Explain like a high schooler could follow. **Never jump to a payoff price or year count without saying where they came from.** The % is the last step, not the first.

**Forbidden:** “Payoff year 5 is $18” with no buildup. Payoff and years are **model assumptions** in `valuation.json` unless contractually dated (then cite the contract).

### A. Catalyst / payoff IRR (`irr_method`: `yield_curve` or holdco SOTP)

Use **numbered steps** for the base case. Bear/bull can be shorter but must still state payoff logic in one line each.

```markdown
#### IRR arithmetic (show your work)

**Step 1 — Price today (what you pay now)**  
- OTC close **$6.70** per share (Stooq 2026-05-22).  
- This is observable; not our estimate.

**Step 2 — Anchor from filings (what book says today)**  
- FRMO book value **$8.55** per share (Feb 28, 2026 quarterly).  
- So the market price is about **22% below book**: ($8.55 − $6.70) ÷ $8.55 ≈ **22%** discount.

**Step 3 — Payoff price (sum-of-parts; must add to the payoff)**  
- List **shares** from the filing (denominator).  
- Show **GAAP $/sh** for each identifiable piece (equity ÷ shares).  
- Add **uplift $/sh** per line with one-line math (e.g. `7.02 × 64% = 4.50`).  
- **Running sum** must equal payoff (e.g. `8.55 + 4.50 + … = 18.00`). Store lines in `valuation.json` `sotp_build` when possible.  
- **2.1× book** and **2.7× price** go **after** the sum as checks (`18 ÷ 8.55`, `18 ÷ 6.70`), not as drivers.  
- Label **[Assumption]** / **[HUMAN REVIEW]** on any line not filing-derived (especially opaque buckets like FRMO “Investment A”).  
- For holdcos, add an **assumption ledger**: each uplift split into sub-lines with **today (filing) → assumption → dollars → ÷ shares**. Show **historical book** if using a growth rate (e.g. 3%/yr = `book × (1.03^5 − 1)`). If sub-lines do not sum to the model line, show **tie-out slack** explicitly.

**Step 4 — Time horizon (why 5 years, not 10)**  
- Lawrence **10-year** math is for steady earners. FRMO is a **catalyst** story (listings, re-marks).  
- We assume **5 years** as the middle of a **3–7 year** window for those catalysts to show up in the share price. **Five years is a model choice** in `valuation.json`, not a management guidance date.

**Step 5 — Total return if payoff happens**  
- Gain multiple = payoff ÷ price today = $18.00 ÷ $6.70 = **2.686**  
- Total return = 2.686 − 1 = **168.6%** (about **169%** total gain if we are right)

**Step 6 — Spread that gain over 5 years (annualized IRR)**  
- Formula: annual return = (payoff ÷ price today)^(1 ÷ years) − 1  
- (18.00 ÷ 6.70)^(1/5) − 1 = (2.686)^(0.2) − 1 = **0.219** → **21.9%** per year

**Bear (shorter):** Payoff **$9.50** ≈ “discount closes toward book, catalysts stall” → (9.50 ÷ 6.70)^(1/5) − 1 = **7.2%**/yr  
**Bull (shorter):** Payoff **$25.00** ≈ “most catalysts land” → (25 ÷ 6.70)^(1/5) − 1 = **30.1%**/yr
```

### B. Scenario owner-cash IRR (`irr_method`: `scenario`)

When `marvin_valuation.py` uses starting owner cash/sh, growth, exit multiple:

```markdown
#### IRR arithmetic (show your work)

**Base case** (must match `valuation.json`)
- Price today: **$30.00**
- Owner cash year 0: **$1.45/sh** (source: …)
- Growth years 1–5 / 6–10: **5% / 3.5%**
- Exit multiple year 10: **10×**
- Year-10 value per share ≈ $1.45 × (1.05)^5 × (1.035)^5 × 10 ≈ **$…** (or cite tool output)
- IRR = (year-10 total return)^(1/10) − 1 → **18.0%** per year  
  *(Show tool: `python _system/scripts/marvin_valuation.py --ticker QDEL`)*

If manual steps are too long, show **inputs** and **one** explicit check, e.g. terminal value = $1.45 × 1.28 × 1.18 × 10 = $X; (X / $30)^(1/10) − 1 = Y%.
```

### C. Full 10-year Lawrence (`irr_method`: `full`)

```markdown
#### IRR arithmetic (show your work)

**Base case**
- Price today: **$153**
- FCF₀ per share: **$7.41** (mid-cycle, FY2025 10-K)
- FCF growth Y1–5 / Y6–10: **8% / 5%**
- Exit P/FCF year 10: **18×**
- Terminal value Y10 ≈ FCF₁₀ × 18; sum dividends + terminal; IRR on CF₀ = −price → **11.0%**  
  *(Inputs from `valuation.json`; verify with `marvin_valuation.py --write`)*
```

### D. HK yield curve (`irr_method`: `yield_curve` on dated recovery)

Show dated payoffs per year if plottable; otherwise same as (A) for each milestone.

### E. When `irr_method`: `pending`

Omit IRR arithmetic; state why in Payoff & return.

**After** IRR arithmetic, one line: `**Upside / downside from price:**` and `**Returns statement:**` (must match base %).

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
| **Segment cash-flow overlay** | Multi-segment compounders: sum segment PVs + options; cross-check consolidated IRR — `segment_cashflow_valuation.md` |

---

## I. Segment cash-flow overlay (multi-segment compounders)

When `valuation_overlay: segment_cashflow` in `valuation.json`, run **both**:

1. **Lawrence consolidated** `full` IRR (`marvin_valuation.py`) — **stance gate**
2. **Segment build** — Speedwell-style explicit assumptions per reportable segment; **sum** discounted owner cash; **reverse DCF** business return at P₀

**Speedwell (Drew Cohen):** invert valuation—fix price, model cash flows, solve implied return; burden loss segments (e.g. Reality Labs) with **zero** option terminal in base.

**Hohn / TCI:** segment narrative (Alphabet: Search, YouTube, Cloud, Waymo **$0** base) in `_system/reference/investment-wisdom/tci/TCI-Q2-2018-Investor-Newsletter-extract.txt`.

**Report:** `### Segment cash-flow build` + `#### Segment IRR arithmetic` in Valuation & IRR; `#### Segment map` in Business & moat. Spec: `segment_cashflow_valuation.md`.

### F2. Segment IRR arithmetic (snippet)

```markdown
#### Segment IRR arithmetic (show your work)

**Step 1 — Segments from 10-K** (cite path)  
**Step 2 — Owner cash Y0 per segment** (op income bridge; capex alloc **[Assumption]**)  
**Step 3 — Project Y1–10 + terminal per segment**  
**Step 4 — Options** (base $0; bull if any)  
**Step 5 — Sum PV/sh** = $A · **Lawrence consolidated IRR** = B% · **Tie-out slack** = …
```

---

## Maintenance

- Recompute IRR on every **refresh** deep dive at current price.
- Store assumptions in `{TICKER}/research/valuation.json` for diff across dates.
- Promote stable IRR methodology bullets to `_system/memory/MEMORY.md` after human review.
