# Dashboard sleeves (Drew / Michael)

Live site: [https://single-stock-investments-2wt.pages.dev/](https://single-stock-investments-2wt.pages.dev/) — Drew `#/drew`, Michael `#/michael`.

Primary tabs **Drew** (`#/drew`) and **Michael** (`#/michael`) read `GET /api/v1/sleeves/book?owner=` and fall back to `data/sleeves_drew.json` / `data/sleeves_michael.json`.

**Save notes** uses Sign in with GitHub (same allow-list as onboard) then `POST /api/v1/sleeves/notes`.

**Fills and IB sync** come from the local desk (`python -m _system.trading.sleeves.desk`) via HMAC `POST /api/v1/sleeves/ingest`. Set Cloudflare secret `SLEEVE_INGEST_TOKEN` and desk env `SLEEVE_INGEST_TOKEN` plus `SLEEVE_INGEST_URL` (Pages `/api/v1/sleeves/ingest`). Never put the token in frontend JS.

Holdings-table **D** / **M** buttons open the matching tab with that ticker in the note drawer. They do not place orders.
