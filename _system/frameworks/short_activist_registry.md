# Short activist / forensic research registry

**Purpose:** Milly (adversarial reviewer) scans these publishers for reports on **portfolio tickers**. Not every name has coverage on every holding.

**Use:** Cross-reference only. A short report is **evidence to reconcile**, not a veto. Goal = **truth**, not bearishness for its own sake.

---

## Tier 1 — Forensic short specialists (priority scan)

| Firm | Typical style | Search hints |
|------|---------------|--------------|
| **Muddy Waters Research** | Accounting fraud, VIEs, related parties | `site:muddywatersresearch.com {TICKER}` |
| **Hindenburg Research** | Fraud, promoters, SPACs, governance | `site:hindenburgresearch.com {company}` |
| **Citron Research** | (mostly inactive post-2021) historical | archive / web search |
| **Kerrisdale Capital** | Long/short letters, accounting | `Kerrisdale {company} report` |
| **Spruce Point Capital** | Forensic accounting, consumer/industrial | `Spruce Point {company}` |
| **Iceberg Research** | Fraud, China, complex structures | `Iceberg Research {company}` |
| **Gotham City Research** | European/ADR fraud | `Gotham City {company}` |
| **Bonitas Research** | China ADRs, fraud | `Bonitas {company}` |
| **Blue Orca Capital** | Asia-Pacific forensic | `Blue Orca {company}` |
| **Wolfpack Research** | Fraud, China | `Wolfpack {company}` |
| **Viceroy Research** | Governance, fraud (global) | `Viceroy {company}` |
| **Grizzly Research** | China / ADR | `Grizzly Research {company}` |
| **Bleeker Street** | Short thesis letters | `Bleeker Street {company}` |
| **Fuzzy Panda Research** | Smaller-cap fraud | web search |
| **Bucephalus Research** | Accounting (often Asia) | web search |

---

## Tier 2 — Activist shorts / hedge letters (secondary)

| Firm | Notes |
|------|--------|
| **Scorpion Capital** | SPACs, fraud |
| **Anathema Research** | Smaller forensic |
| **Night Market** | Short letters |
| **White Diamond Research** | |
| **Unemon Research** | |
| **BMF Reports** | |
| **J Capital Research** | Often China |

---

## Non-short bears (Milly disclosure scan)

| Type | Search hints | Verdict in adversarial |
|------|--------------|------------------------|
| **SEC securities litigation** | `{company} class action 10b-5` | `litigation` — not auto-bear |
| **Late filing (OTC)** | `NT 10-K` `Notification of Late Filing` | `disclosure: hit` |
| **Restatement / non-reliance** | `should no longer be relied upon` Item 4.02 | `disclosure: hit` |
| **Auditor change** | `8-K` auditor resignation | `needs_human` |

---

## Portfolio universe (21 holdings)

`3905.T` `8697.T` `AMZN` `APLD` `BN` `CMSG` `CPRT` `CSGP` `CSU` `DHR` `FRMO` `GOOGL` `ICE` `KEWL` `MSB` `OTCM` `QDEL` `SJT` `SPGI` `TEQ.ST` `WBI`

Milly logs **hit / no hit / unclear** per ticker per refresh.

---

## Reconciliation rules (Milly)

1. **If short report exists:** Summarize **falsifiable claims** (numbers, accounting, legal).
2. **Check each claim** against latest 10-K/10-Q or local equivalent in `{TICKER}/investor-documents/`.
3. **Map to Marvin dive:** Did the deep dive address it? If not → **gap** (not auto-downgrade).
4. **Verdict types:** `refuted_by_filing` | `partially_valid` | `unaddressed` | `stale` | `needs_human`
5. **Do not** change stance or IRR without human review unless **factual error** in Marvin numbers (lint-level).

---

## Maintenance

- Add new firms when human discovers quality forensic work.
- Mark **inactive** firms; keep for historical tickers.
- Store found reports in `{TICKER}/third-party-analyses/short_reports/` with `source`, `date`, `url`, `summary.md`.
