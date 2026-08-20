# Drive Intake

Ticker-shaped PDFs only (VIC, outside research, company decks, activist). Fund letters and books use a different route: `_system/agents/MICHAEL.md`.

Use this Shared Drive folder as the repo drop zone:

- Folder: https://drive.google.com/drive/folders/1OBaWt7SF-OME8hmXkl7tzdFLAfjBrp_C
- Path on Shared Drive: `Admin/Intake`
- Label: Single Stock Research PDF Store
- Service account: `pdf-store-uploader@single-stock-pdf-store.iam.gserviceaccount.com`
- Workflow: `Drive Intake Sync` runs hourly at minute 20 UTC and can also be run manually.

The live Drive layout is under `Admin/Intake` by intake type:

```text
Admin/
  Intake/
    VIC/
      TPL.pdf
      FRMI.pdf
    Research/
      TPL.pdf
    Company/
      TPL.pdf
```

## Grok / CLI drop

Cloud Grok and local agents can upload without clicking Drive:

```powershell
python _system/scripts/drive_intake_drop.py --kind VIC --ticker TPL path\to\writeup.pdf
```

Requires `GOOGLE_APPLICATION_CREDENTIALS`, `GOOGLE_APPLICATION_CREDENTIALS_JSON` (Cloud Agent secret), or `_secrets/google-service-account.json`. VIC still does not go in research-vault. Prompt: `_system/agents/GROK.md`.

## Where To Drop PDFs

Ticker subfolders are also accepted:

```text
Admin/
  Intake/
    VIC/
      TPL/
        VIC writeup.pdf
    Research/
      TPL/
        outside report.pdf
    Company/
      TPL/
        company presentation.pdf
    Activist/
      Long/
        DIS/
          elliott-proxy-letter.pdf
      Short/
        APLD/
          hindenburg-report.pdf
```

Use the exact repo ticker folder name, for example `TPL`, `FRMO`, `0388.HK`, or `TEQ.ST`.

For the flat layout, put the ticker as the filename or as the first clear filename token, such as `TPL.pdf` or `TPL - outside report.pdf`.

Arbitrary filenames (including bare VIC ids such as `163625.pdf`) are also accepted when the PDF text uniquely identifies a repo ticker. The importer extracts text (pypdf, with optional OCR fallback), resolves a single ticker, imports locally, and moves the Drive file under `Admin/Intake/{Kind}/{TICKER}/`. Ambiguous or unreadable PDFs stay in place and appear under `warnings` in `drive_intake_latest.json` (non-fatal).

## Routing

- `Admin/Intake/VIC/{TICKER}.pdf` (or `VIC/{TICKER}.pdf` relative to the intake root) imports to `{TICKER}/third-party-analyses/vic/`
- `Admin/Intake/Research/{TICKER}.pdf` imports to `{TICKER}/third-party-analyses/drive-intake/`
- `Admin/Intake/Company/{TICKER}.pdf` imports to `{TICKER}/investor-documents/drive-intake/`
- `Admin/Intake/Activist/Long/{TICKER}/*.pdf` imports to `{TICKER}/third-party-analyses/activist_reports/long/`
- `Admin/Intake/Activist/Short/{TICKER}/*.pdf` imports to `{TICKER}/third-party-analyses/activist_reports/short/`

The older `Admin/{VIC,Research,Company}/...` layout is still accepted if those folders exist.

After local import, the normal registry/upload step links the PDFs back into the PDF store folders used by the dashboard:

- VIC: `Single Stocks/{TICKER}/VIC/`
- Research: `Single Stocks/{TICKER}/Research/drive-intake/`
- Company: `Single Stocks/{TICKER}/Company/drive-intake/`
- Activist long: `Single Stocks/{TICKER}/Activist/long/`
- Activist short: `Single Stocks/{TICKER}/Activist/short/`

## Automation Flow

1. Drop PDFs into the appropriate Drive intake folder.
2. `Drive Intake Sync` scans the configured intake folder/root, creates missing intake folders, and imports new PDFs.
3. Each imported PDF gets a `.source.json` sidecar with Drive source metadata.
4. `_system/data/drive_intake_manifest.json` records Drive file IDs so the same file is not imported again.
5. The workflow rebuilds the third-party source inventory, document registry, Drive PDF links, insights, research memory, and dashboard data.
6. Letter source links use `_system/reference/document-store/drive_filename_index.json` (full Shared Drive PDF scan) and `_system/reference/document-store/letter_drive_links.json` (maps `letters_index.json` paths to Drive file URLs). These refresh during Drive Intake Sync when credentials are present.
7. The workflow commits the imported documents and rebuilt dashboard artifacts back to `main`.

## Required GitHub Secret

Drive folder access alone is not enough for GitHub Actions. The repo also needs an Actions secret named `GOOGLE_APPLICATION_CREDENTIALS_JSON` containing the full JSON key for `pdf-store-uploader@single-stock-pdf-store.iam.gserviceaccount.com`.

## Rules

- Upload PDFs only.
- Leave files in Drive after upload; the manifest prevents duplicate imports.
- Use existing repo tickers. Unknown / ambiguous PDFs (after content resolve) are reported as `warnings` in `_system/reference/document-store/drive_intake_latest.json`; operational failures remain `errors`.
- Use `--strict` on `import_drive_intake.py` to fail the run when any warning remains (local debugging).
- Use `VIC` only for Value Investors Club writeups; use `Research` for other outside research PDFs; use `Company` for company presentations or manually collected company PDFs; use `Activist/Long` or `Activist/Short` for activist letters, proxy fights, and forensic short reports.
