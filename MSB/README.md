# Mesabi Trust (MSB)

**Ticker:** MSB · **NYSE** · **Market:** US  
**CIK:** `65172` · **Issuer type:** Passive statutory trust (iron ore pellet royalties)  
**Last updated:** 2026-05-25

Mesabi Trust receives royalties on pellets and related iron ore products produced or shipped by **Northshore Mining** (Silver Bay, Minnesota). **Cleveland-Cliffs Inc.** is the mine operator / reporter of quarterly royalty data. Marvin research lives under `research/`; official filings under `investor-documents/sec-edgar/`.

## Download

From repo root:

```powershell
python MSB/investor-documents/download_msb_investor_docs.py
```

Requires `_system/scripts/us_ticker_config.json` to list **`"cik": "65172"`** for SEC pulls.

## Folder map

| Path | Contents |
|------|----------|
| `investor-documents/sec-edgar/` | SEC Forms **10-K / 10-Q / 8-K** |
| `investor-documents/DOWNLOAD_MANIFEST.json` | JSON footprint of latest downloader run |
| `research/` | Marvin outputs (`deep_dive_*.md`, `thesis.md`, news JSON) |
| `INDEX.csv` | Auto-generated catalogue of inventoried `.htm/.pdf/.json` |
