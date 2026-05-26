# AMZN Deep Dive Review — Decision Stack (2026-05-26)

**Agent:** Marvin  
**Full report:** `AMZN/research/deep_dive_2026-05-26.md`  
**Format:** `report_prose.md` refresh (What / Why mispriced / Hohn return math)

---

## Executive summary

Amazon **compounder / stable moat / partial dhando**. Q1-26 sales **$181.5B** (+17%); AWS **+28%**; OCF TTM **$148.5B** but FCF TTM **$1.2B** on AI capex. Lawrence uses **normalized $5.35 FCF/sh**, not spot TTM FCF. At **~$263**, base **3.6%** 10yr IRR. Stance proposal: **watch** (prior **hold** = human override).

## Expected return

| Scenario | Return | Terminal (Y10, model) |
|----------|--------|------------------------|
| Bear | -2.1% | ~$150/sh |
| Base | **3.6%** | ~$277/sh |
| Bull | 7.6% | ~$416/sh |

**Primary risk:** Prolonged AI capex overshoot without AWS/ads ROI.

`python _system/scripts/marvin_valuation.py --ticker AMZN --write`  
`python _system/scripts/lint_deep_dive.py AMZN`

## Classification

| Field | Value |
|-------|-------|
| Stance | watch (proposed) |
| Implied 10yr IRR | 3.6% (base) |
| Predictive attribute | none |
| Lawrence bucket | pricing_power |

## [HUMAN REVIEW]

- Confirm live price; capex path toward ~$90B sustainable.
- Hold override for strategic compounder sleeve only if sub-15% IRR acceptable.
- Strip Anthropic gain from quarterly NI.
