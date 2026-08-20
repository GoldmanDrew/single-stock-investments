# Third-party sources (approval workflow)

**Purpose:** Marvin may **blend** only human-approved external research into IRR and stance. Everything else is cited as **pending** until you approve.

**Approved today:** See `approved_substacks.md` (SSI, Lemon Cakes, Groundbreaker RE).  
**This file:** Proprietary letters, sell-side notes, fund letters, and other PDFs in ticker folders.

---

## Status levels

| Status | Marvin may use in IRR / stance? | Where to register |
|--------|----------------------------------|-------------------|
| **approved** | Yes — full blend per `external_view_blend.md` | Row in **Approved registry** below |
| **context** | No — cite for mental models / cross-check; not in base IRR | `{TICKER}/third-party-analyses/hk_scan_*.md` + `hk_ticker_index.json` |
| **pending** | No — cite in report, flag **[PENDING APPROVAL]** | `{TICKER}/third-party-analyses/pending.md` |
| **rejected** | No — do not cite | Note in pending file with date |

**Horizon Kinetics** quarterly commentaries and Stahl shelf essays default to **context** until human adds an approved row. Workflow: `hk_cross_reference.md`.

**Value Investors Club** intakes default to **pending**. Use `_system/agents/GROK.md` and `_system/scripts/drive_intake_drop.py`; `_system/frameworks/vic_local_intake.md` records the retired local-bookmarklet route. Do not automate VIC login, scheduled crawls, or bulk retrieval.

---

## Approved registry

