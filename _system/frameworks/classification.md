# Holdings classification (Decision Stack)

Unified labels from `_system/frameworks/decision_stack.md` — layers 1–5.

Replace the old single **thesis status** (intact / weakening / strengthening / unclear) with independent axes plus Lawrence return fields.

## Fields

| Field | Lens | Values | Question answered |
|-------|------|--------|-------------------|
| **Archetype** | Stahl | `croupier`, `compounder`, `serial_acquirer`, `platform`, `holding_co`, `optionality`, `turnaround`, `infrastructure` | What *is* this business in the pecuniary economy? |
| **Moat** | Munger | `widening`, `stable`, `eroding`, `unproven`, `n/a` | Is competitive advantage durable? |
| **Dhando** | Pabrai | `full`, `partial`, `none`, `pending` | Heads I win, tails I don't lose much? |
| **Stance** | Pabrai | `core`, `accumulate`, `hold`, `watch`, `trim`, `exit` | What do we *do* with capital? |
| **Cycle** | Stahl (croupiers) | `peak`, `mid`, `trough`, `—` | Normalized earnings vs current activity |
| **Implied 10yr IRR** | Lawrence | e.g. `17% (base)`, `pending` | Expected return at today's price (base case) |
| **IRR method** | Lawrence | `full`, `yield_curve`, `scenario`, `pending` | How IRR was computed |
| **Lawrence bucket** | Lawrence | `pricing_power`, `multi_sided`, `low_cost`, `other` | Oakcliff business taxonomy |

## Source of truth

- Pipeline: `_system/frameworks/decision_stack.md`
- Portfolio map: `_system/portfolio/classification.json`
- Per-ticker copy: `{TICKER}/research/thesis.md` → `## Classification` table
- Valuation + stance proposal: `{TICKER}/research/valuation.json`
- Dashboard: parsed by `_system/scripts/build_dashboard_data.py`
- Sync check: `python _system/scripts/sync_classification.py`

## Report footer (replaces thesis status)

Every deep dive and thesis update ends with:

```markdown
## Classification

| Field | Value |
|-------|-------|
| **Archetype** (Stahl) | … |
| **Moat** (Munger) | … |
| **Dhando** (Pabrai) | … |
| **Stance** | … |
| **Cycle** | … |
| **Implied 10yr IRR** (Lawrence) | … |
| **IRR method** | … |
| **Lawrence bucket** | … |

## [HUMAN REVIEW]
…

## [PROPOSED MEMORY]
…
```

## Dashboard display

- **Table column:** Archetype (primary badge)
- **Detail panel:** Moat · Dhando · Stance (+ Cycle when not `—`)
