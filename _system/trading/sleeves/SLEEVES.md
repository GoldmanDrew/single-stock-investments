# Sleeve split

Same IB account `U805366`. IB will not isolate capital. Classification is the source of truth.

## Michael (long-term residual)

Include:

- Residual stocks and unlevered funds after the exclusions below.
- Pre-`ETF_LS` baseline names.
- Strategy blacklist underlyings: JPM, BRK-B, AXP, APLD, SMR, CBRS.
- Expanded blacklist families (APLZ/APLX for APLD, SMZ for SMR, BRKC/BRKU for BRK-B, …). ls-algo never trades these; Michael trades them by hand, including LETF wrappers.

Exclude:

- SPX 0DTE: `secType=OPT` with symbol/tradingClass SPX or SPXW.
- Systematic LETF book: `orderRef` prefix `ETF_LS|` or `B5P|`, or membership in `data/etf_ls_universe.json` / current plan export, **unless** the ticker is in the blacklist family.

Cash and T-bill ETFs (BIL, SGOV, …) count in NAV as cash, not as idea rows.

## Drew

Empty until new fills tagged `DREW_SLEEVE`. Starts at $100k plus extra margin. Does not inherit Michael's residual names.

## Snapshot files (do not import ls-algo at runtime)

- `data/blacklist.json`
- `data/etf_to_under.json`
- `data/etf_ls_universe.json`

Refresh those JSON files when the ls-algo screener universe or blacklist changes.
