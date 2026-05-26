# Investment Wisdom Library

Curated PDF writings for Marvin's mental-model layer: **Charlie Munger**, **Mohnish Pabrai**, **Murray Stahl**, **Horizon Kinetics**, and **Chris Hohn / TCI** extracts.

**Path:** `_system/reference/investment-wisdom/`

Marvin should cite these files by path when applying frameworks. Primary company research still lives in ticker folders; this library is for **how to think**, not **what we hold**.

**Catalog:** `_system/frameworks/mental_models.md` — tiered mental models with triggers and questions.

## Structure

```
investment-wisdom/
├── README.md           ← this file
├── INDEX.md            ← catalog with themes
├── manifest.csv        ← machine-readable inventory
├── munger/             ← mental models, psychology, worldly wisdom
├── pabrai/             ← Dhando, partner letters, capital allocation
├── stahl/              ← croupiers, exchanges, diversification, spinoffs
├── horizon-kinetics/   ← equity yield curve, quarterly commentary extracts (.txt)
└── tci/                ← Chris Hohn letters; operating mechanics + valuation bridge
```

## Stahl source vault

The full Murray Stahl / Horizon Kinetics archive (400+ PDFs) remains at:

`C:\Users\werdn\Documents\Investing\Horizon Kinetics\hk_pdfs\`

The **stahl/** folder includes the compilation PDF (hard-linked) plus key thematic essays. **horizon-kinetics/** holds curated text extracts for equity yield curve and recent commentaries. See `horizon-kinetics/README.md` and `stahl/` + `INDEX.md` for chapter-level mapping to the manuscript at `Horizon Kinetics/hk_pdfs/book/manuscript/`.

## Human promotion

Distilled beliefs from these writings are promoted to `_system/memory/MEMORY.md` under genius-specific sections after review — never written directly by Marvin during sessions.

## Adding PDFs

Drop new PDFs into the appropriate subfolder and run:

```powershell
python _system/scripts/build_wisdom_manifest.py
```

### Pabrai partner letters (2021+)

Official URL pattern (verified 2026-05-21):

```
https://pabraifunds.com/pdf/web/l_MMDDYY.pdf
```

Example: `l_010124.pdf` = Jan 2024 letter. Index of filenames: scrape `https://pabraifunds.com/letter-to-partner/` for `file=l_*.pdf` links.

Pre-2021 Jan letters: `https://snowballing-co.s3.amazonaws.com/media/l_MMDDYY.pdf` (may 403 on newer requests).
