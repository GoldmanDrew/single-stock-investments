# Dashboard sleeves (Drew / Michael)

Live site: [https://single-stock-investments-2wt.pages.dev/](https://single-stock-investments-2wt.pages.dev/) — Drew `#/drew`, Michael `#/michael`.

Primary tabs **Drew** (`#/drew`) and **Michael** (`#/michael`) read `GET /api/v1/sleeves/book?owner=` and fall back to `data/sleeves_drew.json` / `data/sleeves_michael.json`.

**Save notes** uses Sign in with GitHub (same allow-list as onboard) then `POST /api/v1/sleeves/notes`.

**IB sync** (`python -m _system.trading.sleeves.sync_ib`) reads account `U805366` the same way ls-algo and SPX 0DTE do (TWS `127.0.0.1:7496`, or `--flex` OpenPositions XML). Michael gets the residual long-term book. Drew stays empty until `DREW_SLEEVE` fills. HMAC `POST /api/v1/sleeves/ingest` updates D1 when `SLEEVE_INGEST_TOKEN` is set.

Holdings-table **D** / **M** buttons open the matching tab with that ticker in the note drawer. They do not place orders.
