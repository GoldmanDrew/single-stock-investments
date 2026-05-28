# Deep dive refresh v2 (Marvin workflow)

**Date:** 2026-05-28  
**Goal:** Overview-first reports; **Valuation & IRR (assumption ledger)** at the end; every IRR input explained.

---

## Per ticker (repeat for each holding)

```bash
python _system/scripts/build_filing_evidence.py {TICKER}
python _system/scripts/marvin_valuation.py --ticker {TICKER} --write
python _system/scripts/refresh_deep_dive_v2.py {TICKER}
python _system/scripts/lint_deep_dive.py {TICKER}
```

Batch all holdings:

```bash
python _system/scripts/refresh_deep_dive_v2.py --all
python _system/scripts/lint_deep_dive.py
```

---

## What refresh does

1. Reads latest `deep_dive_*.md` and `valuation.json`.

2. Keeps overview sections (What → Business & moat) without valuation math.

3. Moves / generates **## Valuation & IRR (assumption ledger)** before Classification.

4. Builds **Assumption ledger** table from `valuation.json` (and `sotp_build` for FRMO-style).

5. Updates `third-party-analyses/pending.md` for new `research-notes/` PDFs.

6. Writes `deep_dive_{today}.md`.



---



## Human review after batch



- [ ] Approve pending third parties in `_system/frameworks/third_party_sources.md`

- [ ] Replace FRMO Investment A **+4.50** when look-through table filed

- [ ] Sign off **[HUMAN REVIEW]** lines per ticker

