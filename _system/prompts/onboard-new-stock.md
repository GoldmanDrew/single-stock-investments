# Onboard New Stock

Use the **onboard orchestrator** (dashboard or CLI) — do not manually edit four files.

## Dashboard (cloud)

1. Open portfolio dashboard → **Sign in with GitHub** (one-time OAuth — no PAT)
2. **+ Add holding** → fill ticker, company, market
3. **Run onboard on GitHub** — dispatches `marvin-onboard.yml`
4. Workflow commits scaffold + downloads to `main`, then runs Marvin deep dive (PR)

### OAuth App setup (one time, repo admin)

1. [New OAuth App](https://github.com/settings/developers) — enable **Device Flow**
2. Copy **Client ID** → repo variable **`OAUTH_CLIENT_ID`**
3. Deploy CORS proxy (required): see `dashboard/oauth-proxy/README.md` → set **`OAUTH_PROXY_URL`**

## CLI (local)

```powershell
python _system/scripts/onboard_ticker.py --ticker TICKER --company "Name" --market US --ir-url "https://ir.example.com"
```

## GitHub Actions

```powershell
gh workflow run marvin-onboard.yml -f ticker=SJT -f company="San Juan Basin Royalty Trust" -f market=US
```

## Watchlist only

```powershell
python _system/scripts/onboard_ticker.py --ticker XYZ --company "Name" --market US --watchlist-only
```

Promote from watchlist: dashboard watchlist chip → pre-fills form → submit with **from_watchlist**.

## Registry (source of truth)

`_system/portfolio/registry.json` — syncs to `holdings.md`, `classification.json`, `us_ticker_config.json`:

```powershell
python _system/scripts/sync_portfolio_from_registry.py
```

## Marvin checklist (automatic)

1. Scaffold folder (market template)
2. Register in `registry.json`
3. Run download (US/JP/EU/CA routing)
4. `build_folder_indexes.py` + `build_dashboard_data.py`
5. `_system/reviews/pending/{TICKER}_onboard_{date}.md`
6. Marvin deep dive via Cloud Agent (PR)

Do not write to MEMORY.md without [PROPOSED].
