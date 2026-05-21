# QuidelOrtho Corporation (QDEL) — Document Library

**Ticker:** QDEL | **Exchange:** NASDAQ | **CIK:** 0001906324  
**Last updated:** 2026-05-21

Diagnostics company formed by the 2022 merger of Quidel and Ortho Clinical Diagnostics.

---

## Folder Structure

```
QDEL/
├── investor-documents/
│   ├── sec-edgar/              # 10-K, 10-Q, 8-K, DEF 14A from SEC EDGAR
│   ├── ir-quidelortho/         # IR site PDFs (presentations, reports)
│   ├── research-notes/         # Third-party and internal notes
│   ├── download_qdel_investor_docs.py
│   └── DOWNLOAD_MANIFEST.json
├── research/                   # Marvin analysis (agent-generated)
│   ├── thesis.md
│   └── reports/
├── _download_log.txt
└── README.md
```

---

## Primary Sources

| Source | URL |
|--------|-----|
| Investor Relations | https://ir.quidelortho.com/home/default.aspx |
| SEC EDGAR | https://www.sec.gov/cgi-bin/browse-edgar?CIK=1906324 |
| Financials & Filings | https://ir.quidelortho.com/financials/default.aspx |

---

## Download

Re-download or refresh the archive:

```powershell
cd QDEL\investor-documents
python download_qdel_investor_docs.py
```

Uses **Q4 Investor Relations JSON feeds** for IR PDFs (145+ documents from q4cdn). SEC filings from EDGAR API.

Logs append to **`_download_log.txt`** at the QDEL root.

---

## Research Notes

- **`investor-documents/research-notes/McIntyre_Partnerships_Q1_2026_Letter.pdf`** — Third-party commentary (not primary source)
