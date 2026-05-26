# Consensus Mining & Seigniorage Corp (CMSG)

**Ticker:** CMSG · **Market:** US · **Trading:** OTCQX  
**Corporate site:** https://consensusmining.com · **IR:** ir@consensusmining.com  

CMSG is **not SEC-registered** (no Edgar CIK). Primary disclosure is the **OTCQX Information and Disclosure Statement** (annual), plus audited financial exhibits, shareholder letters, and the annual proxy PDFs hosted on consensusmining.com.

## Folder map

| Path | Contents |
|------|----------|
| `investor-documents/otcmarkets/` | OTCQX annual disclosure PDF (FY2025) |
| `investor-documents/ir-consensusmining/` | Audited FY2024 PDF, quarterly shareholder letters, proxy |
| `research/` | Marvin analysis (`deep_dive_*.md`, `thesis.md`) |
| `_download_log.txt` | Download run history |

## Download

OTC Markets file URLs require a `Referer` from the issuer domain; the script handles that:

```bash
python3 CMSG/investor-documents/download_cmsg_investor_docs.py
```

Then regenerate indexes:

```bash
python3 _system/scripts/build_folder_indexes.py
python3 _system/scripts/sync_portfolio_from_registry.py
```

**Note:** `_system/scripts/download_us_investor_docs.py` cannot be used for CMSG (`us_ticker_config` has no CIK). Registry uses `download.type: us_dedicated` for this name.
