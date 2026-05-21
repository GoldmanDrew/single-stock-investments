#!/usr/bin/env python3
"""Scaffold ticker folders for the single-stock workspace."""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TODAY = date.today().isoformat()

US_TICKERS = {
    "ICE": {
        "company": "Intercontinental Exchange",
        "exchange": "NYSE",
        "cik": "0001571949",
        "ir": "https://ir.theice.com/",
        "notes": "Global exchange and clearing operator (NYSE, ICE Futures, etc.).",
    },
    "CSGP": {
        "company": "CoStar Group",
        "exchange": "NASDAQ",
        "cik": "0001057352",
        "ir": "https://investors.costar.com/",
        "notes": "Commercial real estate information and marketplace.",
    },
    "SPGI": {
        "company": "S&P Global",
        "exchange": "NYSE",
        "cik": "0000064040",
        "ir": "https://investor.spglobal.com/",
        "notes": "Financial intelligence: ratings, indices, market data, Platts.",
    },
    "FRMO": {
        "company": "FRMO Corporation",
        "exchange": "OTC",
        "cik": "0001042017",
        "ir": "http://www.frmocorp.com/",
        "notes": "Investment company; Horizon Kinetics affiliate. Limited SEC filing history.",
    },
    "OTCM": {
        "company": "OTC Markets Group",
        "exchange": "OTCQX",
        "cik": None,
        "ir": "https://www.otcmarkets.com/about/company/investor-relations",
        "notes": "Operator of OTCQX/OTCQB/Pink markets. Primary docs via OTC Markets IR.",
    },
    "CPRT": {
        "company": "Copart",
        "exchange": "NASDAQ",
        "cik": "0000900075",
        "ir": "https://investor.copart.com/",
        "notes": "Online vehicle auction and remarketing.",
    },
    "BN": {
        "company": "Brookfield Corporation",
        "exchange": "NYSE",
        "cik": "0001001085",
        "ir": "https://bn.brookfield.com/",
        "notes": "Alternative asset manager and wealth platform.",
    },
    "AMZN": {
        "company": "Amazon.com",
        "exchange": "NASDAQ",
        "cik": "0001018724",
        "ir": "https://ir.aboutamazon.com/",
        "notes": "E-commerce, AWS cloud, advertising, logistics.",
    },
    "GOOGL": {
        "company": "Alphabet Inc.",
        "exchange": "NASDAQ",
        "cik": "0001652044",
        "ir": "https://abc.xyz/investor/",
        "notes": "Google Search, YouTube, Cloud, Other Bets.",
    },
    "KEWL": {
        "company": "Keweenaw Land Association",
        "exchange": "OTC Pink",
        "cik": None,
        "ir": "https://www.keweenawland.com/",
        "notes": "Mineral rights and land in Michigan/Wisconsin. OTC disclosure.",
    },
    "DHR": {
        "company": "Danaher Corporation",
        "exchange": "NYSE",
        "cik": "0000313616",
        "ir": "https://investors.danaher.com/",
        "notes": "Life sciences and diagnostics platform (Danaher Business System).",
    },
    "WBI": {
        "company": "WaterBridge Infrastructure",
        "exchange": "NYSE",
        "cik": "0002064947",
        "ir": "https://investors.waterbridgeinfrastructure.com/",
        "notes": "Produced-water infrastructure for E&P operators (Delaware Basin).",
    },
}

CA_TICKERS = {
    "CSU": {
        "company": "Constellation Software",
        "exchange": "TSX",
        "ir": "https://www.csisoftware.com/about-us/investor-relations",
        "notes": "Canadian serial acquirer of vertical market software (VMS).",
    },
}


def thesis_md(ticker: str, company: str) -> str:
    return f"""# {ticker} — Investment Thesis

**Status:** unclear  
**Last updated:** {TODAY}

## One-line thesis
TBD — pending primary doc review.

## Key questions
- [ ] Core business model and revenue drivers
- [ ] Competitive moat and capital allocation
- [ ] Valuation vs history and peers
- [ ] Key risks from latest annual / quarterly filings

## [HUMAN REVIEW]
- Thesis not yet drafted from primary sources.
"""


