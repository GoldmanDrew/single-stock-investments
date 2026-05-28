# Third-party sources (approval workflow)

**Purpose:** Marvin may **blend** only human-approved external research into IRR and stance. Everything else is cited as **pending** until you approve.

**Approved today:** See `approved_substacks.md` (SSI, Lemon Cakes).  
**This file:** Proprietary letters, sell-side notes, fund letters, and other PDFs in ticker folders.

---

## Status levels

| Status | Marvin may use in IRR / stance? | Where to register |
|--------|----------------------------------|-------------------|
| **approved** | Yes — full blend per `external_view_blend.md` | Row in **Approved registry** below |
| **pending** | No — cite in report, flag **[PENDING APPROVAL]** | `{TICKER}/third-party-analyses/pending.md` |
| **rejected** | No — do not cite | Note in pending file with date |

---

## Approved registry

| ID | Publisher | Tickers | Path | Approved |
|----|-----------|---------|------|----------|
| `ssi` | Special Situation Investing | FRMO, CMSG, KEWL, … | `approved_substacks.md` | 2026-05-26 |
| `lci` | Lemon Cakes Investing | FRMO, CMSG, … | `approved_substacks.md` | 2026-05-26 |
| `mcintyre` | McIntyre Partnerships | QDEL | `QDEL/investor-documents/research-notes/McIntyre_Partnerships_Q1_2026_Letter.pdf` | **2026-05-28** (human: yes — QDEL blend) |
| `apld_pf3_summary` | Applied Digital / Marvin shop summary (PF3 PR) | APLD | `APLD/investor-documents/research-notes/2026-05-20_Polaris_Forge_3_lease_summary.md` | **2026-05-28** (human: yes) |
| `apld_reiterate_buy` | Research note (run-the-table bull case) | APLD | `APLD/investor-documents/research-notes/What Would A Run The Table Scenario Look Like_ Reiterate BUY.pdf` | **2026-05-28** (human: yes — catalyst / bull framing; not sole IRR anchor) |

---

## Pending registry (human action required)

Marvin scans `{TICKER}/investor-documents/research-notes/` and flags new files here.

| Ticker | File | Type | Status |
|--------|------|------|--------|
| — | — | — | *(none)* |

**To approve:** Add a row to **Approved registry**, update `valuation.json` → `estimates.external[]`, re-run refresh.

---

## Per-ticker files

| File | Purpose |
|------|---------|
| `{TICKER}/third-party-analyses/references.md` | Index of approved + pending URLs/PDFs |
| `{TICKER}/third-party-analyses/pending.md` | Queue for human approval |
| `{TICKER}/research/cross_check_*` | Agreements / divergences / synthesis |

---

## Report language

- **Approved:** “McIntyre (approved third party) assumes …” / “Polaris bull note (approved) …”
- **Pending:** “(**[PENDING APPROVAL]** — not in IRR) …”
- Never fold pending sources into `valuation.json` base IRR without approval.

---

## Discovery on refresh

`refresh_deep_dive_v2.py` runs append new `research-notes/` PDFs to `{TICKER}/third-party-analyses/pending.md` when not in the approved registry.