| ID | Publisher | Tickers | Path | Approved |
|----|-----------|---------|------|----------|
| `ssi` | Special Situation Investing | FRMO, CMSG, KEWL, … | `approved_substacks.md` | 2026-05-26 |
| `lci` | Lemon Cakes Investing | FRMO, CMSG, … | `approved_substacks.md` | 2026-05-26 |
| `groundbreaker` | Groundbreaker RE (Substack) | BWEL, LB, TPL, WBI, **AZLCZ** | `approved_substacks.md` | **2026-06-02** (human: yes — water-rights lens; context tier for unverified acre-foot NAV until filings; **AZLCZ royalty ramp in base IRR 2026-06-05**) |
| `mcintyre` | McIntyre Partnerships | QDEL | `QDEL/investor-documents/research-notes/McIntyre_Partnerships_Q1_2026_Letter.pdf` | **2026-05-28** (human: yes — QDEL blend) |
| `apld_pf3_summary` | Applied Digital / Marvin shop summary (PF3 PR) | APLD | `APLD/investor-documents/research-notes/2026-05-20_Polaris_Forge_3_lease_summary.md` | **2026-05-28** (human: yes) |
| `apld_reiterate_buy` | Research note (run-the-table bull case) | APLD | `APLD/investor-documents/research-notes/What Would A Run The Table Scenario Look Like_ Reiterate BUY.pdf` | **2026-05-28** (human: yes — catalyst / bull framing; not sole IRR anchor) |
| `sohn_rosen_vtrs` | Sohn Conference Foundation / David Rosen (Rubric Capital) | VTRS | `VTRS/investor-documents/research-notes/2026-05-27_Sohn_Digging_Deeper_VTRS_excerpt.md` | **2026-06-02** (human: yes — Idorsia Phase III catalyst / deep-value framing; not sole IRR anchor) |
| `hk_context_teq` | HK extracts + inventory context (TEQ.ST) | TEQ.ST | `TEQ.ST/third-party-analyses/references.md` | **2026-06-02** (human: all context sources approved for synthesis blend) |
| `hk_context_tpl` | HK + SSI + LCI context (TPL) | TPL | `TPL/third-party-analyses/references.md` | **2026-06-02** (human: all context sources approved) |
| `hk_context_frmo` | HK + SSI + LCI context (FRMO) | FRMO | `FRMO/third-party-analyses/references.md` | **2026-06-02** (human: all context sources approved) |
| `hk_context_cmsg` | HK + SSI + LCI + IR PDFs (CMSG) | CMSG | `CMSG/third-party-analyses/references.md` | **2026-06-02** (human: all context sources approved) |
| `hk_context_msb` | HK + SSI context (MSB) | MSB | `MSB/third-party-analyses/references.md` | **2026-06-02** (human: all context sources approved) |
| `hk_context_ice` | HK context (ICE) | ICE | `ICE/third-party-analyses/references.md` | **2026-06-02** (human: all context sources approved) |
| `hk_context_sjt` | HK context (SJT) | SJT | `SJT/third-party-analyses/references.md` | **2026-06-02** (human: all context sources approved) |
| `hk_context_kewl` | HK + SSI context (KEWL) | KEWL | `KEWL/third-party-analyses/references.md` | **2026-06-02** (human: all context sources approved) |
| `semper_bkrb_2025` | Semper Augustus Investments Group | BKRB | `BKRB/investor-documents/research-notes/Semper_Augustus_2025_both-sides-now-berkshire-going-out-on-top.pdf` | **2026-06-18** (human: yes - Berkshire deep-dive / owner-earnings context) |
| `semper_bkrb_2024` | Semper Augustus Investments Group | BKRB | `BKRB/investor-documents/research-notes/Semper_Augustus_2024_wont-get-fooled-again-berkshire-getting-in-tune.pdf` | **2026-06-18** (human: yes - Berkshire deep-dive / insurance and capital allocation context) |
| `semper_bkrb_2023` | Semper Augustus Investments Group | BKRB | `BKRB/investor-documents/research-notes/Semper_Augustus_2023_dirty-deeds-done-dirt-cheap-berkshire-flag-half-staff.pdf` | **2026-06-18** (human: yes - Berkshire deep-dive / valuation context) |
| `semper_bkrb_2022` | Semper Augustus Investments Group | BKRB | `BKRB/investor-documents/research-notes/Semper_Augustus_2022_crazy-train-berkshire-getting-better-all-the-time.pdf` | **2026-06-18** (human: yes - Berkshire deep-dive / business quality context) |
| `semper_bkrb_2021` | Semper Augustus Investments Group | BKRB | `BKRB/investor-documents/research-notes/Semper_Augustus_2021_brown-sugar-berkshire-charlie-is-my-darling.pdf` | **2026-06-18** (human: yes - Berkshire deep-dive / long-horizon context) |
| `semper_bkrb_2020` | Semper Augustus Investments Group | BKRB | `BKRB/investor-documents/research-notes/Semper_Augustus_2020_point-of-no-return-berkshire-goat-goes-full-repo.pdf` | **2026-06-18** (human: yes - Berkshire deep-dive / repurchase context) |
| `semper_bkrb_2019` | Semper Augustus Investments Group | BKRB | `BKRB/investor-documents/research-notes/Semper_Augustus_2019_money-for-nothing-berkshire-fumblerooskie.pdf` | **2026-06-18** (human: yes - Berkshire deep-dive / capital allocation context) |
| `semper_bkrb_2018` | Semper Augustus Investments Group | BKRB | `BKRB/investor-documents/research-notes/Semper_Augustus_2018_addicted-to-loans-second-great-pivot-at-berkshire.pdf` | **2026-06-18** (human: yes - Berkshire deep-dive / operating and investment mix context) |
| `semper_bkrb_2017` | Semper Augustus Investments Group | BKRB | `BKRB/investor-documents/research-notes/Semper_Augustus_2017_double-double-berkshire-charmed-by-tax-deed.pdf` | **2026-06-18** (human: yes - Berkshire deep-dive / tax and valuation context) |
| `semper_bkrb_2016` | Semper Augustus Investments Group | BKRB | `BKRB/investor-documents/research-notes/Semper_Augustus_2016_sympathy-for-the-dog-brief-berkshire-redux.pdf` | **2026-06-18** (human: yes - Berkshire deep-dive / investment case context) |
| `semper_bkrb_2015` | Semper Augustus Investments Group | BKRB | `BKRB/investor-documents/research-notes/Semper_Augustus_2015_party-like-1999-deep-dive-into-berkshire-hathaway.pdf` | **2026-06-18** (human: yes - foundational Berkshire deep dive) |
| `apld_oasis_13d` | Oasis Management (SC 13D/A) | APLD | `APLD/third-party-analyses/activist_reports_index.json` | **2026-07-01** (human: yes — activist governance context; SEC filings in `activist_reports/long/`) |
| `apld_wolfpack_short` | Wolfpack Research short cache (Jul 2023) | APLD | `APLD/third-party-analyses/short_reports/wolfpack_2023-07.md` | **2026-07-01** (human: yes — stale forensic short; context only, not base IRR) |
| `verdad_biotech_2026` | Verdad Capital — Biotech Investing (Obenshain, Rasmussen, Wintner) | sector / biotech_quant | `_system/reference/biotech-quant/papers/verdad_biotech_investing_2026.pdf` | **2026-07-09** (context tier — specialist consensus, spend value, peer momentum; **not** base IRR; see `biotech-quant/SYNTHESIS.md`) |

