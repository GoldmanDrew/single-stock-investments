# VIC intake workflow

The former local bookmarklet/dashboard script is retired at `_system/scripts/attic/vic_local_intake.py`. Do not wire it into workflows or use the obsolete `_system/scripts/vic_local_intake.py` path.

## Supported route

For a VIC PDF the user already has:

```powershell
python _system/scripts/materialize_drive_credentials.py --require
python _system/scripts/drive_intake_drop.py --kind VIC --ticker TPL path\to\writeup.pdf
```

The uploader accepts only PDFs and existing repo ticker folders. It writes `Admin/Intake/VIC/{TICKER}/`, records a content hash, and returns `already_present` rather than duplicating an identical upload.

The Data Pipeline Drive job runs daily at 14:00 UTC. It imports the PDF to `{TICKER}/third-party-analyses/vic/`, writes a `.source.json` sidecar, updates the Drive-ID manifest and source inventory, and records unresolved files in the GitHub job summary plus `_system/reference/document-store/drive_intake_latest.json`.

For text that cannot be represented as a PDF:

1. Write `{TICKER}/third-party-analyses/vic/vic_{date}_{slug}_{hash}.md`.
2. Run `python _system/scripts/third_party_inventory.py TICKER`.
3. Commit the text and refreshed inventory through the normal branch/PR path.

Text-only intake does not pass through Drive.

## Boundaries

- No GitHub Actions workflow stores or uses VIC login credentials.
- No scheduled VIC crawl, login automation, or bulk retrieval is supported.
- VIC does not go in research-vault.
- Unknown or ambiguous tickers are not guessed and do not create ticker folders.

## Approval rule

VIC intakes remain `pending` until a human adds an explicit approved-registry row in `_system/frameworks/third_party_sources.md`.

Pending VIC notes may be used as variant-perception context only. They may not be used in base IRR, target price, or stance.
