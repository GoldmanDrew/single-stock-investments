# Japan Exchange Group (8697.T) ù Document Archive

Local archive of official investor-relations materials for **Japan Exchange Group, Inc.** (TSE: **8697**), sourced primarily from [JPX Investor Relations](https://www.jpx.co.jp/english/corporate/investor-relations/index.html).

**Last updated:** 2026-05-21  
**Total PDFs:** 399 files (389 source URLs on jpx.co.jp)

---

## Folder structure

| Folder | Contents |
|--------|----------|
| `01_Official/` | Annual securities reports, integrated reports (JPX Report), extraordinary reports |
| `02_Quarterly/` | Earnings releases and quarterly explanatory materials (FY2012ùFY2025) |
| `03_Events/` | Investor Day decks, earnings presentations, Q&A, transcripts |
| `04_Strategy/` | Medium-term management plans and IT master plans |
| `06_References/` | External sources (EDINET, market data links) ù not mirrored locally |

### `01_Official/`

- **`Annual_Securities_Reports/English/`** ù Full English annual securities reports (FY2021ùFY2024) and IFRS consolidated financial statements (2015ù2022)
- **`Annual_Securities_Reports/Japanese/`** ù Japanese ??????? archives (quarterly and annual, ~2012ù2025)
- **`Integrated_Reports/`** ù JPX Report / integrated reports 2013ù2025 (full editions)
- **`Integrated_Reports/2025_Sections/`** ù JPX Report 2025 by section
- **`Integrated_Reports/TSE_Group_Historical/`** ù Pre-merger TSE Group annual reports (1998ù2011)
- **`Extraordinary_Reports/`** ù Governance and compensation extraordinary reports

### `02_Quarterly/`

- **`Earnings_Releases/`** ù Quarterly earnings release PDFs (`E_ER_*`, `ER_JPX_*`)
- **`Explanatory_Materials/`** ù Slide decks and supplementary materials (`E_EM_*`, `EM_JPX_*`)
- **`TSE_Group_Archive/`** ù Historical TSE Group quarterly results (pre-JPX merger)

### `03_Events/`

- **`Investor_Day/`** ù Subsidiary and group presentations (TSE, OSE, JSCC, JPXI, etc.)
- **`Earnings_Presentations/`** ù Post-earnings presentation materials
- **`Q_and_A/`** ù FAQ and earnings-call Q&A documents
- **`Transcripts/`** ù English earnings call transcripts
- **`Other/`** ù Miscellaneous IR event materials

### `04_Strategy/`

- **`Mid_Term_Plans/`** ù 1st through 4th medium-term management plans, updates, and IT master plans (2013ù2027)

---

## Key documents (start here)

| Document | Location |
|----------|----------|
| Annual Securities Report FY2024 | `01_Official/Annual_Securities_Reports/English/Annual_Securities_Report_fy2024.pdf` |
| JPX Report 2025 (A4, screen) | `01_Official/Integrated_Reports/JPXReport2025_A4.pdf` |
| Medium-Term Management Plan 2027 | `04_Strategy/Mid_Term_Plans/mtmp_e_20260428.pdf` (latest update) |
| Q4 FY2025 Earnings Release | `02_Quarterly/Earnings_Releases/E_ER_JPX_Q4FY2025.pdf` |
| Q4 FY2025 Explanatory Material | `02_Quarterly/Explanatory_Materials/E_EM_JPX_Q4FY2025.pdf` |

---

## Maintenance

Re-download or refresh the archive:

```powershell
powershell -ExecutionPolicy Bypass -File "_scripts\download_and_organize.ps1"
powershell -ExecutionPolicy Bypass -File "_scripts\reorganize_existing.ps1"
```

- **`_pdf_urls.txt`** ù Canonical list of source PDF URLs  
- **`_download_log.txt`** ù Download run log  
- **`_scripts/`** ù Automation scripts (not investor-facing content)

## Research

Marvin analysis lives in **`research/`** (thesis, reports). Official PDFs stay in numbered folders above.

---

## External references (`06_References/`)

Sell-side equity research is generally paywalled and is **not** included here. Useful free/regulatory complements:

- **EDINET** (Japanese filings, XBRL): [Search 8697](https://disclosure2.edinet-fsa.go.jp/WEEE0040.aspx) ù EDINET code E03814
- **JPX IR Library**: https://www.jpx.co.jp/english/corporate/investor-relations/ir-library/index.html
- **TSE company page**: https://www.jpx.co.jp/english/listing/co-search/01.html?code=8697
- **IRBANK (EDINET mirror index)**: https://irbank.net/E03814/edinet

---

## Disclaimer

Documents are ù Japan Exchange Group, Inc. This archive is for personal research only. English translations on the JPX site are reference versions; the Japanese original prevails where they differ.