---

## Approved market-data sources (context tier — not IRR)

| ID | Publisher | Use | Path / URL | Approved |
|----|-----------|-----|------------|----------|
| `finra_equity_si` | FINRA Equity Short Interest (biweekly) | Biotech quant short factor | `https://cdn.finra.org/equity/otcmarket/biweekly/shrtYYYYMMDD.csv` → `_system/reference/market-data/ownership/short_interest/` | **2026-07-09** (market data only; diversified short book; **not** base IRR) |
| `clinicaltrials_gov` | ClinicalTrials.gov API v2 | Peer / cohort similarity | `https://clinicaltrials.gov/api/v2/studies` → `ownership/biotech_clinical_profiles.json` | **2026-07-09** (context tier peer momentum; **not** base IRR) |
| `reddit_mentions` | Reddit (OAuth API) | Portfolio ticker mention volume / retail attention | `_system/reference/market-data/social/reddit_mentions_latest.json` (`make reddit-ingest`) | **2026-07-09** (context tier social scan; **not** base IRR) |
| `tracked_funds_13f` | SEC 13F (curated great funds) | Value-shop / mutual-fund ownership overlay | `_system/reference/market-data/ownership/tracked_funds/` (`make tracked-funds-13f-ingest`) | **2026-07-09** (ownership context; **not** base IRR unless a specific fund letter is human-approved) |

---

## Pending registry (human action required)

Marvin scans `{TICKER}/investor-documents/research-notes/` and flags new files here.

| Ticker | File | Type | Status |
|--------|------|------|--------|
| — | — | — | *(none)* |

**To approve:** Add a row to **Approved registry**, update `valuation.json` → `estimates.external[]`, re-run refresh.

---

## Per-ticker files

| File | Purpose |
|------|---------|
| `{TICKER}/third-party-analyses/references.md` | Index of approved + pending URLs/PDFs + HK scan |
| `{TICKER}/third-party-analyses/vic/*.md` | Local single-page VIC intakes; pending until human approval |
| `{TICKER}/third-party-analyses/hk_scan_{date}.md` | Auto HK / Stahl source map (`scan_hk_sources.py`) |
| `{TICKER}/third-party-analyses/pending.md` | Queue for human approval |
| `{TICKER}/research/cross_check_*` | Agreements / divergences / synthesis |

---

## Report language

- **Approved:** “McIntyre (approved third party) assumes …” / “Polaris bull note (approved) …”
- **Pending:** “(**[PENDING APPROVAL]** — not in IRR) …”
- Never fold pending sources into `valuation.json` base IRR without approval.

---

## Discovery on refresh

- `scan_third_party_sources.py` — **every universe ticker**: build `source_inventory_{date}.md` (approved, pending, Substacks, HK, research-notes, shorts).
- `scan_hk_sources.py` — HK-indexed tickers only (called via `--with-hk`).
- `scaffold_cross_check.py` / agent narrative — **required** `cross_check_third_party_{date}.md` or named cross-check per `third_party_cross_reference.md`.
- `check_cross_checks.py` — verify inventory + cross-check exist for registry holdings.
- `refresh_deep_dive_v2.py` — append new `research-notes/` PDFs to `pending.md`.
