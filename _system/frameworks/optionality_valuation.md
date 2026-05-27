# Optionality & Limited-Downside Valuation

**Purpose:** Secondary valuation layer for names where **Lawrence 10yr FCF IRR** and standard **Hohn operating bridges** understate the investment case. Use when the payoff is **asymmetric** — bounded floor + open-ended or dated catalyst — not when heroic growth assumptions are required.

**Do not use for:** operating compounders priced on earnings (use Lawrence `full`), or binary pre-revenue bets with no asset floor (use `scenario` with explicit failure modes).

---

## When to trigger (any of)

| Trigger | Examples |
|---------|----------|
| **Asset floor ≥ price risk** | Cash + book > ~50% of price; no debt; depleting trust with cash reserve |
| **Look-through NAV / SOTP** | Holdco; private stakes marked below fair value |
| **Dormant asset priced at zero** | Royalty not in run-rate; Copperwood option; HK stake at cost |
| **HK transitory + yield curve** | Distribution suspension, bonus tier gap, legal recovery with timeline |
| **Market structure discount** | Royalty trust / OTC / K-1 excluded from yield screens |

Set `valuation_mode: optionality` in `{TICKER}/research/valuation.json` and document `optionality_gate` (below).

---

## Three archetype overlays

### A. Holdco flywheel + catalyst stack (FRMO)

