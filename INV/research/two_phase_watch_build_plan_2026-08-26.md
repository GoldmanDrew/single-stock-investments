# Two-phase watch: build plan (INV dashboard)

**Date:** 2026-08-26
**Status:** implemented 2026-08-26. Weekly job: `.github/workflows/two-phase-watch.yml`.
**Does not set stance or base IRR.** Rank 1–3 hits go to review; they never auto-edit `valuation.json`.

Spec this implements: `INV/research/two_phase_cooling_watch.md`.
Competitive memo: `INV/research/competitive_analysis_two_phase_2026-08-26.md`.

---

## 1. What we are building

A **named-artifact monitor** for Accelsius / two-phase cooling, shown on the INV holding pane.

It answers three questions, in order:

1. Did NVIDIA or AMD make two-phase **required** on a named GPU generation?
2. Who got **designed in** (Accelsius vs Vertiv / Boyd / ZutaCore)?
3. Did an OEM or operator copy that into **production**?

It is not a news firehose and not a VIC Grok job.

**Non-goals**

- LinkedIn HTML scrape, login, or employee-feed crawl
- Unsupervised Grok summarizer of the live web
- Putting rank 5–6 (booths, papers) into base valuation
- A new Insights “Index Watch” clone
- Mixing Accelsius hits into the generic News pill

---

## 2. How it fits the existing machine

The dashboard is a static SPA (`dashboard/index.html`). INV is the right-hand detail pane at `#/research/coverage/INV`. Python builds JSON; Cloudflare Pages serves it.

```
Collectors (weekly + event days)
        |
        v
INV/research/evidence/two_phase_watch_ledger.json   (dedupe + ranks)
INV/research/evidence/two_phase_watch_YYYY-MM-DD.md (human note)
        |
        v
build_dashboard_data.py  ->  t.two_phase_watch
build_dashboard_shards.py -> dashboard/data/tickers/INV.json
        |
        v
Coverage detail pane: "Two-phase cooling watch" <details>
```

Reuse, do not replace:

| Existing piece | Use |
|----------------|-----|
| `download_us_investor_docs.py` | Already pulls NVDA, AMD, VRT, JCI, SMCI, DELL, HPE, INV 10-K/10-Q/8-K |
| `{TICKER}/research/evidence/_text/` | Keyword scan those extracts |
| `build_management_evidence.py` | Scan `{TICKER}/investor-documents/transcripts/` if present |
| `ingest_portfolio_news.py` | Add allowlisted Google News queries (Accelsius IR + LinkedIn-*origin* headlines, not a LinkedIn crawl) |
| Data Pipeline `news` cron (`30 */6`) | Keep as-is for INV ticker news |
| New job or Sunday World Model slot | Weekly watch compile |
| `marvin_cloud_refresh.py INV` | Optional: run watch compile before dashboard rebuild |

Do **not** widen `KEYWORD_LINES` in `build_filing_evidence.py` for all 834 tickers. Cooling terms on TPL or QDEL would pollute every filing digest. Keep a **watch-specific** regex in the new script.

---

## 3. Data contract

Canonical machine file: `INV/research/evidence/two_phase_watch_ledger.json`

```json
{
  "schema_version": 1,
  "ticker": "INV",
  "as_of": "2026-08-26",
  "highest_open_rank": 6,
  "status": "new_hits",
  "hits": [
    {
      "id": "sha1 of source_url+quote",
      "first_seen": "2026-08-26",
      "last_seen": "2026-08-26",
      "rank": 2,
      "source_kind": "filing|transcript|ir|event_pdf|news|linkedin_syndicated",
      "source_ticker": "NVDA",
      "title": "…",
      "quote": "<=280 chars",
      "source_url": "https://…",
      "local_path": "NVDA/investor-documents/…",
      "vendor_named": ["Accelsius", "Vertiv"],
      "falsifier": false
    }
  ]
}
```

Status values: `new_hits` | `no_material_hit` | `stale` (ledger older than 10 days).

Rank 1–3 also write a one-line row to `_system/reviews/pending/` so they show up in the human queue. Rank 4–6 stay on the INV pane only.

Human note remains `INV/research/evidence/two_phase_watch_YYYY-MM-DD.md` (even when the outcome is “no material hit”).

Dashboard field `t.two_phase_watch` is a **compact** copy: as_of, status, highest_open_rank, last 8 hits, count_by_rank. Add `two_phase_watch` to `DETAIL_ONLY_FIELDS` in `build_dashboard_shards.py` so it does not bloat `core.json`.

---

## 4. Collectors (phased)

### P0. Local keyword scan (no new network)

Script: `_system/scripts/two_phase_watch.py`

Inputs (read-only):

- Tickers: `NVDA`, `AMD`, `VRT`, `JCI`, `SMCI`, `DELL`, `HPE`, `INV`
- Paths: `*/research/evidence/_text/*.txt`, latest 10-K/10-Q/8-K HTML, `*/investor-documents/transcripts/**`, `*/research/evidence/management_digest_*.md`

