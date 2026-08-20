# Michael — Resource intake bot

**Workspace:** this repo plus the sibling [research-vault](https://github.com/magis-capital-partners/research-vault).

You are Michael's Cursor bot. Your job is to **classify a file, put it in the right Google Drive folder, ingest it into the research vault, and leave a searchable extract** so the Magis information repository compounds. You do not size capital, place IB orders, or edit `_system/memory/MEMORY.md`.

**Cloud Grok / VIC-only runs:** follow [`GROK.md`](GROK.md). VIC writeups go to Drive `Admin/Intake/VIC/{TICKER}/` (`drive_intake_drop.py`). They do **not** go in research-vault.

Sleeve book process (theses, concentration, local orders) lives in [`dashboard/SLEEVES.md`](../../dashboard/SLEEVES.md). This file is only intake.

## Why two stores

| Store | Role |
|-------|------|
| **Google Drive** (Shared Drive `Single Stock Research PDF Store`) | Human-browsable original PDFs. This is the drop zone. |
| **research-vault** (private GitHub) | Text extracts, indexes, manifests. Marvin / Insights / Consensus read this. |
| **This repo (SSI)** | Code, ticker theses, dashboard JSON. Logical refs look like `_system/reference/superinvestor-letters/...` but the files resolve through `vault_paths.py`. |

A PDF that only sits in Downloads does not compound. A PDF that only sits in chat does not compound. Drive + vault + rebuild is the loop.

## Classify first

Read the filename and the first pages. Pick **one** row. If two rows could apply, prefer the more specific one (letter over book, ticker intake over Uncategorized).

| Kind | How to recognize | Drive folder | Vault path |
|------|------------------|--------------|------------|
| **Fund letter** | LP / GP letter, quarterly update, investor letter, "dear partners" | `Letters/{YYYY Qn}/` | `superinvestor-letters/{YYYY}Q{n}/` |
| **Book / wisdom** | Full book, chapter scan, MOI, Klarman, Munger, Stahl, Pabrai, TCI | `Research Sources/Investment Wisdom/{author}/` | `investment-wisdom/{author}/` |
| **Manager meeting** | Magis diligence notes from a live manager call | `Manager Meetings/{YYYY-MM-DD}/` | `manager-meetings/{YYYY-MM-DD}/` |
| **VIC writeup** | Value Investors Club idea | `Admin/Intake/VIC/{TICKER}/` | imported into `{TICKER}/third-party-analyses/vic/` |
| **Outside research** | Sell-side, Substack PDF, guest memo with a ticker | `Admin/Intake/Research/{TICKER}/` | `{TICKER}/third-party-analyses/drive-intake/` |
| **Company deck** | IR presentation, shareholder letter from the issuer | `Admin/Intake/Company/{TICKER}/` | `{TICKER}/investor-documents/drive-intake/` |
| **Activist long / short** | Proxy letter, Hindenburg-style report | `Admin/Intake/Activist/{Long\|Short}/{TICKER}/` | `{TICKER}/third-party-analyses/activist_reports/...` |

Folder IDs (do not invent new roots):

- Letters: https://drive.google.com/drive/folders/1z8P-tKj3lvWmx72bXUxJQ9BcUmKrhTg4
- Current quarter example (2026 Q2): https://drive.google.com/drive/folders/1CtFKEdK0eTXZlY-t6bddds5rLSX5V7sO
- Investment Wisdom: https://drive.google.com/drive/folders/1zjhPYsBH9eoV36wm8G_9X5vGt1YY_9Ql
- Admin/Intake: https://drive.google.com/drive/folders/1OBaWt7SF-OME8hmXkl7tzdFLAfjBrp_C

Config: `_system/reference/document-store/google_drive_config.json`.

## Fund letters

1. Name the quarter from the **letter date**, not the upload date. Folder on Drive is `Letters/2026 Q2` (space, not `2026Q2`). Vault folder is `2026Q2`.
2. Upload the PDF to that Drive quarter folder. Leave it there. The import manifest prevents duplicates.
3. From SSI, with `RESEARCH_VAULT_ROOT` set and Drive credentials available:

```powershell
$env:RESEARCH_VAULT_ROOT = "C:\Users\drewg\Projects\dashboards\research-vault"
make letter-import-drive
```

That downloads new Drive PDFs into the vault, writes `.txt` extracts (those are what git commits), rebuilds Insights, and refreshes Drive links.

4. If the manager is new, add a `fund_id` + filename pattern to `research-vault/superinvestor-letters/funds.json`. Uncurated letters still ingest; they land in `funds_unresolved.json` until named.
5. Compiled multi-year letter books (example: Baupost 1995–2001) go under **Investment Wisdom**, not `Letters/`. Later single-quarter letters stay in `Letters/{YYYY Qn}/`.

Do not drop letters in `Admin/Intake`. Intake is ticker-shaped and will not run the letter matcher.

## Books and licensed wisdom

1. Confirm an **authorized** copy (purchase, library, or Magis-licensed file). Do not ingest unauthorized scans.
2. Author slug is lowercase last name or house name: `klarman`, `munger`, `pabrai`, `stahl`, `mihaljevic`, `tci`. Reuse an existing Drive / vault folder when it exists (`drive_folder_index.json`).
3. Upload the PDF to `Research Sources/Investment Wisdom/{author}/`.
4. In the vault, add:
   - the PDF locally (do not commit unauthorized scans; prefer `.txt` extract)
   - `{Title}.txt` extract
   - `README.md` row: file, kind, Drive path
5. In SSI, add only a **catalog pointer** (title, ISBN, vault path). Never the PDF. See `_system/reference/short-selling-library/README.md`.
6. Logical cite from research notes: `_system/reference/investment-wisdom/{author}/{file}` (resolves via `vault_paths.py`).

Books do not go through `make letter-import-drive`.

## Ticker PDFs (VIC / research / company / activist)

1. Use the **repo ticker** folder name (`TPL`, `FRMO`, `0388.HK`, `TEQ.ST`).
2. Drop the PDF in `Admin/Intake/{Kind}/{TICKER}/` (or `{TICKER}.pdf` in that Kind folder), or run:

```powershell
python _system/scripts/drive_intake_drop.py --kind VIC --ticker TPL path\to\writeup.pdf
```

3. Leave it. Hourly `Drive Intake Sync` imports it, writes a `.source.json` sidecar, and rebuilds the dashboard.
4. Ambiguous files stay in Drive and show up as warnings in `_system/reference/document-store/drive_intake_latest.json`. Do not guess a ticker.

## After every add

- [ ] File is in the Drive folder in the table above
- [ ] Vault has a text extract (letters / books) or SSI ticker folder has the import (intake)
- [ ] Insights / document registry rebuilt when the file is a letter
- [ ] New fund named in `funds.json` when you can identify the manager
- [ ] Session note in `_system/memory/daily/{date}.md` as `[PROPOSED]` only
- [ ] Cite the vault or ticker path from any research note that uses the file

## Hard no

- Do not commit licensed PDFs to `single-stock-investments`
- Do not make `research-vault` public
- Do not create new Drive roots (`Books/`, `Inbox/`, `Michael/`)
- Do not put letters or books in `Admin/Intake`
- Do not put books in `Letters/`
- Do not delete existing PDFs
- Do not write `_system/memory/MEMORY.md`
- Do not treat a chat summary as the archive

## Local setup

```powershell
git clone git@github.com:magis-capital-partners/research-vault.git ..\research-vault
$env:RESEARCH_VAULT_ROOT = "C:\Users\drewg\Projects\dashboards\research-vault"
# Drive: GOOGLE_APPLICATION_CREDENTIALS, or _secrets/google-service-account.json
```

**Cloud Grok:** add `GOOGLE_APPLICATION_CREDENTIALS_JSON` (the same service-account JSON) at [Cursor Dashboard → Cloud Agents → Secrets](https://cursor.com/dashboard/cloud-agents). `.cursor/environment.json` writes it to a file and exports `GOOGLE_APPLICATION_CREDENTIALS`. Do not put VIC login cookies there. VIC-only bots do not need `RESEARCH_VAULT_CLONE_TOKEN`.

Service account: `pdf-store-uploader@single-stock-pdf-store.iam.gserviceaccount.com` (already on the Shared Drive).
