# Ticker Scaffold Templates

Reference layouts when onboarding new holdings. Copy and adapt per market.

## US (see APLD/)

```
{TICKER}/
├── README.md
├── investor-documents/
│   ├── sec-edgar/
│   ├── ir-{company}/
│   ├── research-notes/
│   ├── download_{ticker}_investor_docs.py
│   └── DOWNLOAD_MANIFEST.json
├── research/
│   ├── thesis.md
│   └── reports/
└── _download_log.txt
```

## Japan (see 8697.T/)

```
{TICKER}/
├── README.md
├── INDEX.csv
├── 01_Official/
├── 02_Quarterly/
├── 03_Events/
├── 04_Strategy/
├── 06_References/
├── _scripts/download_and_organize.ps1
├── _pdf_urls.txt
├── research/
└── _download_log.txt
```

## Europe / Sweden (see TEQ.ST/)

```
{TICKER}/
├── README.md
├── document-index.csv
├── official-reports/
├── corporate-documents/
├── presentations-and-media/
├── third-party-analyses/
├── research/
└── _download_log.txt
```

Always add `research/` for Marvin outputs — never overwrite official PDF folders.