Regex (case-insensitive):

```
two[- ]phase|pumped two[- ]phase|OMNICOOL|COOLERCHIPS|NeuCool|Accelsius|ZutaCore|Zuta.?Core|W45|W50|direct[- ]to[- ]chip|refrigerant.{0,40}cool
```

Vertiv extra: `MegaMod|\bCDU\b` only when co-occurring with two-phase / refrigerant / liquid cooling (avoid every coolant-distribution mention).

Output: ledger + dated markdown. First run backfills the known items already listed in the watch spec (Heydari, OMNICOOL, DarkNX removed booking, Series B).

This P0 is enough to light the dashboard panel.

### P1. Accelsius + Innventure IR (weekly)

Allowlisted GETs only:

- `https://accelsius.com/` news / press RSS or sitemap lastmod
- `https://ir.innventure.com/` and `https://www.innventure.com/news/`
- Accelsius BusinessWire / GlobeNewswire search for “Accelsius”

Store new PDFs/HTML under `INV/investor-documents/competitive/ir/`. Log 404s. Do not spider the whole marketing site.

Cadence: weekly, plus INV 8-K days (already covered by downloads).

### P2. Event PDF indexes (not whole-site crawls)

Fetch **index pages**, then download a PDF only if the URL is new and the title/snippet matches the regex.

| Source | When | How |
|--------|------|-----|
| ARPA-E COOLERCHIPS | Quarterly + if index hash changes | `arpa-e.energy.gov` program page |
| Hot Chips | August | `hotchips.org` tutorial list |
| NVIDIA GTC | March (and GTC DC if it returns) | session PDF links containing cooling / Heydari / Manaserh |
| OCP Global Summit | October | thermal / cooling track |
| AMD Instinct thermal guides | On docs version bump | AMD documentation index, not amd.com root |

Store under `INV/investor-documents/competitive/events/{source}/`. Cap: 20 new PDFs per run.

### P3. Filings freshness

Do not add a second EDGAR crawler. The existing holdings download already covers these tickers. The watch script only **scans** what is on disk. After NVDA/AMD/VRT earnings weeks, a `download_us_investor_docs.py --ticker NVDA` (etc.) already runs in the light/full download jobs. If a 10-Q is missing, the ledger records `coverage_gap`, it does not scrape EDGAR ad hoc during market hours for no reason. (IB Gateway rules are unrelated; SEC HTTPS is fine anytime.)

### P4. Transcripts

`INV` itself has almost no transcripts (`management_digest` was empty in July). NVDA/AMD/VRT/SMCI often do.

Plan:

1. If `{TICKER}/investor-documents/transcripts/` exists, scan it in P0.
2. If Polygon/Benzinga earnings transcripts are already wired for those tickers, add the cooling regex to that extract path rather than buying Seeking Alpha.
3. Do not start a new paid transcript vendor for this watch.

---

## 5. LinkedIn: do not scrape. Capture syndicated copies.

LinkedIn’s user agreement forbids scraping profiles, company feeds, or using non-official crawlers. There is no general-purpose “read any company page” API without being the page admin (Marketing / Community Management APIs). A standing employee-feed scrape would also be noisy and would violate the watch spec’s “no NVIDIA employee LinkedIn wholesale” rule.

**What we can do instead**

| Method | What it gets | Use |
|--------|--------------|-----|
| Google News RSS, query `Accelsius OR NeuCool OR "two-phase cooling" (NVIDIA OR Vertiv)` with publisher LinkedIn | Public posts that Google already indexed | Add as an extra query in `ingest_portfolio_news.py`, tagged `linkedin_syndicated`, rank 5–6 by default |
| Company IR that LinkedIn merely mirrors | Accelsius / Innventure / Vertiv press | P1 IR collector (canonical) |
| Named-person check via **Vicki** (browser agent), human-initiated | Heydari / Claman / Vertiv product posts after a GTC week | Write a one-page brief to `INV/research/shopbot/` when you actually want a look. Not a cron. |
| Official NVIDIA / AMD / Vertiv blogs and ARPA-E PDFs | The papers that matter | P2. This is where Heydari actually publishes. |

**Do not build:** LinkedIn login cookies in secrets, Sales Navigator export bots, profile HTML parsers, or a Playwright loop against `linkedin.com/in/…`.

If a syndicated LinkedIn item names Accelsius **and** a hyperscaler production MW, the ranker can promote it to rank 1, but the evidence still needs an IR/SEC/OEM URL before it is treated as a commercial fact.

---

## 6. Ranker (mechanical, then human)

Default rank from source + entities:

