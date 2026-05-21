# Onboard New Stock

Ticker: {{TICKER}}
Company: {{COMPANY_NAME}}
Market: {{US | JP | EU | OTHER}}
CIK (US only): {{CIK}}
IR URL: {{IR_URL}}

You are Marvin.

1. List existing ticker folders to confirm {{TICKER}} does not already exist
2. Create folder scaffold (use _system/templates/ matching market type)
3. Write {{TICKER}}/README.md with company name, exchange, IR links, folder map
4. Create download script:
   - US: Python script like APLD/investor-documents/download_apld_investor_docs.py (SEC User-Agent required)
   - JP: PowerShell like 8697.T/_scripts/download_and_organize.ps1 + _pdf_urls.txt
   - EU: Python or PowerShell targeting IR PDF list → document-index.csv
5. Run the download script; log results to {{TICKER}}/_download_log.txt
6. Update _system/portfolio/holdings.md with new row (thesis: TBD)
7. Write _system/reviews/pending/{{TICKER}}_onboard_{{date}}.md with download summary + gaps

Do not mark anything FINAL. Do not write to MEMORY.md without [PROPOSED].
