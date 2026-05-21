# QDEL IR harvest — shopbot notes

**Date:** 2026-05-21  
**Agent:** Vicki (browser + Q4 feed discovery)

## Finding

Static HTML scrape of `ir.quidelortho.com` returns **0** financial PDFs. PDF links are loaded via **Q4 Investor Relations JSON feeds**:

- `https://ir.quidelortho.com/feed/FinancialReport.svc/GetFinancialReportList?LanguageId=1&PageSize=-1`
- `https://ir.quidelortho.com/feed/Event.svc/GetEventList?LanguageId=1&PageSize=-1`

CDN base: `https://s201.q4cdn.com/442754795/files/`

## Result

**145 IR PDF URLs** discovered (annual reports, quarterly presentations, earnings scripts, conference decks).

Harvest script: `QDEL/investor-documents/_fetch_q4_feeds.py`  
URL list: `QDEL/investor-documents/_ir_pdf_urls.txt`  
Integrated into: `download_qdel_investor_docs.py`

## Browser observation

Financials page shows many "PDF (opens in new window)" links in accessibility tree; click intercepted by overlay on first attempt. Feed API approach is more reliable than DOM scraping.

## [HUMAN REVIEW]

- Privacy/terms PDFs included in harvest; filter if undesired
- CloudFront URLs (`d18rn0p25nwr6d.cloudfront.net/CIK-0001906324/...`) also present — verify download success
