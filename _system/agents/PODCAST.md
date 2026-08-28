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
6. **Analyse** — local-model claims, figures and thesis for episodes with real speech (`analyze_podcast_batch.py`, writes `llm_analysis` to `*.meta.json`)
7. **Publish** — vault catalog → episode detail shards → merge via `build_insights.py` → Insights Podcasts panel

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
| Local-model analysis | `llm_analysis` block inside each `*.meta.json` |
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
- A stage that writes must name its reader. `llm_analysis` was written by
  `analyze_podcast_batch.py` for eight episodes — 117 claims and 229 verified
  figures — while `build_podcast_insights.py` still read only `highlights` and
  `summary`, so none of it reached the dashboard and nothing said so. The
  producer is not done until the shard carries the field.
- The security master decides ticker attribution, and it decides by *equality*
  of names. A leading-word run ("Ford" for "Ford Motor Company") counts only
  when exactly one master row matches; anything ambiguous drops the symbol. The
  character-prefix version of that rule filed four Costco claims under CMRE, a
  Greek containership lessor, because the master stores Costamare before Costco.
  A missing ticker is recoverable; a wrong one is not.

## Analyse stage

```bash
# Coverage, no work
python _system/scripts/analyze_podcast_batch.py --status

# Run it. Yields to the Whisper backfill by default -- see --share-with-whisper.
python _system/scripts/analyze_podcast_batch.py --model qwen-gpu --hours 8
```

Needs a local model served on an OpenAI-compatible endpoint (`llm_local.py`);
there is no hosted LLM transport in this repo. Claims are verified against the
transcript in code, so a quote the model invented is dropped rather than
believed — but verification cannot catch a *real* quote filed under the wrong
company, which is why attribution goes through the security master.

Eligible episodes are those with genuine speech: ≥25 KB of text that is unique
to the episode after per-show boilerplate is removed. That is ~593 of the 3,750
catalogued, and the ceiling is the corpus, not the analyser.

**It shares one box with the Whisper backfill.** When both run, transcription
fell from ~3.0 to ~0.55 episodes/hour — a 5.5× collapse measured across the
checkpoints either side of `llama-server` starting on 2026-08-26. The analyser
now waits for the daemon to be idle by default.

## Config

- `_system/reference/podcasts/show_registry.json`
- `_system/reference/podcasts/podcast_guest_registry.json`
- `_system/reference/podcasts/company_alias_overrides.json`
- `_system/reference/podcasts/officer_directory.json`