**Sources:** `_system/reference/investment-wisdom/stahl/`; approved Substacks — `_system/frameworks/approved_substacks.md`, `FRMO/third-party-analyses/references.md`; [SSI FRMO flywheel](https://specialsituationinvesting.substack.com/p/frmo-corp-a-frictionless-flywheel); [LCI crypto conglomerate](https://lemoncakesinvesting.substack.com/p/frmo-frmo-corp-commentary-on-frmos)

| Lens | Question |
|------|----------|
| **Flywheel / permanent capital** | Does the vehicle compound book without fund-flow risk? |
| **Sum-of-parts** | List top stakes + cash; mark private assets at **fair** not GAAP |
| **Catalyst stack** | Dated or probable events: HK IPO, MIAX IPO, CMSG IPO, Winland control → operating earnings |
| **Insider alignment** | Director/officer ownership %; compensation structure |
| **Floor** | Book value, net cash, no recourse debt |

**Primary metrics (not 10yr FCF):**

1. **NAV / look-through discount** — price vs FRMO-attributable book and vs SOTP fair value  
2. **Catalyst IRR** — annualized return if named catalysts close in X years (HK re-mark, MIAX listing)  
3. **Dhando floor** — bear case = book erosion or flat NAV, not operating bankruptcy  

**Predictive attribute:** `dormant_asset` (private stakes below fair value)

---

### B. Mineral / land floor + free option (KEWL)

**Sources:** Special Situation Investing — [KEWL intro](https://specialsituationinvesting.substack.com/p/keweenaw-land-association-kewl), [KEWL update](https://specialsituationinvesting.substack.com/p/update-keweenaw-land-association)

| Lens | Question |
|------|----------|
| **Floor** | Cash + treasuries per share; audited book; acreage $/acre vs peer transactions |
| **Burn runway** | Pro forma cash burn ex one-offs; years of runway at bare-bones opex |
| **Free option** | Model **zero** production royalties in base; size Copperwood (or next lease) in bull only |
| **Patient capital** | Repurchases above/below book; Cornwall/Mai alignment |
| **Permutations** | 667K-acre package, contiguous blocks, new lessees independent of Copperwood |

**Primary metrics:**

1. **Floor value / price** — book + cash vs market cap (flag when price **above** book — dhando weakens)  
2. **Option yield** — royalty $ if named project hits ÷ market cap (Substack ~23–24% FCF yield best case)  
3. **Pabrai low risk, high uncertainty** — tails bounded by liquid assets; heads = production royalties  

**Predictive attribute:** `dormant_asset` + optional `equity_yield_curve` if construction/production date firms up

---

### C. Passive royalty trust — HK curve (MSB)

**Sources:** `_system/reference/investment-wisdom/horizon-kinetics/HK-Q4-2024-Commentary-extract.txt` (Mesabi case study); `HK-Q1-2025-Commentary-extract.txt`; `HK-Q3-2025-Commentary-extract.txt`

| Lens | Question |
|------|----------|
| **Transitory problem** | Is distribution/bonus gap **temporary** with contractual/mechanical resolution? |
| **Equity yield curve** | Plot annualized return vs years until normalized payouts + legal clarity |
| **Normalized distribution yield** | Use **mid-cycle / post-recovery** $/unit, not single depressed quarter |
| **Market structure discount** | ETF/yield-screen exclusion; “almost unknown” despite decades of outperformance |
| **No management risk** | Trust admin only — operator dispute is legal, not governance |

**HK Mesabi facts (commentary):**

- 40yr annualized total return **~9.8%** to unitholders (1985–2024)  
- Arbitration award **$5.43/unit** — price moved one-for-one when spreadsheet-ready  
- At **~$26**, normalized annual distribution **>$2/unit** → **>8% yield**  
- Q1 2025: parallel to SJT — suspension/reinstatement, **time arbitrage**  
- Q3 2025: Cliffs premium dispute; **$72M** prior award; second arbitration on intercompany/idling  

**Primary metrics:**

1. **Normalized distribution yield** at current price (not TTM depressed)  
2. **Equity yield curve** — payoff = cumulative distributions + terminal unit value over 3–8 years  
3. **Legal catalyst** — arbitration timeline as dated recovery (curve steepness)  

**Predictive attributes:** `equity_yield_curve`, `transitory_problem`, `market_structure_discount`

---

## valuation.json shape

```json
{
  "valuation_mode": "optionality",
  "method": "yield_curve",
  "optionality_gate": {
    "framework": "holdco_sotp | mineral_floor_option | hk_royalty_curve",
    "floor_pass": true,
    "floor_metric": "book_per_share",
    "floor_value": 8.55,
    "primary_metric": "normalized_yield",
    "primary_return_pct": 8.0,
    "notes": "Do not use base Lawrence IRR as sole stance gate"
  },
  "scenarios": { "bear": {}, "base": {}, "bull": {} }
}
```

---

## Stance logic (optionality mode)

When `valuation_mode == optionality`, Marvin **does not** auto-downgrade to `watch` solely because Lawrence base IRR < 15%.

| Condition | Stance proposal |
|-----------|-----------------|
| `floor_pass` + `dhando` full/partial + primary metric ≥ 15% | `hold` or `accumulate` |
| `floor_pass` + bull scenario ≥ 20% + incumbent sleeve | `hold` (document override) |
| `floor_pass` + primary metric 7–15% (normalized yield / SOTP discount) | `hold` or `watch` — size for option |
| Price above floor / weak dhando | `watch` |
| `dhando` none or floor fails | `watch` or `trim` |

Always reconcile with human **stance** in `classification.json`; document overrides in `[HUMAN REVIEW]`.

---

## Report integration

In deep dives for optionality names, add after **Payoff & return**:

```markdown
### Optionality overlay

| Field | Value |
|-------|-------|
| Framework | holdco_sotp / mineral_floor_option / hk_royalty_curve |
| Floor | … |
| Free option / catalyst | … |
| Primary metric | … |
| Predictive attribute(s) | … |
```

Reference this file + external sources in `[PROPOSED MEMORY]` when promoting beliefs.

---

## Holdings map

| Ticker | Overlay | Primary metric |
|--------|---------|----------------|
| **FRMO** | Holdco SOTP + catalyst stack | Look-through NAV discount; catalyst IRR |
| **KEWL** | Mineral floor + Copperwood option | Option yield (bull); book/cash floor |
| **MSB** | HK royalty curve | Normalized distribution yield + arbitration timeline |
| **SJT** | HK royalty curve (existing) | NPI deficit paydown curve |
