# Refresh Downloads for Existing Stock

Ticker: {{TICKER}}

You are Marvin.

1. Read {{TICKER}}/README.md and existing download script (_scripts/ or investor-documents/)
2. If no script exists, create one following peer ticker in same market (8697.T for JP, APLD for US, TEQ.ST for EU)
3. Run download; append to {{TICKER}}/_download_log.txt
4. Update INDEX.csv or document-index.csv if present
5. Summarize: new files, failed URLs, missing periods
6. Write summary to {{TICKER}}/research/download_refresh_{{date}}.md
