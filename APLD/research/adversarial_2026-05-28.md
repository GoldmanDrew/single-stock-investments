---
filing: pass
consistency: partial
disclosure: pass
short: stale_hit
third_party: partial
block_final: false
blocking_issues: []
re_pass: false
---

# APLD — Adversarial review

**Date:** 2026-05-28  
**Agent:** Milly  
**Dive reviewed:** `APLD/research/deep_dive_2026-05-28.md`  
**Valuation reviewed:** `APLD/research/valuation.json`  
**Filings used:** `10-Q_20260408_rpt20260228_acc0001144879_26_000030.htm` (FQ3 FY2026, Feb 28, 2026)

**Goal:** Truth-seeking QA. Not bearish for its own sake.

---

## Summary verdict


| Area                  | Status          | One line                                                               |
| --------------------- | --------------- | ---------------------------------------------------------------------- |
| Filing reconciliation | **pass**        | Core Q3 revenue, NI, and equity match XBRL extract                     |
| Internal consistency  | **partial**     | Blended return wording differs slightly; bull 19.3% vs JSON bull 20.4% |
| Short activist scan   | **hit (stale)** | Jul 2023 Wolfpack / Bear Cave / Friendly Bear; dive addresses themes   |


**Overall:** Filing-consistent on primary metrics. **Refresh** empty holdco subsection headers in Business. **Do not** treat 2023 shorts as current without re-read.

---

## Filing reconciliation


| #   | Claim in dive                                          | Filing value                                                             | Match?        | Severity                            |
| --- | ------------------------------------------------------ | ------------------------------------------------------------------------ | ------------- | ----------------------------------- |
| 1   | FQ3 revenue **$126.6M**                                | `RevenueFromContractWithCustomerExcludingAssessedTax: 126,637` ($126.6M) | **Yes**       | —                                   |
| 2   | GAAP NI to common **$100.9M**                          | `NetIncomeLossAvailableToCommonStockholdersBasic: 100,861`               | **Yes**       | —                                   |
| 3   | Discontinued-op gain **~$59.7M** (Cloud held-for-sale) | Per 10-Q MD&A / disc ops (dive cites path)                               | **Plausible** | inference risk if not in XBRL line  |
| 4   | PF3 **$7.5B** base revenue                             | Press release May 20, 2026 (not in Feb 10-Q)                             | **N/A**       | filing-external PR; cited correctly |
| 5   | **1,200 MW** / **~$31B** contracted                    | Company disclosure May 2026                                              | **N/A**       | post-quarter PR                     |


---

## Internal consistency


| Check                     | Expected  | Found                     | OK?                                                  |
| ------------------------- | --------- | ------------------------- | ---------------------------------------------------- |
| Base IRR exec / blended   | **12.6%** | **12.6%**                 | Yes                                                  |
| `valuation.json` base_pct | **12.6**  | **12.6**                  | Yes                                                  |
| Bull IRR exec             | **19.3%** | valuation bull **20.4%**  | **No** — reconcile (likely different scenario label) |
| Blended section return    | **~13%**  | Returns at end **~11.5%** | **Partial** — blended paragraph vs valuation ledger  |
| Stance                    | **watch** | **watch**                 | Yes                                                  |


**Inference risk:** Approved external PDF (`apld_reiterate_buy`) not yet cross-checked line-by-line in dive (human approved 2026-05-28).

---

## Short activist scan


| Firm                  | Report? | Date         | Reconciliation                                                                                              |
| --------------------- | ------- | ------------ | ----------------------------------------------------------------------------------------------------------- |
| Muddy Waters          | No      | —            | —                                                                                                           |
| Hindenburg            | No      | —            | —                                                                                                           |
| **Wolfpack Research** | **Yes** | **Jul 2023** | Related-party / B. Riley / governance; dive cites capital structure and CoreWeave — **partially addressed** |
| **The Bear Cave**     | **Yes** | **Jul 2023** | Overlap with Wolfpack era                                                                                   |
| **The Friendly Bear** | **Yes** | **Jul 2023** | B. Riley control allegations                                                                                |


**Verdict:** Claims are **stale** (pre–AI lease pivot). Dive correctly stresses **secured debt subordinates equity** and **related-party** risk. Recommend one explicit sentence: “2023 forensic shorts preceded current hyperscaler lease book; re-read if new report published.”

**2026 note:** Capital Light (Mar 2026) flagged Base Electron / B. Riley linkage to APLD ecosystem — **not** in dive; **[HUMAN REVIEW]** if material to PF3 counterparty.

---

## Recommended actions

1. **Marvin:** Restore content under `#### Look-through snapshot` / `#### Catalyst path` (headers empty after v2 refresh).
2. **Marvin:** Align bull **19.3%** vs **20.4%** (exec vs `valuation.json`) or footnote scenario difference.
3. **Human:** Optional read of approved `apld_reiterate_buy` PDF vs PF3 PR numbers.

---

## [HUMAN REVIEW]

- Empty Business subsection headers (structural refresh bug)
- Base Electron / B. Riley press narrative (Mar 2026) not in dive