| Condition | Rank |
|-----------|------|
| Accelsius + named hyperscaler (AWS, Google, Microsoft, Meta, Oracle) + production/MW | 1 |
| NVIDIA or AMD + reference design / MGX / Instinct thermal guide + vendor name | 2 |
| SMCI / DELL / HPE + two-phase SKU + vendor name | 3 |
| Vertiv or Boyd two-phase GA, Accelsius not named | 4 (falsifier-leaning) |
| GTC / lab / Inception / HyperStart unnamed | 5 |
| Heydari / Manaserh / ARPA-E paper only | 6 |

Override: INV 8-K Accelsius contract / ownership / DarkNX booking change is rank 1 for **INV capital**, even if it is not an NVIDIA design win. The 19 Aug board letter (DarkNX booking removed) is that class of hit.

Never write rank 5–6 into `valuation.json`. Rank 1–3: pending review note only.

---

## 7. Cadence and CI

| Job | When | What |
|-----|------|------|
| P0+P1 compile | Weekly, Sunday UTC (after World Model, or a new `two_phase_watch` cron `0 17 * * 0`) | Scan disk + Accelsius IR + write ledger |
| Event bump | Manual / dispatch on GTC, Hot Chips, OCP, NVDA/AMD/VRT/INV earnings day | P2 PDF index |
| Dashboard | Nightly `intake-full` already rebuilds shards | `build_dashboard_data.py` reads ledger |
| News extras | Existing `30 */6` news job | New Google News queries only |

Keep the watch job **short** (minutes, not hours). No Playwright. No Gateway. CPU-light so NY4 coexistence is irrelevant (this runs on GitHub Actions, not NY4).

---

## 8. Dashboard: where it goes

**Primary surface:** Research → Coverage → INV detail pane (`#/research/coverage/INV`).

Insert a new `<details class="detail-section">` in `selectTicker()` in `dashboard/index.html` **after Company context and before Research memory / External context**.

Today the order is:

```
… Essential insights → KPI trend → Company context → Research memory → External context → …
```

around `dashboard/index.html` ~5597–5601 (`dossierSection` then `researchMemory` then `externalContext`).

**Why that slot**

- Company context is already industry structure and timeline. The watch is the Accelsius-specific continuation of that story.
- External context is a mixed Letters / Filings / News pill. A ranked ladder would disappear under News.
- Valuation workbench **Evidence** is gap-tracking for the contract, not a competitive monitor.
- Ideas → Watchlist is the onboard queue, not INV.
- Insights → Index Watch is the only UI named “watch” today, and it is the wrong domain.

**Secondary (optional, later):** a one-line chip on the sticky header when `highest_open_rank <= 3` and `as_of` is within 14 days: `Two-phase · rank 2 · 3d ago`. Clicking opens the section. Do not put a cooling widget on Portfolio or Insights overview.

**Do not** add INV to `holdings_themes.json` `ai_power_land`. That overlay is Permian / power / hyperscaler capex context and is explicitly not a base-IRR input. This watch is a **ticker evidence panel**, not a theme CSV.

### Panel UI (keep it small)

Summary line: `as_of` · status · highest rank.

Then a compact table, newest first:

| Rank | Date | Source | Hit | Vendor named |
|------|------|--------|-----|--------------|
| 4 | 2026-08-19 | INV 8-K | DarkNX booking removed; earnout forfeited | Accelsius |
| 6 | 2026-01 | ARPA-E | OMNICOOL: NVIDIA + Vertiv + Boyd | Vertiv, Boyd |

Empty / `no_material_hit`: one sentence, not a blank card. Link to `two_phase_cooling_watch.md` and the latest dated note.

Open by default only when rank ≤ 3. Otherwise collapsed, like Company context.

---

## 9. Implementation order (when you cut a branch)

1. Ledger schema + `two_phase_watch.py` P0 scan of local `_text/` for the eight tickers. Seed with known backfill. Tests: regex fixtures, dedupe, rank table.
2. `build_ticker_row()` reads the ledger → `t.two_phase_watch`. Shard field. Panel in `index.html`. Fixture INV.json in tests if dashboard tests exist.
3. P1 Accelsius/Innventure IR allowlist + weekly GHA job.
4. Google News extra queries (including LinkedIn-as-publisher). Tag `linkedin_syndicated`.
5. P2 event PDF indexes. Dispatch on GTC / Hot Chips / OCP.
6. Header chip for rank 1–3. Optional Insights ticker-drawer one-liner with “Open INV”.

Estimate: steps 1–2 are the dashboard-visible product. Steps 3–5 are the actual monitor. Step 6 is polish.

---

## 10. Falsifiers the panel must show in red

- Vertiv two-phase GA, Accelsius not named
- NVIDIA MGX / AMD Instinct guide names Boyd or Vertiv only
- INV Accelsius ownership below 25% without cash proceeds
- Another DarkNX-style booking reversal
- Parent SEPA / primary that jumps share count without Accelsius revenue

Those are rank 4 (or INV-capital rank 1) and stay on the pane even when there is no “good news.”
