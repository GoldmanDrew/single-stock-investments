# Activist coverage — standing decisions

Decisions taken during the 2026-08-26 coverage work, recorded so they stop
resurfacing as open questions in later audits. Each says what was decided, why,
and what would change the answer.

---

## 1. Pre-XML unattributed rows are accepted, not chased

**Decision.** The ~479 feed rows from filings made before 2024-12-18 that still
resolve to `sec_filer:<slug>` rather than a registry firm are accepted as-is.
No further parser work is planned for them.

**Why.** Schedules 13D/G only became structured XML on 2024-12-18. Before that
the only machine-readable source is the rendered HTML cover page, whose layout
varies by filing agent. The parser fixes in PR #905 recovered what was
recoverable: HTML entities, the boilerplate-prefix and split-label artifacts,
and the trailing EIN. What remains are filings whose HTML genuinely does not
carry a clean name in a recoverable position.

Measured after the fixes, the residue is also mostly **not activism**: the
largest remaining names are founders and control persons (Charles Ergen, Joshua
Harris, Chip Wilson), strategic acquirers (Riot Platforms, General Electric,
Johnson & Johnson, Cisco) and PE/holdco vehicles (JAB BevCo, New Omaha
Holdings). The filer taxonomy classifies these correctly without needing their
names parsed any better than they already are.

**What would change it.** A cheap bulk source of historical reporting-person
names keyed by accession — if one appears, a one-off join is preferable to more
regex work.

---

## 2. Firm matching keeps a 120KB scan window

**Decision.** `FIRM_MATCH_TEXT_LIMIT` stays at 120,000 characters.

**Why.** Firm matching is the pipeline's dominant cost — one alternation over
325 registry terms across each filing. Shrinking the window was measured on a
random 250-filing sample:

| window | time | results that changed |
|---|---|---|
| 120,000 | 22.8s | baseline |
| 60,000 | 16.9s | 1 / 250 |
| 40,000 | 16.1s | 3 / 250 |
| 25,000 | 12.6s | 6 / 250 |

A 26% speedup for a 0.4% accuracy loss is a bad trade for a scan that runs once
a day over a handful of new filings. The window matters only for the one-off
full reindex, which can take the time.

**What would change it.** If the daily scan ever has to re-parse the whole
corpus routinely, revisit — and prefer a real multi-pattern matcher
(Aho-Corasick) over a smaller window, since that costs no accuracy at all.

---

## 3. High-volume forms are collected filer-side, not issuer-side

**Decision.** Form 3/4/5, 13F-HR and N-PX are pulled from the **filer's** EDGAR
submissions (`sec_filer_discovery.py`), never from the issuer's. 8-K is pulled
issuer-side but only for a ticker that already has a live campaign, capped per
ticker.

**Why.** An issuer's Form 4 stream is mostly ordinary executive compensation and
its 8-K stream is mostly unrelated corporate events; collecting either
unconditionally across 834 tickers would swamp the feed and the scan. Asking
instead what a *tracked activist* filed is precise, and costs one extra request
per firm rather than thousands per issuer.

**What would change it.** Nothing foreseeable — this is the natural shape of
the data. Note that it makes filer-CIK backfill load-bearing: a firm with no
`sec_cik` contributes no Form 4 coverage.

---

## 4. The publisher-site lane keeps three sources retired

**Decision.** `culper`, `blue_orca`, `carlyle` and `j_capital` are `manual`
rather than `site_index`, and `iceberg` is inactive.

**Why.** Verified live on 2026-08-26: the first three return HTTP 403 to any
non-browser client and a realistic browser User-Agent does not help — these are
WAF challenges that need JS execution. `jc-capital.com` fails TLS verification
even against the certifi bundle. `icebergresearch.com` is a parked HugeDomains
sales page; the firm's site is gone. Leaving `site_index` on produced roughly
225 logged failures a month and zero rows.

**What would change it.** A headless browser in the scan path would clear the
403s. That is a large dependency for four sources — worth it only if the same
capability is needed elsewhere.

---

## 5. EDINET is built but idle until a key exists

**Decision.** `edinet_activist_scan.py` is complete and tested, and reports
"not configured" until `EDINET_API_KEY` is set.

**Why.** EDINET API v2 requires a free subscription key
(https://api.edinet-fsa.go.jp/). Obtaining one is a human registration step.

**Note the trap.** An unauthenticated request returns **HTTP 200** with
`{"StatusCode": 401}` in the body. A caller checking `resp.status` sees success
and an empty result list, which is indistinguishable from "no filings today" —
the same dark-feed shape that let a Yahoo series go stale for 16 sessions. The
module reads the status out of the payload and raises; there is a test for it.

**What would change it.** Someone registering for a key and adding it to the
repository secrets. Until then Japan — the second-most-active activism market
in the world — has no coverage, and that is a known, recorded gap rather than
an assumed one.
