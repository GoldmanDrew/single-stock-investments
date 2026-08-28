# Two-phase cooling watch: NVIDIA / AMD / Vertiv to Accelsius

**For:** INV (Innventure) / Accelsius NeuCool
**Created:** 2026-08-26
**Does not set stance or base return.** Hits land in `INV/research/evidence/two_phase_watch_YYYY-MM-DD.md`.

Do **not** use the VIC Grok agent (`_system/agents/GROK.md`) for this. That persona files Value Investors Club PDFs to Drive. It is the wrong tool.

---

## What we are trying to learn

NVIDIA and AMD will not show up as Accelsius customers on an income statement. They show up as **specifiers**. The watch is for: (1) two-phase becoming required on a named GPU generation, (2) who gets designed in (Accelsius vs Vertiv/Boyd/ZutaCore), (3) whether a hyperscaler or OEM copies that design into production.

A Grok/X scrape of "NVIDIA two-phase" will mostly return the same Heydari slides and Inception booth noise. Design the watch around **named artifacts**, not keyword volume.

---

## Signal ladder (only promote on higher rungs)

| Rank | Signal | Example | INV implication |
|------|--------|---------|-----------------|
| 1 | Named production MW | AWS/Google/MSFT/Meta + Accelsius | Thesis-changing |
| 2 | Chip-maker reference design that names a vendor | NVIDIA MGX or AMD Instinct thermal guide lists NeuCool or Vertiv two-phase | High |
| 3 | OEM SKU | Super Micro / Dell / HPE shipping two-phase factory-integrated, vendor named | High |
| 4 | Incumbent ships two-phase at scale | Vertiv CDU/cold plate GA, Boyd OMNICOOL productized | Competitive bear unless Accelsius is the OEM |
| 5 | Lab / Inception / conference | GTC booth, Equinix lab, HyperStart unnamed hyperscalers | Context only |
| 6 | Employee papers / posts | Heydari, Manaserh, ARPA-E, NSF | Confirms the physics path, not the vendor |

Never put rank 5–6 into `valuation.json` base.

---

## Sources to scrape (allowlist)

### A. Filings and earnings (highest signal per hour)

Pull with the existing US download path and transcript ingest. Keyword scan only these tickers:

- **NVDA, AMD:** "two-phase", "two phase", "pumped two-phase", "refrigerant", "direct-to-chip", "cold plate", "OMNICOOL", "COOLERCHIPS", "NeuCool", "Accelsius", "ZutaCore", "facility water", "W45", "W50"
- **VRT** (Vertiv): same list plus "CDU", "MegaMod"
- **JCI, EL.PA / ARNC-class Legrand:** Accelsius, NeuCool, two-phase
- **SMCI, DELL, HPE:** two-phase, Accelsius, liquid cooling SKU
- **EQIX, DLR, IRM:** liquid cooling lab / production
- **INV:** 8-K, 10-Q revenue, ownership %, SEPA draws, Accelsius contracts

Implementation: extend the existing filing digest keyword list for those tickers rather than a new crawler. Hits → the INV evidence note with filing path and page.

### B. First-party PDF drops (do not crawl the whole NVIDIA site)

Fetch only when a new URL appears on these indexes:

| Source | URL pattern | Cadence |
|--------|-------------|---------|
| ARPA-E COOLERCHIPS / OMNICOOL | `arpa-e.energy.gov` PDFs with NVIDIA, Heydari, Manaserh | Quarterly + on new upload |
| Hot Chips / GTC / OCP Global Summit | session PDFs from NVIDIA cooling tutorials | Event-driven (GTC spring, Hot Chips August, OCP October) |
| NVIDIA developer / MGX docs | cooling design guides | On version bump |
| AMD Instinct thermal design guides | AMD.com documentation | On version bump |
| Accelsius IR / newsroom | accelsius.com press, innventure IR | Weekly |
| NSF / IEEE papers | authors Heydari, Manaserh, Al-Zu'bi | Quarterly scholar alert |

Store PDFs under `INV/investor-documents/competitive/` (create on first file). Do not put them in `_system/`.

### C. X / Grok (optional, secondary)

Use only if you want leading *gossip* on the named engineers. This is not a primary source.

**Accounts to follow (not a firehose):**

- NVIDIA corporate + GTC
- Ali Heydari (if public)
- Vertiv IR / product
- Accelsius / Josh Claman
- ZutaCore
- Data Center Dynamics, The Register data-center desk

**Query allowlist (exact-ish):**

```
("two-phase" OR "two phase" OR "pumped two-phase") (cooling OR CDU OR "cold plate") (NVIDIA OR AMD OR Vertiv OR Accelsius OR NeuCool OR ZutaCore)
from: listed accounts
```

Cost: X API is metered. Run this **weekly**, not continuously. Cap: 50 posts/week, store IDs so you do not re-pull. Confirm with the operator before any paid X call (see Cursor X skill).

Do **not** "use Grok" as an unsupervised summarizer of the live web. If a Cloud Grok run exists, give it this file as the prompt, require citations to URLs, and have it write the dated evidence note. No stance, no IRR.

### D. Do not scrape

- NVIDIA employee LinkedIn wholesale
- Hyperscaler job boards as a "signal" (too noisy)
- Random Reddit / StockTwits
- The VIC Grok drop pipeline

---

## Recommended setup (this repo)

```
Weekly Cloud Marvin (not VIC Grok)
  1. SEC keyword scan NVDA AMD VRT JCI SMCI DELL INV
  2. Accelsius + Innventure IR RSS
  3. Check ARPA-E / GTC / OCP / AMD docs index for new PDFs
  4. Optional: X allowlist pull (if operator approved spend)
  5. Write INV/research/evidence/two_phase_watch_{date}.md
     - new hits by signal rank
     - "no material hit" is a valid outcome
  6. If rank 1–3: Slack/review pending, do not auto-edit valuation.json
```

Cadence: **weekly off-earnings**, plus **event days** (GTC, Hot Chips, OCP, INV/NVDA/AMD/VRT earnings).

Owner: Marvin research agent. Human promotes anything that should change Accelsius EV or ownership in `valuation.json`.

A Cursor Automation / `/loop` that only runs the watch script is fine. A Grok bot that chatters in Slack is not.

---

## Watchlist file (copy into the weekly note)

```
People: Ali Heydari, Yaman Manaserh, Greg Busch (Vertiv on OMNICOOL), Sukhvinder Kang (Boyd)
Products: NeuCool IR150, MR250, HyperStart; Vertiv MegaMod / CDU; ZutaCore; CoolIT
Chips: Blackwell, Vera Rubin, MI325X, MI355X, next Instinct
Operators: DarkNX Ontario 300 MW (65+65 MW halls), unnamed HyperStart hyperscalers
Falsifiers: Vertiv two-phase GA without Accelsius; NVIDIA reference names Boyd/Vertiv only; INV ownership <25%
```

---

## First backfill (already known, do not re-discover)

- Heydari, Hot Chips 2024, "Next-Generation Cooling For NVIDIA Accelerated Computing"
- ARPA-E OMNICOOL: NVIDIA + Vertiv + Boyd + Durbin + Binghamton + Villanova
- NSF paper: "Advancing in Data Centers Thermal Management: Experimental Assessment of Two-Phase Liquid Cooling Technology" (Heydari, Al-Zu'bi, Manaserh)
- Accelsius GTC 2026 IR150; NVIDIA Inception member
- DarkNX 300 MW; JCI Series B $65 million; Legrand
- INV Q2 2026 10-Q going concern; earnout on Accelsius contract >$15 million
