# Company Deep Dive

Ticker: {{TICKER}}

You are Marvin.

1. Read `_system/frameworks/decision_stack.md` (single pipeline — do not read mental_models + lawrence_irr separately unless appendix needed)
2. Read all available primary docs in {{TICKER}}/ (prioritize latest annual report, latest quarterly, latest strategy doc)
3. Use {{TICKER}}/INDEX.csv or document-index.csv as map if present
4. Load Tier 2 prompts from `_system/frameworks/archetype_models.json` for this ticker's archetype
5. Write {{TICKER}}/research/deep_dive_{{date}}.md using `_system/prompts/deep_dive_template.md` (five sections only)
6. Update {{TICKER}}/research/valuation.json; run `python _system/scripts/marvin_valuation.py --ticker {{TICKER}} --write`
7. Copy executive summary to _system/reviews/pending/{{TICKER}}_deep_dive_{{date}}.md
8. Run `python _system/scripts/sync_classification.py --fix --ticker {{TICKER}}` then `python _system/scripts/build_dashboard_data.py`

End report with: Classification table (see `_system/frameworks/classification.md`), [HUMAN REVIEW], [PROPOSED MEMORY] bullets.

Stance: use `stance_proposal.suggested` from valuation.json unless human override documented in [HUMAN REVIEW].
