# Dashboard sleeves (Drew / Michael)

Live site: [https://single-stock-investments-2wt.pages.dev/](https://single-stock-investments-2wt.pages.dev/) — Drew `#/drew`, Michael `#/michael`.

## How the book is run

1. **Residual long-term names.** Michael's tab is the configured Magis IBKR account after dropping the ls-algo universe (unless the name is a blacklist family Michael trades by hand) and SPX / XSP. Drew starts empty and only receives fills tagged `DREW_SLEEVE`.
2. **Write the thesis.** Every name needs why we own it and what would make it a permanent loss of capital. Notes save on the dashboard after GitHub sign-in. They do not send orders.
3. **Hold for years.** The gain column is a fact about cost versus mark. It is not a trading signal. Money-weighted IRR appears only after dated buys and sells.
4. **Watch concentration.** Independence is 0 while every name sits in one cluster. Assign a cluster in the note. Size is a process choice.
5. **Orders stay local.** `python -m _system.trading.sleeves.desk` or `python -m _system.trading.sleeves.send`. Quote live from IB, save a draft, retype the ticker, then send a DAY limit. The hosted site cannot reach Gateway.

## Wiring

Primary tabs **Drew** (`#/drew`) and **Michael** (`#/michael`) read `GET /api/v1/sleeves/book?owner=` and fall back to `data/sleeves_drew.json` / `data/sleeves_michael.json`.

**Save notes** uses Sign in with GitHub (same allow-list as onboard) then `POST /api/v1/sleeves/notes`.

**IB sync** (`python -m _system.trading.sleeves.sync_ib`) requires `IBKR_ACCOUNT` and reads the same account as ls-algo and SPX 0DTE (TWS `127.0.0.1:7496`, or `--flex` OpenPositions XML). HMAC `POST /api/v1/sleeves/ingest` updates D1 when `SLEEVE_INGEST_TOKEN` is set.

Holdings-table **D** / **M** buttons open the matching tab with that ticker in the note drawer. They do not place orders.
