# Batch deep dive dispatch — 2026-06-03

## User request

Force `marvin-deep-dive` for all **22** onboard-pending tickers from batch 2026-06-03.

## Cloud agent attempt

`gh workflow run marvin-deep-dive.yml` failed for every ticker with **HTTP 403** (integration token cannot dispatch workflows). See failed list in git history of this file before PR merge.

## Automated fix (PR)

1. **`batch-marvin-deep-dive.yml`** — matrix job (default **3** parallel) runs `marvin_deep_dive.mjs` per ticker.
2. **`_system/data/deep_dive_dispatch_queue.json`** — queue with all 22 tickers; **push to `main` triggers** the batch workflow.
3. **`build_deep_dive_dispatch_matrix.py`** — resolves tickers from queue or onboard-pending.

## After merge

- Actions → **Marvin Deep Dive** should start automatically from the queue file push (batch mode).
- Or manually: `gh workflow run batch-marvin-deep-dive.yml -R GoldmanDrew/single-stock-investments`
- Per-ticker (admin PAT): `_system/scripts/batch_dispatch_deep_dives.sh`

## Tickers (22)

PSK.TO, ALS.TO, BUR, PCYO, SBR, RGLD, RPRX, MSTR, BKRB, GLXY, DMLP, MRSH, HKHC, TRC, OR, CME, CBOE, PBT, WPM, FNV, MIAX, HE

Each run opens a **separate PR**; merge after human review. Expect ~8 batches at 3 parallel (runtime hours).
