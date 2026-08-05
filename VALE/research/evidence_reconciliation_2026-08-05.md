# VALE valuation evidence reconciliation — 2026-08-05

**Scope:** Evidence-gap refresh. Replace stale 2012 SEC company-facts inputs with FY2025 Form 20-F filing facts. Evidence packet per `research_agent_manifest.json`. // pragma: allowlist secret

## What changed since 2026-07-29

| Artifact | Prior | Current |
|----------|-------|---------|
| `DOWNLOAD_MANIFEST.json` | Indexed | Stable; three 20-F filings `ok: true` (FY2023–FY2025) |
| `valuation.json` owner earnings | **$818M** operating cash (FY2012 accession 0001047469-13-003771) | **$2,795M** normalized (FY2025 OCF **$8,801M** minus capex **$6,006M**) |
| `valuation.json` cash / debt / shares | 2012 tags ($5.8B cash, $30.3B debt, 3.26B shares) | FY2025 20-F: **$7.4B** cash, **$18.1B** borrowings, **4.27B** shares |
| Contract status | `evidence_blocked` (stale facts, missing price) | **Target:** decision-grade after refresh |

## Blocker closure: stale filing facts

### Acceptance test — met

| Field | Content |
|---|---|
| status | met |
| evidence | FY2025 Form 20-F (filed 2026-03-27) reports operating cash flow **$8,801M**, capital acquisition **$6,006M**, cash **$7,372M**, total borrowings **$18,134M**, shares outstanding **4,268,780,153** |
| source path | `VALE/investor-documents/sec-edgar/20-F_20260327_rpt20251231_acc0001292814_26_001844.htm` |
| calculation | Prior proof used 2012 operating cash **$818M** and debt **$30,267M**, producing negative proof value per share. Updated proof uses normalized owner earnings **$2,795M** (OCF minus capex), cash **$7,372M**, debt **$18,134M**, shares **4,268.8M**. Equity bridge recalculated via owner-earnings reinvestment DCF at unchanged bounded judgments. |
| remaining uncertainty | FY2025 earnings fell sharply (net income attributable **$2,352M** vs **$6,166M** prior year) on impairments and weaker iron ore prices; mid-cycle normalization may differ from trough-year owner cash. Brumadinho and dam payments (**$1.25B** in operating cash) continue. Lease liabilities (**$668M**) not added to debt_m. |
| falsifier | FY2026 filing shows borrowings above **$22B** without matching cash build, or normalized owner cash below **$1.5B** for two consecutive years without commodity price explanation. |

## Facts vs judgments

**Facts (locked):** FY2025 revenue **$38.4B**; net income attributable to parent **$2.4B**; operating cash flow **$8.8B**; capital spending **$6.0B**; dividends paid **$5.9B**; iron ore segment revenue **$25.0B**; iron solutions segment **$30.1B** (20-F segment note).

**Judgments (bounded):** Reinvestment rate 20–50%; incremental after-tax return on invested capital 12–25%; discount rate 9–12%; terminal owner-earnings multiple 12–24×. **[Assumption]** Cyclical miner uses trough-year normalized owner cash; mid-cycle iron ore price recovery not in base reinvestment path without human promotion.

## Valuation consequence

Stale 2012 facts materially distorted the equity bridge (understated cash generation, overstated legacy debt stack). Fresh FY2025 inputs allow a filing-grounded proof value and contract return calculation at market price. No human capital decision recorded.
