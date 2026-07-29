# Thematic indicator panels

Broadly-ingested macro / industry context that explains *why* holdings' optionality reprices. Consumed narrowly by tagged tickers only.

## Files

| Path | Contents |
|------|----------|
| `manifest.json` | Latest value, YoY, direction, staleness per series, grouped by theme |
| `{series_id}.csv` | Append-only history (`date,value`) per indicator |
| `filing_panels/*.csv` | Filing-derived time series (TPL water, AZLCZ leases, hyperscaler capex) |

## Pipeline (daily order)

```bash
python -m darwin.import_external_data          # from _system/scripts; sync etf-dashboard
python _system/scripts/extract_theme_facts.py
python _system/scripts/fetch_theme_panel.py
python _system/scripts/apply_context_overlay.py
python _system/scripts/fetch_ls_microstructure.py
python _system/scripts/fetch_peer_panel.py
```

- **Config:** `_system/scripts/theme_panel_config.json`
- **Tags:** `_system/portfolio/holdings_themes.json` (`"*"` expands to all registry holdings for `macro_regime`)
- **Sources:** FRED (rates, credit, gas, WTI), Yahoo daily (fallback when FRED/Stooq blocked), etf-dashboard CSV/JSON, EIA (Permian; needs `EIA_API_KEY`), repo `ai_overlay`, filing panels.

## etf-dashboard submodule

Live data: `_external/etf-dashboard` (see `.gitmodules`). Override path with `DARWIN_ETF_DASHBOARD_ROOT`. Synced snapshots also land in `_system/reference/market-data/external/` for offline CI.

## Rules

- **Context only.** Every indicator carries `in_base_irr: false`. Tailwinds may inform narrative and diligence; they never rewrite the universal valuation contract, Power Zone route, IC recommendation, or `human_decision.json`.
- Legacy Lawrence fields (`implied_return`, scenario growth) are **not** production authority — do not “promote into IRR” as if that were the house method. See `proof_first_valuation.md`.
- Any dual-agent promote that sets `in_base_irr: true` is a specialist/legacy annotation only; live capital remains human-gated. Residual gaps → **[OPEN DILIGENCE]** / **[Assumption]**.
- Offline-safe: on network failure, cached CSV history is kept; Yahoo proxies used for WTI/VIX/GLD when FRED times out.
- Deep dives: `#### Thematic context` in Business & moat (mechanical table + Marvin narrative preserved on refresh).

## Themes

| Theme | Chain | Tagged holdings |
|-------|-------|-----------------|
| `ai_power_land` | AI compute -> power -> grid/water -> land/hosting | TPL, LB, WBI, APLD, BWEL, **AZLCZ** |
| `macro_regime` | HY OAS, rates, dollar, VIX, credit impulse, expert horizons | All registry holdings (`*`) |
| `gold_royalties` | Gold spot, GDX, GDX/GLD ratio | RGLD, FNV, WPM, OR, MSB |
| `exchange_volatility` | Home-market vol (US VIX/SPY + regional realized); VRP + VIX term slope | CME, ICE, CBOE, MIAX, 8697.T, 0388.HK, ASX.AX |
| `water_surface` | TPL water panel + WTI + oil/gas activity | TPL, LB, WBI, BWEL, AZLCZ, GYRO, TRC, CDZI |
| `timber_housing` | Housing starts / permits + 10Y | ADN.TO, RYN, PCH, WY |
| `btc_hash_power` | BTC spot + power cost + hyperscaler pulse | CMSG, CLSK, BMNR, MSTR, IREN, HUT, APLD |
| `energy_royalty` | WTI / HH + oil-gas activity | SJT, DMLP, PBT, SBR, KRP, … |
| `pharma_royalty` | XLV / XBI sector tape + 10Y | RPRX, ABBV, LLY, VTRS |
| `nuclear_power` | URA + electricity + hyperscaler + AGI horizon | SMR, CEG, VST, DNN, AES, XEL |
| `index_data_fees` | VIX / realized vol + 10Y | SPGI, MCO, MSCI, FDS, OTCM |

See `_system/frameworks/optionality_valuation.md` § **Thematic context layer**.
