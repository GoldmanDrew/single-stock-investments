# Portfolio Dashboard — Plan & Deployment

**Date:** 2026-05-21  
**Agent:** Marvin  
**Status:** v1 built and running locally; GitHub Pages ready on push

---

## Goal

A static dashboard — styled like [etf-dashboard](file:///C:/Users/werdn/Documents/Investing/etf-dashboard) — that lists every ticker in the Single Stock Investments universe with key infrastructure metrics, completeness scores, and recent developments.

---

## Architecture (mirrors etf-dashboard)

```
Ticker folders + _system/portfolio/holdings.md
              │
              ▼
_system/scripts/build_dashboard_data.py
              │
              ▼
dashboard/data/dashboard_data.json
              │
              ▼
dashboard/index.html  (static SPA, DM Sans + JetBrains Mono, dark theme)
              │
              ▼
GitHub Pages (or local python -m http.server)
```

**No server in production.** Same pattern as etf-dashboard: build script → single JSON → React-free vanilla JS UI.

---

## v1 metrics (filesystem-based)

| Metric | Source |
|--------|--------|
| Ticker, company, market | `holdings.md` + folder scan |
| PDF count | Recursive `*.pdf` in ticker folder |
| SEC filing count | `investor-documents/sec-edgar/` |
| README / download script / index / research | Boolean checks |
| Last download | `_download_log.txt` |
| Last research | Newest file in `research/` |
| Thesis status | Parsed from `research/thesis.md` |
| Completeness score | Weighted infra score (0–100) |
| Recent developments | Latest 8-Ks from manifest, recent PDFs, Marvin reports |
| Recent files | 5 newest files by mtime |

---

## UI (etf-dashboard design tokens)

Reused from etf-dashboard:

- `--bg-primary: #0a0e17`, `--bg-card: #151d2e`, `--border: #1e2d46`
- DM Sans body, JetBrains Mono for numbers/tickers
- Summary strip, sortable table, detail panel
- Market badges (US/JP/SE), thesis status badges, completeness bars

**Live locally:** `http://localhost:8765/` (see below)

---

## Deployment

### Local (active now)

```powershell
cd "C:\Users\werdn\Documents\Investing\Single Stock Investments\dashboard"
python -m http.server 8765
```

Open: http://localhost:8765/

Rebuild data after folder changes:

```powershell
python _system/scripts/build_dashboard_data.py
```

### GitHub Pages (when repo is pushed)

1. Create GitHub repo (e.g. `single-stock-investments`)
2. Push workspace to `main`
3. Enable GitHub Pages → source: **GitHub Actions**
4. Workflow `.github/workflows/dashboard-deploy.yml` runs on push + daily cron
5. Site serves from `/` with `dashboard/index.html` + `dashboard/data/`

---

## Phase 2 roadmap (requires confirmation)

| Phase | Feature | Data source |
|-------|---------|-------------|
| 2a | Live prices, daily change | Polygon or Yahoo Finance API |
| 2b | Earnings calendar | SEC / IR scrape |
| 2c | Marvin research feed | Auto-index `research/reports/*.md` |
| 2d | Combined universe | Merge watchlist + ETF holdings if desired |
| 2e | Email / Slack alerts | New 8-K or download refresh |
| 2f | Per-ticker detail page | Deep link to folder README + latest 10-K summary |

### Combined universe note

Current universe = 5 ticker folders at workspace root. To include watchlist candidates or cross-portfolio ETFs, extend `build_dashboard_data.py` to read:

- `_system/watchlist/companies.md`
- Optional external CSV (e.g. etf-dashboard universe export)

---

## Files created

| Path | Purpose |
|------|---------|
| `dashboard/index.html` | Static UI |
| `dashboard/data/dashboard_data.json` | Generated metrics |
| `_system/scripts/build_dashboard_data.py` | Build script |
| `.github/workflows/dashboard-deploy.yml` | Pages deploy |

---

## [HUMAN REVIEW]

- Confirm GitHub repo name for Pages deploy
- Confirm Phase 2 priority (prices vs earnings vs research feed)
- Confirm whether IR PDF gap on QDEL should be first Vicki task

## Thesis status

**unclear** — dashboard is infra-only in v1.

---

*v1 deployed locally 2026-05-21. No API keys required.*
