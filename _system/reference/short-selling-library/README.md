# Short-selling research library

This directory separates **licensed/copyrighted books** from **publicly distributed research**. Do not commit unauthorized book scans. Books are catalogued for purchase, library access, or a user-supplied licensed copy; official public papers are stored under `public/` with their source URL.

## Core books — catalogue only

| Resource | Why it belongs in the process | Access |
|---|---|---|
| Kathryn F. Staley, *The Art of Short Selling* (1996) | Field cases, balance-sheet deterioration, accounting signals, and short thesis construction | ISBN 9780471146322 · purchase/library/authorized copy |
| Howard M. Schilit, Jeremy Perler, Yoni Engelhart, *Financial Shenanigans*, 4th ed. | Earnings quality, cash-flow manipulation, acquisition accounting, and KPI games | ISBN 9781260117264 · purchase/library/authorized copy |
| Thornton L. O'glove, *Quality of Earnings* | Receivables, inventories, capitalization, taxes, and reported-vs-economic earnings | ISBN 9780684863757 · purchase/library/authorized copy |
| Scott Fearon, *Dead Companies Walking* | Competitive decay, management denial, and catalyst discipline | ISBN 9781137279644 · purchase/library/authorized copy |
| Christine S. Richard, *Confidence Game* | Forensic credit work, regulatory claims, and the path/timing problem in a public short | ISBN 9781118010419 · purchase/library/authorized copy |
| Bethany McLean and Peter Elkind, *The Smartest Guys in the Room* | Related parties, incentives, off-balance-sheet structures, and narrative control | ISBN 9781591846604 · purchase/library/authorized copy |

When an authorized ebook/PDF is supplied, store it in the private research vault, not this operational repository, and add only a metadata pointer here.

## Public documents stored here

| Local file | Original source | Use |
|---|---|---|
| `public/sec_financial_reporting_manual_2026.pdf` | https://www.sec.gov/files/cf-frm.pdf | Filing and disclosure requirements; treat as non-authoritative staff guidance where the SEC says so. |
| `public/sec_short_sale_position_transaction_reporting_2014.pdf` | https://www.sec.gov/files/short-sale-position-and-transaction-reporting0.pdf | Market structure, short-position data, reporting limitations, and policy background. |
| `public/nber_w9466_efficiency_and_the_bear.pdf` | https://www.nber.org/system/files/working_papers/w9466/w9466.pdf | Short-sale constraints, market efficiency, volatility, and skew. |
| `public/nber_w20282_shorting_premium.pdf` | https://www.nber.org/papers/w20282.pdf | Borrow fees, anomaly interaction, and the shorting risk premium. |
| `public/nber_w16335_short_selling_market_quality.pdf` | https://www.nber.org/system/files/working_papers/w16335/w16335.pdf | Experimental evidence on lending supply, prices, and market quality. |

Public availability does not erase copyright. Preserve attribution and do not redistribute outside the terms of the source.

## Live official references

- SEC Regulation SHO overview: https://www.sec.gov/investor/pubs/regsho.htm
- SEC Accounting and Auditing Enforcement Releases: https://www.sec.gov/enforcement-litigation/accounting-auditing-enforcement-releases
- SEC Financial Reporting Manual (current web edition): https://www.sec.gov/about/divisions-offices/division-corporation-finance/financial-reporting-manual
- Investor.gov leveraged/inverse ETF bulletin: https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-alerts/sec
- AQR, “Price Efficiency and Short Selling”: https://www.aqr.com/Insights/Research/Journal-Article/Price-Efficiency-and-Short-Selling
- NBER, “Go Down Fighting: Short Sellers vs. Firms”: https://www.nber.org/papers/w10659

## Reading-to-workflow map

1. **Idea formation:** Staley/Fearon → define the market belief, variant view, catalyst, and falsifier.
2. **Accounting:** Schilit/O'glove + SEC FRM/AAER → reconcile revenue, working capital, capitalization, reserves, acquisitions, and non-GAAP claims.
3. **Tradability:** Regulation SHO + NBER/AQR → borrow, utilization, fee, recall, crowding, squeeze, and options alternatives.
4. **Instrument:** Investor.gov bulletin → daily reset, swaps, tracking, liquidity, and path dependence for ECHX-like products.
5. **Memory:** write a dated baseline and every later check-in to the Short Alpha ledger; never rewrite the original hypothesis after seeing the outcome.
