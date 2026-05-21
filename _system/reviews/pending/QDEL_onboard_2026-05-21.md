# QDEL Onboard — 2026-05-21

**Status:** Complete (Phase A+B)  
**Agent:** Marvin

---

## Summary

QuidelOrtho (QDEL, CIK 0001906324) has been onboarded to the US template.

| Item | Result |
|------|--------|
| README | Created |
| Download script | `investor-documents/download_qdel_investor_docs.py` |
| SEC filings | 42 downloaded (10-K, 10-Q, 8-K, DEF 14A, S-3ASR) |
| IR PDFs | 0 (IR site returned no static PDF links; 404 on news-events URL) |
| research/ | Created with `thesis.md` |
| Third-party PDF | Moved to `investor-documents/research-notes/` |
| Manifest | `DOWNLOAD_MANIFEST.json` |
| Log | `_download_log.txt` |

---

## Gaps

1. **IR PDFs** — QuidelOrtho IR pages appear to use dynamic loading or non-PDF formats. Vicki browser pass may be needed to map presentation/report URLs.
2. **Thesis** — Not yet drafted from primary 10-K.
3. **Price / market data** — Not in scope for this onboard.

---

## Thesis status

**unclear**

## [HUMAN REVIEW]
- Review latest 10-K (filed 2026-02-19) before drafting thesis
- Confirm whether IR PDF harvest needs Vicki interactive scrape

## [PROPOSED MEMORY]
- [PROPOSED] QDEL CIK is 0001906324; SEC archive complete through 2026-05-21
- [PROPOSED] QDEL IR PDFs require alternate harvest strategy (static scrape returned 0)

---

*Download executed 2026-05-21 per human confirmation.*
