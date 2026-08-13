# Safeties

All gates fail closed. There is no UI override except `execution.allow_live` in `config.yaml`.

## Session

- Connect only to `127.0.0.1`.
- Bind account `U805366`. Refuse if TWS is on another account.
- Drew uses client ID 71, Michael 72. Do not use 0, 17, 41, 87, 90, or ls-algo worker offsets.
- NY4 Gateway and this local TWS cannot be logged in at the same time.

## Order

- `dry_run: true` until `allow_live: true`.
- Live send also requires retyping the ticker on the confirm card.
- Limit orders only. No market, no options, no SPXW, no OTC, no crypto.
- USD stocks/ETFs, SMART/NYSE/NASDAQ/AMEX/ARCA.
- Quote age must be under `quote_max_age_seconds` (15).
- Last may not move more than `price_band_pct` (1%) between propose and approve.
- `proposal_id` is one-shot.
- Same-ticker cooldown (10 minutes).
- Kill file `_system/trading/sleeves/KILL` blocks everything.

## Sizing

- Drew: max $25k per order, 20% of $100k per name, 12 names, max gross $200k.
- Michael: YAML caps; NAV from last classified residual book.
- BUY that would breach sleeve gross is rejected.

## Name filters

- Drew cannot submit systematic LETF names (`ETF_LS` / `B5P` / universe snapshot) or blacklist-family names (those are Michael's).
- Michael can submit blacklist-family names (JPM, BRK-B, AXP, APLD, SMR, CBRS and wrappers such as APLZ).
- Michael cannot submit SPXW or systematic LETF plan names.

## Logging

JSON logs under `_system/trading/sleeves/logs/` (gitignored). Local store under `data/local/` (gitignored).
