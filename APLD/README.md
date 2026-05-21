# Applied Digital (APLD) — Document Library

**Ticker:** APLD | **Exchange:** NASDAQ | **CIK:** 0001144879  
**Last updated:** 2026-05-21

Data center and digital infrastructure company focused on AI/cloud hosting, colocation, and HPC workloads.

---

## Folder Structure

```
APLD/
├── investor-documents/
│   ├── sec-edgar/              # 10-K, 10-Q, 8-K, DEF 14A from SEC EDGAR
│   ├── ir-applieddigital/      # IR site PDFs (presentations)
│   ├── research-notes/         # Third-party and internal notes
│   ├── download_apld_investor_docs.py
│   └── DOWNLOAD_MANIFEST.json
├── research/                   # Marvin analysis (agent-generated)
│   ├── thesis.md
│   └── reports/
└── README.md
```

---

## Primary Sources

| Source | URL |
|--------|-----|
| Investor Relations | https://ir.applieddigital.com/ |
| SEC EDGAR | https://www.sec.gov/cgi-bin/browse-edgar?CIK=1144879 |
| Presentations | https://ir.applieddigital.com/news-events/presentations |

---

## Download

Re-download or refresh the archive:

```powershell
cd APLD\investor-documents
python download_apld_investor_docs.py
```

Logs append to **`_download_log.txt`** at the APLD root when present.

---

## Notes

- Root-level duplicate PDF should live in `investor-documents/research-notes/` (third-party research, not primary source).
