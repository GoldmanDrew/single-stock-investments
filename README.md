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

## Structure

- **Ticker folders** — official PDFs, indexes, download scripts
- **`_system/`** — memory, frameworks, prompts, reviews
- **`dashboard/`** — static portfolio UI
