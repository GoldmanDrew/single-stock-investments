# San Juan Basin Royalty Trust (SJT) — Document Library

**Ticker:** SJT | **Exchange:** NYSE | **CIK:** 0000319655  
**Last updated:** 2026-05-21

Passive royalty trust holding ~75% net-overriding royalty on San Juan Basin gas/oil properties (New Mexico). No operating business — distributions pass through from operator (historically Hilcorp; verify in latest 10-K).

---

## Folder Structure

```
SJT/
├── investor-documents/
│   ├── sec-edgar/              # SEC 10-K, 8-K, etc.
│   ├── ir-sjt/                 # Trustee / trust site PDFs (if any)
│   └── download_sjt_investor_docs.py
├── research/
│   ├── thesis.md
│   └── reports/
├── _download_log.txt
└── README.md
```

---

## Primary Sources

| Source | URL |
|--------|-----|
| SEC EDGAR | https://www.sec.gov/cgi-bin/browse-edgar?CIK=316596 |
| Trust information | https://www.sjbasin.com/ (verify current trustee links) |

---

## Download

```powershell
python SJT/investor-documents/download_sjt_investor_docs.py
```

**Last download:** 2026-05-22 — 48 primary SEC filings + 24 monthly distribution exhibits (EX-99.1 on 8-Ks). IR site returned 0 PDFs (trust is SEC-primary).

---

## Classification (Marvin)

| Field | Value |
|-------|-------|
| Archetype | optionality (depleting royalty stream) |
| Moat | n/a |
| Dhando | partial (commodity-linked cash yield) |
| Stance | watch |
