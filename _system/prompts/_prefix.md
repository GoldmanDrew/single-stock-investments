Workspace root: the repository root (the directory containing `_system/`).
Resolve it at runtime — do not assume a machine-specific path.

Before answering:
1. List all ticker folders at workspace root (exclude `_system`, names starting with `.`)
2. Read _system/agents/MARVIN.md
3. Read _system/memory/MEMORY.md and _system/memory/daily/{today}.md
3b. Read _system/memory/corrections.md — known agent errors and the correction
    for each. These are mistakes already made once; repeating one is the most
    expensive kind of error because it means the loop is not compounding. If a
    correction contradicts anything below, the correction wins.
4. Read _system/portfolio/holdings.md
5. Read _system/frameworks/decision_stack.md; for {TICKER} read valuation.json and open only frameworks from classification.md trigger map (see investment-frameworks.mdc — not the full frameworks folder)
6. Read _system/frameworks/investment_process.md when doing discover/download workflow
7. For ticker {TICKER}: read {TICKER}/research/thesis_card.json plus the latest research/evidence/filing_digest_*.md first (compact card: thesis, base IRR, key assumptions, open questions, top citations). Open the full deep dive only when the card is missing or your task changes the thesis/valuation itself. Read {TICKER}/README.md if present.
8. Prefer primary sources in ticker folders (PDFs, INDEX.csv) over memory
9. Write analysis to {TICKER}/research/ — not chat-only
10. Mechanical close: marvin_cloud_refresh.py {TICKER} --date YYYY-MM-DD (do not duplicate its steps)
11. Propose memory updates as [PROPOSED] in daily log only
12. Separate facts / inferences / opinions; cite file paths and page refs where possible
13. New _system/frameworks/*.md files require framework_governance.md checklist
14. When you hit a pipeline or tooling error that a future run could repeat —
    a silent overwrite, a config that shadows another, a file regenerated from
    somewhere unexpected — append a row to _system/memory/corrections.md with
    the error, the correction and the source. That file is read by every agent
    at step 3b; a fix recorded only in a chat transcript is lost.
15. Evaluation, not vibes: `python _system/scripts/calibrate_ssi.py` prints the
    three blueprint bars and says INSUFFICIENT DATA rather than inventing a
    number. Never claim a capability meets a bar the calibration does not
    measure. Adjudicate queued cases with
    `python _system/scripts/ssi_adjudicate.py status`.
