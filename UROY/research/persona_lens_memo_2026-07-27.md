# UROY — Power Zone / persona lens memo

**Date:** 2026-07-27  
**Companion:** `deep_dive_2026-07-27.md`, `valuation.json`, `new_urc_deal_economics.json`

## Security in one line

A **levered Wyoming trona-royalty and land estate** wrapped in a uranium royalty platform, listing into the U.S. as New URC.

## Routed Power Zones

| Rank | Profile | Why |
|------|---------|-----|
| Primary | `scarce_asset_optionality` | Perpetual mineral/surface rights + capital-free royalties (TPL-class method, not TPL clone) |
| Secondary | `capital_cycle` | Soda ash in deep oversupply; midcycle vs trough is the whole debate |
| Secondary | `credit_and_normalized_returns` | US$625m debt and ~1x interest cover make this an equity stub |

Personas that should speak: **Stahl/HK**, **Pabrai**, **Marathon capital cycle**, **Marks**. Personas that should mostly stay silent: **Hohn**, **Buffett/Weschler** (until FCF and leverage heal).

## Different conclusions on the same facts

```text
Same facts
  long-life trona royalties
  huge land grant estate
  uranium call options
  US$625m debt
  soda ash trough
  deemed US$3.64 / proxy US$2.96
        │
        ├─ Stahl/HK ──► "Own the scarce land vehicle for decades IF entry capitalizes midcycle cash, not hype."
        ├─ Capital cycle ──► "Best asset entry is the trough — but pay trough multiples, not average."
        ├─ Pabrai ──► "Downside not bounded for equity; debt turns a durable asset into a fragile stub."
        ├─ Marks/credit ──► "Underwrite coverage and refinance first; narrative options are residual."
        ├─ Lemon Cakes ──► "Market asleep; 15–20x fair; deal print rich; asymmetric if you get the cycle right."
        └─ Hohn/Buffett ──► "Silent / pass — not a high-quality compounder at this cash yield."
```

## What would change minds

| Persona | Falsifier / unlock |
|---------|-------------------|
| Pabrai | Net debt/EBITDA toward ≤3x on trough EBITDA; coverage clearly >2x |
| Stahl | Listing price that implies ≤~18x midcycle attributable EBITDA with intact land options |
| Capital cycle | Evidence China synthetic/trona supply is cutting and glass demand stabilizing |
| Marks | Transparent Royalty Notes schedule + liquidity runway >24 months without dilutive equity |
| Bull camp | Operator capacity additions showing up in royalty tons, not just press releases |

## Mechanical next step

`python _system/scripts/persona_lens.py --ticker UROY` after `marvin_cloud_refresh.py` so `lenses.json` matches classification.
