# Quality Checklist

**Workflow:** folded into `_system/frameworks/decision_stack.md` and `_system/prompts/deep_dive_template.md`. Use this as a completeness reference before human review.

## Business quality (→ Business & moat)
- [ ] Understand revenue mix and key segments
- [ ] Identify primary growth drivers (organic vs M&A vs pricing)
- [ ] Map competitive position and switching costs
- [ ] Assess management track record on capital allocation
- [ ] Run Tier 2 prompts from `archetype_models.json`

## Financial quality (→ Business & moat / Payoff & return)
- [ ] Review 3+ years of revenue, margin, and FCF trends
- [ ] Check balance sheet: net debt, maturity profile, off-balance-sheet items
- [ ] Understand unit economics where disclosed
- [ ] Note accounting policies that affect comparability

## Governance & risk (→ Risks & inversion)
- [ ] Read latest proxy / governance docs (US) or equivalent
- [ ] Flag related-party transactions, dual-class shares, or concentration risk
- [ ] List top 3 business-specific risks from primary filings
- [ ] Munger inversion — what kills the thesis?

## Valuation (→ Payoff & return)
- [ ] Five-question gate complete
- [ ] `valuation.json` updated; `marvin_valuation.py --write` run
- [ ] Bear / base / bull returns documented
- [ ] Stance proposal vs approved stance reconciled (override if needed)

## Prose & Hohn essentials (→ `report_prose.md`, `hohn_business_analysis.md`)
- [ ] `## What this business is` and `## Why the market might be wrong` present
- [ ] Executive summary 120–180 words; does not open with archetype labels
- [ ] `#### Return math in plain English` + `**Upside / downside from price:**`
- [ ] `**Primary risk:**` once; ≤3 secondary risks
- [ ] Fieldwork or "None this period" + what would upgrade conviction
- [ ] holding_co/optionality: look-through + SOTP/NAV + catalyst path in body
- [ ] `### Mental models in plain English` after Tier 2
- [ ] No em dashes in narrative (max 1 per report)

## Documentation
- [ ] Cite primary sources with file paths
- [ ] Separate facts / inferences / opinions ([Fact] / [Inference] / [Opinion] where non-obvious)
- [ ] End with classification table, optional Terms, and [HUMAN REVIEW] items
- [ ] `sync_classification.py` and `lint_deep_dive.py` pass (use `--legacy` only for unrefreshed old dives)
