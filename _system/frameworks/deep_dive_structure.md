# Deep dive structure (single source of truth)

**Purpose:** One place for *what sections exist* and *what not to repeat*. Voice lives in `report_prose.md`; pipeline in `decision_stack.md`; IRR detail in `irr_assumption_ledger.md` + `lawrence_irr.md`.

**Template:** `_system/prompts/deep_dive_template.md`  
**Lint:** `python _system/scripts/lint_deep_dive.py {TICKER}`

---

## Where rules live (no duplication)

| Question | Read this only |
|----------|----------------|
| What sections, what order | **This file** |
| IRR assumption ledger (repeatable) | `irr_assumption_ledger.md` |
| Analysis order | `decision_stack.md` |
| Voice / plain English | `report_prose.md` |
| Valuation readable by archetype | `archetype_valuation_prose.md` |
| IRR formulas | `lawrence_irr.md` § F |
| Third-party approval | `third_party_sources.md` |
| Approved Substacks | `approved_substacks.md` |
| Cursor pointers | `.cursor/rules/investment-frameworks.mdc` + `marvin-core.mdc` |

---

## Report outline (required order)

| # | Section | Say once |
|---|---------|----------|
| 1 | Header links | date, prior dive, `valuation.json`, evidence digest, third-party index, **`adversarial_{date}.md` (Milly, required)** |
| 2 | **What this business is** | ≤5 sentences — **company overview starts here** |
| 3 | **Why the market might be wrong** | 2–3 sentences + predictive attribute |
| 4 | **Executive summary** | 120–180 words; **one** base IRR % — **no formulas** |
| 5 | **Primary sources reviewed** | Inventory table only (10-K, 10-Q, IR, approved/pending third party) |
| 6 | **Business & moat** | Stahl, mental models, Hohn mechanics — **no IRR, no valuation bridge** |
| 7 | **Approved Substack** | Only if ticker in `approved_substacks.md` |
| 8 | **Blended estimate** | Only if approved/pending external view cited |
| 9 | **Payoff & return** | Gates, dhando, stance — **points to Valuation & IRR** |
| 10 | **Risks & inversion** | Primary risk + ≤3 bullets |
| 11 | **Valuation & IRR (assumption ledger)** | **End of analysis** — bridge + ledger + IRR arithmetic |
| 12 | Footer | Classification, Terms, [HUMAN REVIEW], [PROPOSED MEMORY] |

---

## Business & moat (overview body)

| Subsection | Required | Do not include here |
|------------|----------|---------------------|
| What (Stahl + Lawrence bucket) | Yes | IRR %, payoff $ |
| Mental models | Yes | Duplicate Tier 2 + plain English |
| Business mechanics (Hohn) | Yes | snapshot, pillars, fieldwork, disruption |
| Moat (Munger) | Yes | Valuation bridge, assumption ledger |
| Look-through / catalyst (holdco only) | If needed | Full SOTP math — that lives in §11 |
| **Segment map** (multi-segment compounder) | If `segment_cashflow` overlay | Segment PV math — that lives in §11 |

---

## Valuation & IRR (assumption ledger) — end of report

| Subsection | Required |
|------------|----------|
| Price today + method tag | Yes |
| **Valuation bridge** | bear / base / bull table |
| **Assumption ledger (base case)** | Table: every input + source or **[Assumption]** |
| **IRR arithmetic (show your work)** | Numbered steps; no unexplained payoffs |
| **Upside / downside from price** | One line |
| **Returns statement** | One sentence; = exec summary % |
| SOTP / look-through tables | If `holding_co` / `optionality` |
| **Segment cash-flow build** | If `valuation_overlay: segment_cashflow` (GOOGL-style) |

Spec: `irr_assumption_ledger.md`. JSON: `valuation.json` + `sotp_build` when SOTP; + `segment_build` when segment overlay.

---

## Deduplication rules

| Redundant pattern | Fix |
|-------------------|-----|
| IRR in Business & moat + at end | **End only** |
| Valuation bridge in two places | **End only** |
| Exec summary shows full math | One % in exec; math in §11 |
| Tier 2 + Mental models | **Mental models** only |
| Pending third party in base IRR | **[PENDING APPROVAL]**; not in `valuation.json` base |

---

## Refresh workflow (all holdings)

```bash
python _system/scripts/build_filing_evidence.py {TICKER}
python _system/scripts/marvin_valuation.py --ticker {TICKER} --write
python _system/scripts/refresh_deep_dive_v2.py {TICKER}
python _system/scripts/lint_deep_dive.py {TICKER}
```

Batch: `python _system/scripts/refresh_deep_dive_v2.py --all`

---

## Mental models (single format)

| Model | Finding | Source |
|-------|---------|--------|

Do not restate in Substack section unless new external detail.

---

## Payoff & return (slim)

1. Five-question gate  
2. Predictive attribute (one sentence)  
3. Dhando table  
4. Stance: `Scenarios and all IRR assumptions: see ## Valuation & IRR (assumption ledger) and valuation.json.`

No bear/base/bull table here. No IRR formulas here.
