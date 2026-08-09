# Batch onboard — 2026-06-03

**Manifest:** `_system/portfolio/onboard_batch_2026-06-03.json`  
**Runner:** `python3 _system/scripts/batch_onboard_tickers.py`  
**Result:** EXIT 0 — 22 new holdings (51 total in registry/dashboard)

## Tickers onboarded

| Ticker | Company | Market | Download |
|--------|---------|--------|----------|
| HE | Hawaiian Electric Industries | US | SEC + IR |
| MIAX | Miami International Holdings | US | SEC + IR |
| FNV | Franco-Nevada Corporation | US | SEC + IR |
| WPM | Wheaton Precious Metals | US | SEC + IR |
| PBT | Permian Basin Royalty Trust | US | SEC + IR (8-K exhibits) |
| CBOE | Cboe Global Markets | US | SEC + IR |
| CME | CME Group | US | SEC + IR |
| OR | Osisko Gold Royalties | US | SEC + IR |
| TRC | Tejon Ranch | US | SEC + IR |
| HKHC | Horizon Kinetics Holding | US | SEC + IR |
| MRSH | Marsh & McLennan | US | SEC + IR |
| DMLP | Dorchester Minerals | US | SEC + IR |
| GLXY | Galaxy Digital | US | SEC + IR |
| BKRB | Berkshire Hathaway (Class B) | US | SEC (CIK 1067983) |
| MSTR | MicroStrategy | US | SEC + IR |
| RPRX | Royalty Pharma | US | SEC + IR |
| RGLD | Royal Gold | US | SEC + IR |
| SBR | Sabine Royalty Trust | US | SEC + IR (8-K exhibits) |
| PCYO | Pure Cycle | US | SEC + IR |
| BUR | Burford Capital | US | SEC + IR |
| ALS.TO | Altius Minerals | CA | IR scrape only (no SEC) |
| PSK.TO | PrairieSky Royalty | CA | IR scrape only (no SEC) |

**Skipped:** **BN** (already in portfolio).

## Analyses (not auto-complete)

Onboard pipeline delivered per ticker:

- `research/thesis.md` (classification scaffold)
- `research/cross_check_third_party_2026-06-03.md` (scaffold)
- `third-party-analyses/source_inventory_2026-06-03.md`
- `{TICKER}/_onboard_status.json` with `deep_dive_pending: true`

**Deep dives** are **not** written in batch mode (`--no-deep-dive`). Queue:

```bash
# One ticker at a time (GitHub Actions)
gh workflow run marvin-deep-dive.yml -f ticker=HE

# Or local mechanical pass after narrative exists:
python _system/scripts/marvin_cloud_refresh.py HE --date 2026-06-03
```

Daily `marvin-refresh` job prioritizes `onboard_pending` holdings.

## [HUMAN REVIEW]

- **BKRB:** User symbol **BKRB**; SEC entity **BRK-B**, CIK **1067983**.
- **MRSH:** NYSE symbol change from **MMC** (Jan 2026); EDGAR may still show MMC in older accession names.
- **ALS.TO / PSK.TO:** Add SEDAR+ PDFs or Vicki scrape if IR harvest is thin (`research/shopbot/`).

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] Batch onboard 2026-06-03: 22 names added for croupier/royalty/platform research funnel.
