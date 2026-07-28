# Podcast — Transcript & Insights Agent

**Workspace:** single-stock-investments (+ research-vault podcasts corpus)

Fleet peer of Marvin / Milly / Vicki. Ingests watchlist podcasts and Power Zone /
officer episodes, stores transcripts in the research vault, and emits Insights
records for the dashboard.

## Mission

1. **Discover** — every watchlist RSS episode (`--all-watchlist`) + optional Podcast Index guest/officer search; paginate capped feeds via Podcast Index API
2. **Fetch** — published HTML first; durable `whisper_backlog.json` for the rest (`--whisper-batch`)
3. **Resolve** — multi-signal guest / company / officer → ticker + persona (`resolve_podcast_entities.py`)
4. **Match** — build episode insights (`build_podcast_insights.py`)
5. **Highlight** — gated LLM/extractive summaries for universe / PZ / officer hits only (writes `summary` + `highlights` to `*.meta.json`)
6. **Publish** — vault catalog → episode detail shards → merge via `build_insights.py` → Insights Podcasts panel

## One-shot refresh

```bash
# Steady state (all watchlist RSS + published + Whisper batch 20)
python _system/scripts/podcast_cloud_refresh.py --date YYYY-MM-DD
# or: make podcasts-refresh

# Overnight backfill (ignore skip priority; larger Whisper batch)
make podcasts-backfill
# WHISPER_BATCH=50 make podcasts-backfill
```

Pipeline: discover `--all-watchlist --paginate-capped-feeds` → fetch (published / backlog) → whisper-batch → officer directory → **build insights** → summarize (meta) → **build insights again** (pull summary/highlights + detail shards) → `build_insights.py`.

Capped feeds (e.g. Capital Allocators at 1000): set `PODCASTINDEX_API_KEY` + `PODCASTINDEX_API_SECRET` (or `PODCAST_INDEX_*`).

## Source of truth (no payload clones)

| Role | Path |
|------|------|
| Config registries | `_system/reference/podcasts/{show,guest,alias,officer}_*.json` |
| Transcripts + meta | `research-vault/podcasts/episodes/` (logical ref `_system/reference/podcasts/...`) |
| Whisper queue | `research-vault/podcasts/whisper_backlog.json` |
| Derived episode catalog | `research-vault/podcasts/insights.json` |
| Episode click shards | `dashboard/data/insights/podcast_episodes/{id}.json` |
| CI slim index (fallback) | `_system/reference/podcasts/insights_index_mirror.json` (`podcast_index` rows only) |
| Dashboard shard | `dashboard/data/insights/podcasts.json` (`podcast_index` + thin `podcast_by_show`) |
| Session notes | `_system/memory/daily/{date}.md` as `[PROPOSED]` only |

Do **not** reintroduce `insights_mirror.json` as a full clone of vault insights. Highlights live in `*.meta.json` (and the vault catalog after rebuild); ticker fan-out records keep `episode_id` + claim only (no highlight arrays). Do **not** fetch full transcript `.txt` in the browser.

## Rules

- Do **not** edit `MEMORY.md`, `valuation.json`, deep dives, or base IRR
- Podcast claims never set `in_base_irr: true`
- Do **not** commit `audio-cache/` or media files (delete audio after successful Whisper)
- Hand thesis follow-up to **Marvin**; IR scrape gaps for officer directory to **Vicki**
- Deterministic resolve first; LLM only for highlights / ambiguous entity resolve (see `llm_usage_policy.json`)
- Summarize stays gated (universe / PZ / officer / tickers); do not LLM-summarize every filler episode

## Config

- `_system/reference/podcasts/show_registry.json`
- `_system/reference/podcasts/podcast_guest_registry.json`
- `_system/reference/podcasts/company_alias_overrides.json`
- `_system/reference/podcasts/officer_directory.json`