def us_readme(ticker: str, meta: dict) -> str:
    cik_line = f"**CIK:** {meta['cik']}" if meta.get("cik") else "**CIK:** — (OTC / non-SEC filer)"
    sec_line = (
        f"https://www.sec.gov/cgi-bin/browse-edgar?CIK={meta['cik'].lstrip('0')}"
        if meta.get("cik")
        else "—"
    )
    return f"""# {meta['company']} ({ticker}) — Document Library

**Ticker:** {ticker} | **Exchange:** {meta['exchange']} | {cik_line}  
**Last updated:** {TODAY}

{meta['notes']}

---

## Folder Structure

```
{ticker}/
├── investor-documents/
│   ├── sec-edgar/              # SEC filings (if applicable)
│   ├── ir-{ticker.lower()}/    # IR site PDFs
│   ├── research-notes/         # Third-party notes
│   └── download_{ticker.lower()}_investor_docs.py  # (to be created)
├── research/
│   ├── thesis.md
│   └── reports/
└── README.md
```

---

## Primary Sources

| Source | URL |
|--------|-----|
| Investor Relations | {meta['ir']} |
| SEC EDGAR | {sec_line} |

---

## Download

Download script not yet created. Use `_system/prompts/onboard-new-stock.md` or peer template `APLD/`.

Logs go to **`_download_log.txt`** when download runs.
"""


def ca_readme(ticker: str, meta: dict) -> str:
    return f"""# {meta['company']} ({ticker}) — Document Library

**Ticker:** {ticker} | **Exchange:** {meta['exchange']}  
**Last updated:** {TODAY}

{meta['notes']}

---

## Folder Structure

```
{ticker}/
├── official-reports/
├── corporate-documents/
├── presentations-and-media/
├── document-index.csv
├── research/
│   ├── thesis.md
│   └── reports/
└── README.md
```

---

## Primary Sources

| Source | URL |
|--------|-----|
| Investor Relations | {meta['ir']} |
| SEDAR+ | https://www.sedarplus.ca/ |

---

## Download

Download script not yet created. Adapt `TEQ.ST/` or `_system/templates/ticker-scaffold/`.
"""


def scaffold_us(ticker: str, meta: dict) -> None:
    base = ROOT / ticker
    dirs = [
        base / "investor-documents" / "sec-edgar",
        base / "investor-documents" / f"ir-{ticker.lower()}",
        base / "investor-documents" / "research-notes",
        base / "research" / "reports",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    (base / "README.md").write_text(us_readme(ticker, meta), encoding="utf-8")
    (base / "research" / "thesis.md").write_text(thesis_md(ticker, meta["company"]), encoding="utf-8")


def scaffold_ca(ticker: str, meta: dict) -> None:
    base = ROOT / ticker
    dirs = [
        base / "official-reports",
        base / "corporate-documents",
        base / "presentations-and-media",
        base / "research" / "reports",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    idx = base / "document-index.csv"
    if not idx.exists():
        with idx.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["path", "title", "date", "source_url", "type"])
    (base / "README.md").write_text(ca_readme(ticker, meta), encoding="utf-8")
    (base / "research" / "thesis.md").write_text(thesis_md(ticker, meta["company"]), encoding="utf-8")


def main() -> None:
    created = []
    for ticker, meta in US_TICKERS.items():
        if (ROOT / ticker).exists():
            print(f"SKIP {ticker} (exists)")
            continue
        scaffold_us(ticker, meta)
        created.append(ticker)
        print(f"OK {ticker}")
    for ticker, meta in CA_TICKERS.items():
        if (ROOT / ticker).exists():
            print(f"SKIP {ticker} (exists)")
            continue
        scaffold_ca(ticker, meta)
        created.append(ticker)
        print(f"OK {ticker}")
    print(f"Created {len(created)}: {', '.join(created)}")


if __name__ == "__main__":
    main()
