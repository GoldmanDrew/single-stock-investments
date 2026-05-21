# Single Stock Investments

Personal single-stock research workspace with Marvin (research agent) infrastructure.

## Holdings

8697.T · 3905.T · APLD · QDEL · TEQ.ST · ICE · CSGP · SPGI · FRMO · OTCM · CPRT · BN · AMZN · GOOGL · KEWL · CSU · DHR · WBI

See [`_system/portfolio/holdings.md`](_system/portfolio/holdings.md).

## Dashboard

Static portfolio dashboard (etf-dashboard styling):

```powershell
python _system/scripts/build_dashboard_data.py
cd dashboard
python -m http.server 8765
```

Open http://localhost:8765/

## Agents

- [`_system/agents/MARVIN.md`](_system/agents/MARVIN.md) — research + downloads
- [`_system/agents/VICKI.md`](_system/agents/VICKI.md) — browser / IR harvest

## GitHub integration

| Repo | Visibility | Purpose |
|------|------------|---------|
| [single-stock-investments](https://github.com/GoldmanDrew/single-stock-investments) | Private | Full Marvin workspace (PDFs, research, memory) |
| [single-stock-dashboard](https://github.com/GoldmanDrew/single-stock-dashboard) | Public | Dashboard UI only (metrics JSON — no proprietary notes) |

### Workflows

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| [`daily-sync.yml`](.github/workflows/daily-sync.yml) | Daily 12:00 UTC + manual | Downloads → commit workspace → sync public dashboard |
| [`marvin-deep-dive.yml`](.github/workflows/marvin-deep-dive.yml) | Manual (ticker input) | Cursor Cloud Agent deep dive → opens PR for review |

### Secrets (Settings → Secrets → Actions)

| Secret | Required for | How to get |
|--------|--------------|------------|
| `DASHBOARD_SYNC_TOKEN` | Public dashboard sync | Fine-grained PAT with `contents: write` on `single-stock-dashboard` |
| `CURSOR_API_KEY` | Marvin deep dive in CI | [Cursor Cloud Agents dashboard](https://cursor.com/dashboard/cloud-agents) |

### Local publish

```powershell
powershell -ExecutionPolicy Bypass -File _system/scripts/publish_github.ps1
```

Rebuilds dashboard JSON, pushes private repo, syncs public Pages repo.

### Marvin session → GitHub

After local Marvin work:

```powershell
python _system/scripts/build_dashboard_data.py
git add -A
git commit -m "research: YOUR_MESSAGE"
git push origin main
```

Or run **Actions → Marvin Deep Dive** with a ticker; review and merge the PR the cloud agent opens.

## Structure

- **Ticker folders** — official PDFs, indexes, download scripts
- **`_system/`** — memory, frameworks, prompts, reviews
- **`dashboard/`** — static portfolio UI
