# Performance (long-term)

Four levers. Mark-to-market noise is not the score.

## Independence

- One primary cluster per name. Same cluster counts as correlated.
- Pairwise return correlation among open names: **1-year primary**. 60-day is a footnote on Drew only.
- Score = `1 - mean(|corr|)`, minus a penalty if one cluster is more than 40% of gross.
- Adding a name should show independence before vs after. Block only if average |corr| > 0.6 **and** same cluster.

Without price history the dashboard uses cluster co-membership (same cluster = 1, else 0).

## IRR

- Per-name money-weighted XIRR from cashflows (buys negative).
- Sleeve XIRR vs Drew's $100k starting capital, or Michael's residual NAV after first sync then cashflows.
- Thesis IRR from SSI valuation files is reference only. Do not mix Power Zone / Lawrence language into the sleeve returns statement.

## Permanent loss of capital

- Not drawdown. Max DD is a separate line.
- At entry: PLC 1–5 plus one sentence: what would make this a permanent loss.
- Realized PLC: thesis broken and exit below cost with no recovery path, or impairment.
- Suggested size shrinks as PLC rises, even at conviction 5.

## Conviction

- 1–5 at entry. Later changes are a new note, not a silent edit.
- Calibration: by bucket, count, average realized IRR, PLC rate, median years held.
- High conviction should mean better IRR and not more PLC, over years.

## Quarterly scorecard

- Completeness: percent of positions with a thesis note
- Independence (1y)
- Sleeve XIRR
- PLC events / capital at risk
- Conviction calibration gap
- Median holding period (Michael: warn if new adds are under 1 year)
