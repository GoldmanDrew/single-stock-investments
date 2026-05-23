# Single Stock Investments

Personal single-stock research workspace with Marvin (research agent) infrastructure.

## Holdings

8697.T · 3905.T · APLD · QDEL · TEQ.ST · ICE · CSGP · SPGI · FRMO · OTCM · CPRT · BN · AMZN · GOOGL · KEWL · CSU · DHR · WBI

See [`_system/portfolio/holdings.md`](_system/portfolio/holdings.md).

## Dashboard

Static portfolio dashboard (etf-dashboard styling) in [`dashboard/`](dashboard/).

**Local preview:**

```powershell
python _system/scripts/build_dashboard_data.py
cd dashboard
python -m http.server 8765
```

Open http://localhost:8765/

**Live site (GitHub Pages, same repo):**

https://goldmandrew.github.io/single-stock-investments/

## Agents

- [`_system/agents/MARVIN.md`](_system/agents/MARVIN.md) — research + downloads
- [`_system/agents/VICKI.md`](_system/agents/VICKI.md) — browser / IR harvest

## GitHub integration

| Item | URL |
|------|-----|
| **Repository** | [github.com/GoldmanDrew/single-stock-investments](https://github.com/GoldmanDrew/single-stock-investments) (public) |
| **Dashboard (Pages)** | [goldmandrew.github.io/single-stock-investments](https://goldmandrew.github.io/single-stock-investments/) |

Everything lives in one repo: Marvin workspace + `dashboard/` for Pages. **No PAT required** for dashboard sync.

### One-time Pages setup

1. **Settings → General → Change repository visibility → Public**
2. **Settings → Pages → Build and deployment → Source: GitHub Actions**
3. Run **Actions → Deploy Dashboard (GitHub Pages) → Run workflow**

You can delete the old `DASHBOARD_SYNC_TOKEN` secret and archive `single-stock-dashboard` if no longer needed.

### Workflows

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| [`daily-sync.yml`](.github/workflows/daily-sync.yml) | Daily 12:00 UTC + manual | Download holdings → commit → **auto Marvin refresh** if new docs |
| [`dashboard-pages.yml`](.github/workflows/dashboard-pages.yml) | Push to `main` (dashboard paths) + manual | Rebuild JSON → deploy `dashboard/` to GitHub Pages |
| [`marvin-deep-dive.yml`](.github/workflows/marvin-deep-dive.yml) | Manual (ticker input) | Cursor Cloud Agent deep dive → opens PR |
| [`marvin-daily-deep-dive.yml`](.github/workflows/marvin-daily-deep-dive.yml) | Manual only | Pick on new documents (or **force_rotate**) → cloud agent → PR |

Push to `main` after downloads or research triggers a Pages deploy automatically when dashboard-related paths change.

**Daily analysis loop:** `daily-sync` (12:00 UTC) downloads new SEC/IR files → on success, `marvin-daily-deep-dive` runs → picks tickers whose primary documents are **newer than their latest deep dive** → opens a Cursor PR. If nothing new, the deep dive workflow **skips** (use manual run + **force_rotate** to refresh the oldest dive anyway).

### Secrets (Settings → Secrets → Actions)

| Secret | Required for | How to get |
|--------|--------------|------------|
| `CURSOR_API_KEY` | Marvin deep dive in CI (manual + **daily auto**) | [Cursor Dashboard → Integrations](https://cursor.com/dashboard/integrations) |

### Local publish

```powershell
powershell -ExecutionPolicy Bypass -File _system/scripts/publish_github.ps1
```

Rebuilds dashboard JSON and pushes to `main`. Pages deploy runs via GitHub Actions (no second repo).

### Marvin session → GitHub

After local Marvin work:

```powershell
python _system/scripts/build_dashboard_data.py
git add -A
git commit -m "research: YOUR_MESSAGE"
git push origin main
```

Or run **Actions → Marvin Deep Dive** with a ticker; review and merge the PR the cloud agent opens.

### Public repo note

Making this repo public exposes ticker PDFs, research notes, and `_system/memory/MEMORY.md`. Review contents before switching visibility.

## Structure

- **Ticker folders** — official PDFs, indexes, download scripts
- **`_system/`** — memory, frameworks, prompts, reviews
- **`dashboard/`** — static portfolio UI
